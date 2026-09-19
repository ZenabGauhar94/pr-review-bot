"""
Parses a unified diff (the format GitHub's compare API and `git diff` both
produce) into structured, per-file, per-line data.

Why we need this instead of just handing the LLM the raw diff:
1. LLMs are unreliable at mapping a line *inside a diff hunk* back to the
   real line number in the final file. If we want to post inline PR
   comments, GitHub's API needs the real file line number, not "line 7 of
   the diff hunk". We compute that ourselves so we never have to trust the
   model on this.
2. Keeping the diff structured lets us filter (e.g. skip generated files,
   skip pure deletions) before spending tokens on the LLM call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class DiffLine:
    # Line number in the NEW version of the file. None for removed lines,
    # since a removed line has no position in the new file.
    new_lineno: int | None
    # "+" added, "-" removed, " " context (unchanged)
    kind: str
    content: str


@dataclass
class FileDiff:
    old_path: str
    new_path: str
    lines: list[DiffLine] = field(default_factory=list)

    def added_lines(self) -> list[DiffLine]:
        return [l for l in self.lines if l.kind == "+"]


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """Parse a full multi-file unified diff into a list of FileDiff objects."""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_lineno = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git"):
            # e.g. "diff --git a/foo.py b/foo.py" — new file section starting.
            current = None
            continue

        if raw_line.startswith("--- "):
            old_path = raw_line[4:].strip()
            old_path = old_path[2:] if old_path.startswith(("a/", "b/")) else old_path
            continue

        if raw_line.startswith("+++ "):
            new_path = raw_line[4:].strip()
            new_path = new_path[2:] if new_path.startswith(("a/", "b/")) else new_path
            current = FileDiff(old_path=old_path, new_path=new_path)
            files.append(current)
            continue

        hunk_match = HUNK_HEADER_RE.match(raw_line)
        if hunk_match:
            new_lineno = int(hunk_match.group(3))
            continue

        if current is None:
            continue  # preamble lines (index, mode changes, etc.)

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current.lines.append(DiffLine(new_lineno, "+", raw_line[1:]))
            new_lineno += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            current.lines.append(DiffLine(None, "-", raw_line[1:]))
        else:
            content = raw_line[1:] if raw_line.startswith(" ") else raw_line
            current.lines.append(DiffLine(new_lineno, " ", content))
            new_lineno += 1

    return files


def render_for_llm(files: list[FileDiff], max_chars: int = 12000) -> str:
    """
    Render parsed diffs back into a compact, line-numbered format for the
    LLM prompt. We prefix every line with its real file line number so the
    model can report line numbers directly instead of us having to guess
    which line it meant.
    """
    out = []
    budget = max_chars
    for f in files:
        block = [f"### FILE: {f.new_path}"]
        for line in f.lines:
            if line.kind == "-":
                continue  # removed lines aren't reviewable in the new file
            prefix = "+" if line.kind == "+" else " "
            block.append(f"{line.new_lineno:>5} {prefix} {line.content}")
        block_text = "\n".join(block)
        if budget - len(block_text) < 0:
            out.append(f"### FILE: {f.new_path}\n[... skipped, diff too large for budget ...]")
            continue
        budget -= len(block_text)
        out.append(block_text)
    return "\n\n".join(out)
