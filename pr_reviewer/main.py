"""
Entry point run inside the GitHub Action. Reads the PR event context that
GitHub injects into the runner, fetches the diff, runs static analysis +
LLM review, and posts the result back as a PR review.

Run locally with --dry-run to test the pipeline without posting to GitHub
(prints the review to stdout instead). This is also what eval/run_eval.py
uses under the hood.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from pr_reviewer.diff_parser import parse_unified_diff, render_for_llm
from pr_reviewer.github_client import GitHubClient
from pr_reviewer.llm_review import LLMOutputError, review_diff
from pr_reviewer.schemas import ReviewResult
from pr_reviewer.static_analysis import render_for_llm as render_static, run_ruff


def get_pr_context_from_event() -> tuple[str, int]:
    """Reads GITHUB_REPOSITORY and the PR number out of the GitHub Actions
    event payload (GITHUB_EVENT_PATH). See:
    https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#pull_request
    """
    repo = os.environ["GITHUB_REPOSITORY"]
    event_path = os.environ["GITHUB_EVENT_PATH"]
    with open(event_path) as f:
        event = json.load(f)
    pr_number = event["pull_request"]["number"]
    return repo, pr_number


def run_review_on_diff_text(diff_text: str) -> ReviewResult:
    files = parse_unified_diff(diff_text)
    changed_paths = [f.new_path for f in files]

    static_findings = run_ruff(changed_paths)
    static_text = render_static(static_findings)
    diff_text_for_llm = render_for_llm(files)

    return review_diff(diff_text_for_llm, static_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print review instead of posting to GitHub")
    parser.add_argument("--diff-file", help="Review a local diff file instead of fetching from GitHub")
    args = parser.parse_args()

    if args.diff_file:
        with open(args.diff_file) as f:
            diff_text = f.read()
        result = run_review_on_diff_text(diff_text)
        print(result.model_dump_json(indent=2))
        return 0

    repo, pr_number = get_pr_context_from_event()
    client = GitHubClient(token=os.environ["GITHUB_TOKEN"], repo=repo)
    diff_text = client.get_pr_diff(pr_number)

    try:
        result = run_review_on_diff_text(diff_text)
    except LLMOutputError as e:
        print(f"::error::LLM review failed: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(result.model_dump_json(indent=2))
    else:
        client.post_review(pr_number, result)
        print(f"Posted review with {len(result.issues)} issue(s) on PR #{pr_number}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
