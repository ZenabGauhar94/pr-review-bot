"""
Calls an LLM to review a diff and returns a validated ReviewResult. This is
the "AI engineering" core of the project: prompt design, forcing structured
JSON output, and defensively handling a model that doesn't perfectly follow
instructions.

Uses Groq's free API (no credit card required) via the OpenAI-compatible
client -- Groq serves open-weight models (Llama 3.3 70B here) on custom
inference hardware.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI
from pydantic import ValidationError

from pr_reviewer.schemas import ReviewResult

MODEL = "openai/gpt-oss-120b"
BASE_URL = "https://api.groq.com/openai/v1"

SYSTEM_PROMPT = """You are a senior software engineer doing a pull request code review.

You will be given:
1. A diff, with real file line numbers prefixed on every line ("+" = added line).
2. Static analysis findings from a linter (may be empty).

Review ONLY the added ("+") lines. Do not comment on unchanged context lines.
Focus on: correctness bugs, security issues, and maintainability problems.
Do not comment on pure style preferences the linter would already catch — the
linter findings are given to you so you don't have to repeat them.

Respond with ONLY a JSON object matching this exact schema, no other text,
no markdown code fences:

{
  "summary": "1-3 sentence overall summary of the change",
  "overall_risk": "nit" | "suggestion" | "bug" | "security",
  "issues": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "nit" | "suggestion" | "bug" | "security",
      "category": "correctness" | "style" | "performance" | "security" | "maintainability" | "testing",
      "comment": "specific, actionable explanation, under 500 chars",
      "confidence": 0.0 to 1.0
    }
  ]
}

If you find nothing worth flagging, return an empty issues list. Do not
invent issues to appear thorough — precision matters more than volume.
"""


def review_diff(diff_text_for_llm: str, static_findings_text: str) -> ReviewResult:
    client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url=BASE_URL)

    user_message = f"""## Static analysis findings
{static_findings_text}

## Diff to review
{diff_text_for_llm}
"""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw_text = response.choices[0].message.content or ""
    raw_text = _strip_markdown_fences(raw_text)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise LLMOutputError(f"Model did not return valid JSON: {e}\nRaw: {raw_text[:500]}") from e

    try:
        return ReviewResult.model_validate(parsed)
    except ValidationError as e:
        raise LLMOutputError(f"Model JSON did not match schema: {e}") from e


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


class LLMOutputError(Exception):
    """Raised when the model's output can't be parsed/validated as a ReviewResult."""