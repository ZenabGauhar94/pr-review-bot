"""
Eval harness: runs the review pipeline against a small labeled set of diffs
with known, hand-injected issues, and reports how many it caught.

This is intentionally simple (line + category match, no fuzzy matching) —
the point isn't a sophisticated eval framework, it's proving the pipeline's
accuracy is *measured* rather than assumed. Run this after any prompt
change to check for regressions before you trust the bot on a real repo.

Usage:
    python eval/run_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pr_reviewer.main import run_review_on_diff_text  # noqa: E402

EVAL_DIR = Path(__file__).parent


def matches(issue, expected) -> bool:
    return issue.file == expected["file"] and issue.line == expected["line"] and issue.category.value == expected["category"]


def main() -> None:
    with open(EVAL_DIR / "eval_set.json") as f:
        eval_set = json.load(f)["cases"]

    total_expected = 0
    total_caught = 0
    total_flagged = 0
    total_true_positive_flags = 0

    print(f"{'case':<25} {'expected':>8} {'caught':>8} {'flagged':>8}")
    print("-" * 55)

    for case in eval_set:
        diff_path = EVAL_DIR / case["diff_file"]
        diff_text = diff_path.read_text()
        result = run_review_on_diff_text(diff_text)

        expected = case["expected_findings"]
        caught = sum(1 for exp in expected if any(matches(issue, exp) for issue in result.issues))
        true_positive_flags = sum(1 for issue in result.issues if any(matches(issue, exp) for exp in expected))

        total_expected += len(expected)
        total_caught += caught
        total_flagged += len(result.issues)
        total_true_positive_flags += true_positive_flags

        print(f"{diff_path.stem:<25} {len(expected):>8} {caught:>8} {len(result.issues):>8}")
        for issue in result.issues:
            print(f"    -> {issue.file}:{issue.line} [{issue.category.value}] {issue.comment[:80]}")

    recall = total_caught / total_expected if total_expected else 1.0
    precision = total_true_positive_flags / total_flagged if total_flagged else 1.0

    print("-" * 55)
    print(f"Recall:    {recall:.0%}  ({total_caught}/{total_expected} known issues caught)")
    print(f"Precision: {precision:.0%}  ({total_true_positive_flags}/{total_flagged} flags were real)")


if __name__ == "__main__":
    main()