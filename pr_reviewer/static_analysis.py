"""
Runs `ruff` (a fast Python linter) over changed files and returns findings
in a plain dict format.

Why bother with a linter when we also have an LLM review? Two reasons:
1. Linters are deterministic and cheap. Anything a linter can catch, it
   should catch — don't burn LLM tokens (or risk a hallucinated miss) on
   things regex/AST-based tools already solve reliably.
2. We feed the linter's findings INTO the LLM prompt as extra context, so
   the model can reason about them ("this unused import is fine here
   because...") instead of duplicating the same checks blindly.
"""

from __future__ import annotations

import json
import subprocess


def run_ruff(file_paths: list[str], repo_root: str = ".") -> list[dict]:
    """Run ruff on the given files and return its findings as a list of dicts.
    Returns an empty list (rather than raising) if ruff isn't installed or
    a file no longer exists, so this never blocks the pipeline.
    """
    py_files = [f for f in file_paths if f.endswith(".py")]
    if not py_files:
        return []

    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", *py_files],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if not result.stdout.strip():
        return []

    try:
        findings = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return [
        {
            "file": f.get("filename"),
            "line": f.get("location", {}).get("row"),
            "code": f.get("code"),
            "message": f.get("message"),
        }
        for f in findings
    ]


def render_for_llm(findings: list[dict]) -> str:
    if not findings:
        return "(no static analysis findings)"
    lines = [f"{f['file']}:{f['line']} [{f['code']}] {f['message']}" for f in findings]
    return "\n".join(lines)
