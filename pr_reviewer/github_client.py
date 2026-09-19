"""
Thin wrapper around the GitHub REST API: fetch a PR's diff, and post a
review with inline comments back onto it.

We use plain `requests` instead of a heavier SDK so it's obvious exactly
which API calls are being made — useful to point to in an interview.
"""

from __future__ import annotations

import requests

from pr_reviewer.schemas import ReviewResult

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str, repo: str):
        """repo is "owner/name", e.g. "octocat/hello-world"."""
        self.repo = repo
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get_pr_diff(self, pr_number: int) -> str:
        url = f"{GITHUB_API}/repos/{self.repo}/pulls/{pr_number}"
        resp = self.session.get(url, headers={"Accept": "application/vnd.github.v3.diff"})
        resp.raise_for_status()
        return resp.text

    def get_pr_head_sha(self, pr_number: int) -> str:
        url = f"{GITHUB_API}/repos/{self.repo}/pulls/{pr_number}"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()["head"]["sha"]

    def post_review(self, pr_number: int, result: ReviewResult) -> None:
        """Post one PR review containing a summary body plus inline comments
        on each flagged line."""
        head_sha = self.get_pr_head_sha(pr_number)

        comments = [
            {
                "path": issue.file,
                "line": issue.line,
                "body": f"**[{issue.severity.value}/{issue.category.value}]** {issue.comment} "
                f"(confidence: {issue.confidence:.0%})",
            }
            for issue in result.issues
        ]

        body = f"🤖 **Automated review** — risk: `{result.overall_risk.value}`\n\n{result.summary}"
        if not comments:
            body += "\n\nNo specific issues flagged."

        url = f"{GITHUB_API}/repos/{self.repo}/pulls/{pr_number}/reviews"
        payload = {
            "commit_id": head_sha,
            "body": body,
            "event": "COMMENT",  # use "COMMENT" not "REQUEST_CHANGES" — be a helpful bot, not a blocking gate
            "comments": comments,
        }
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
