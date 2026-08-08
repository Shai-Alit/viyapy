#!/usr/bin/env python3
"""AI pull-request reviewer backed by an Azure AI Foundry (Azure OpenAI) model.

Runs in GitHub Actions on a pull request. It pulls the PR's diff, asks the
configured model (e.g. a ``gpt-5.1-codex`` deployment) to review it, and posts
the findings back as an inline PR review — one comment anchored to each relevant
changed line, plus a summary.

Design notes
------------
* Standard library only (``urllib``) so the workflow needs no ``pip install``.
* Comment-only: the review is submitted with ``event=COMMENT`` and never blocks
  the merge. Configuration errors exit non-zero (so they surface during setup);
  transient model/API errors also exit non-zero to show a visible signal, but a
  best-effort summary comment is posted first when possible.
* Line anchoring is validated against the diff. The model is only allowed to
  comment on added (``+``) lines; any finding that names a line outside the diff
  is demoted into the summary rather than dropped, because GitHub rejects a
  review whose comments fall outside the changed ranges.

Environment
-----------
GITHUB_TOKEN, GITHUB_REPOSITORY (``owner/repo``), PR_NUMBER,
AZURE_OPENAI_ENDPOINT (the Foundry base, e.g.
``https://<name>.services.ai.azure.com``), AZURE_OPENAI_API_KEY,
AZURE_OPENAI_MODEL (the deployed model name, e.g. ``gpt-5.1-codex``).

The Foundry **v1** API surface is used: ``{endpoint}/openai/v1/chat/completions``
with a ``Bearer`` token and the model named in the request body — no
``api-version`` query string and no ``/deployments/`` path segment.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

GITHUB_API = "https://api.github.com"
# Only diffs up to this many characters are sent to the model; larger PRs are
# truncated with a marker so the request stays bounded and cheap.
MAX_DIFF_CHARS = 200_000
MAX_OUTPUT_TOKENS = 8000
SEVERITY_ORDER = ("blocking", "major", "minor", "nit")
SEVERITY_LABEL = {
    "blocking": "🔴 Blocking",
    "major": "🟠 Major",
    "minor": "🟡 Minor",
    "nit": "🔵 Nit",
}


def _env(name: str, *, required: bool = True) -> str:
    value = os.environ.get(name, "").strip()
    if required and not value:
        sys.exit(f"ai_review: missing required environment variable {name!r}")
    return value


# ---------------------------------------------------------------------------
# GitHub REST helpers
# ---------------------------------------------------------------------------
def _gh_request(
    method: str, path: str, token: str, *, accept: str, body: dict[str, Any] | None = None
) -> Any:
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "viyapy-ai-reviewer")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed host)
        raw = resp.read().decode()
    return json.loads(raw) if raw else None


def get_pr_files(repo: str, pr: str, token: str) -> list[dict[str, Any]]:
    """Return every changed file in the PR (following pagination)."""
    files: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _gh_request(
            "GET",
            f"/repos/{repo}/pulls/{pr}/files?per_page=100&page={page}",
            token,
            accept="application/vnd.github+json",
        )
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


# ---------------------------------------------------------------------------
# Diff parsing
# ---------------------------------------------------------------------------
def annotate_patch(patch: str) -> tuple[str, set[int]]:
    """Number a unified-diff patch by new-file line and collect commentable lines.

    Returns the annotated text (each line prefixed with its new-file line number
    where one exists) and the set of new-file line numbers that are *added*
    lines — the only lines a review comment may anchor to.
    """
    out: list[str] = []
    added: set[int] = set()
    new_line = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            # @@ -old,cnt +new,cnt @@
            try:
                new_part = line.split("+", 1)[1].split(" ", 1)[0]
                new_line = int(new_part.split(",", 1)[0])
            except (IndexError, ValueError):
                new_line = 0
            out.append(f"        {line}")
        elif line.startswith("+") and not line.startswith("+++"):
            added.add(new_line)
            out.append(f"{new_line:>6} + {line[1:]}")
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            out.append(f"       - {line[1:]}")
        elif line.startswith(("+++", "---")):
            continue
        else:  # context line
            out.append(f"{new_line:>6}   {line[1:] if line else ''}")
            new_line += 1
    return "\n".join(out), added


def build_diff_blob(files: list[dict[str, Any]]) -> tuple[str, dict[str, set[int]]]:
    """Build the annotated diff text and per-file set of commentable lines."""
    valid: dict[str, set[int]] = {}
    chunks: list[str] = []
    for f in files:
        patch = f.get("patch")
        path = f["filename"]
        if not patch:  # binary, renamed-only, or too large to diff
            chunks.append(f"### {path} ({f.get('status')}, no textual diff)\n")
            continue
        annotated, added = annotate_patch(patch)
        valid[path] = added
        chunks.append(f"### {path} ({f.get('status')})\n{annotated}\n")
    blob = "\n".join(chunks)
    if len(blob) > MAX_DIFF_CHARS:
        blob = blob[:MAX_DIFF_CHARS] + "\n\n[diff truncated — PR too large to send in full]"
    return blob, valid


# ---------------------------------------------------------------------------
# Model call (Azure OpenAI chat completions)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an independent, senior Python-library reviewer for `viyapy`, a typed
client for SAS Viya Intelligent Decisioning that MUST support both Viya 3.5 and
Viya 4 (LTS + Stable) behind a version/dialect layer. The design intent lives in
PRODUCTION_PLAN.md.

Review priorities, highest first:
1. Correctness & error handling — no bare/blind `except`, no `print` in library
   code (use logging), never return None to signal failure, every HTTP call has a
   timeout, failures raise typed `ViyaError` subclasses.
2. Public API quality — full type hints (mypy --strict), docstrings on public
   API, no secrets/tokens leaked in logs or `__repr__`.
3. Viya version handling — 3.5 vs 4 differences belong in the dialect layer, not
   scattered `if version ==` checks; watch the MAS `output` vs `outputs` shape.
4. Tests — new/changed logic has unit tests with mocked HTTP (no network), error
   branches covered, per-generation fixtures.
5. Security & packaging hygiene; docs/CHANGELOG updated when relevant.

For `src/viyapy/**` enforce priorities 1-3 strictly. For `tests/**` require no
network use and error-branch + per-generation-fixture coverage.

Be specific, concise, and high-signal — prefer fewer, important findings over
nitpicks. Only comment on lines marked `+` (added) in the diff; use the integer
line number shown at the start of that line. If the PR looks good, say so in the
summary and return an empty comments list.

Respond with ONLY a JSON object of this exact shape:
{
  "summary": "markdown overall assessment, note any blocking issues",
  "comments": [
    {"path": "src/viyapy/x.py", "line": 42, "severity": "blocking|major|minor|nit",
     "body": "markdown explanation of the issue and a concrete suggestion"}
  ]
}"""


def call_model(diff_blob: str) -> dict[str, Any]:
    endpoint = _env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    model = _env("AZURE_OPENAI_MODEL")
    api_key = _env("AZURE_OPENAI_API_KEY")

    url = f"{endpoint}/openai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Review this pull-request diff:\n\n{diff_blob}"},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
        "reasoning_effort": "medium",
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 (configured host)
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        sys.exit(f"ai_review: Azure OpenAI call failed ({exc.code}): {detail}")

    content = data["choices"][0]["message"]["content"]
    return _parse_json(content)


def _parse_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(content[start : end + 1])
        raise


# ---------------------------------------------------------------------------
# Posting the review
# ---------------------------------------------------------------------------
def _sev(comment: dict[str, Any]) -> str:
    sev = str(comment.get("severity", "minor")).lower()
    return sev if sev in SEVERITY_LABEL else "minor"


def post_review(
    repo: str, pr: str, token: str, result: dict[str, Any], valid: dict[str, set[int]]
) -> None:
    summary = str(result.get("summary", "")).strip() or "_No summary provided._"
    raw_comments = result.get("comments") or []

    inline: list[dict[str, Any]] = []
    demoted: list[str] = []
    for c in raw_comments:
        path, line = c.get("path"), c.get("line")
        label = SEVERITY_LABEL[_sev(c)]
        body = f"**{label}** — {str(c.get('body', '')).strip()}"
        if isinstance(line, int) and line in valid.get(path, set()):
            inline.append({"path": path, "line": line, "side": "RIGHT", "body": body})
        else:  # keep the finding, just can't anchor it to the diff
            demoted.append(f"- **{path}:{line}** {label} — {str(c.get('body', '')).strip()}")

    counts = {s: 0 for s in SEVERITY_ORDER}
    for c in raw_comments:
        counts[_sev(c)] += 1
    tally = ", ".join(f"{SEVERITY_LABEL[s]}: {counts[s]}" for s in SEVERITY_ORDER if counts[s])
    body_parts = ["## 🤖 Codex review", summary]
    if tally:
        body_parts.append(f"**Findings:** {tally}")
    if demoted:
        body_parts.append("### Additional findings (outside the diff range)\n" + "\n".join(demoted))
    review_body = "\n\n".join(body_parts)

    try:
        _gh_request(
            "POST",
            f"/repos/{repo}/pulls/{pr}/reviews",
            token,
            accept="application/vnd.github+json",
            body={"event": "COMMENT", "body": review_body, "comments": inline},
        )
        print(f"ai_review: posted review with {len(inline)} inline comment(s).")
    except urllib.error.HTTPError as exc:
        # Fall back to a plain summary comment so findings are never lost.
        detail = exc.read().decode(errors="replace")[:500]
        print(f"ai_review: inline review rejected ({exc.code}: {detail}); posting summary only.")
        fallback = review_body
        if inline:
            fallback += "\n\n### Inline findings\n" + "\n".join(
                f"- **{c['path']}:{c['line']}** {c['body']}" for c in inline
            )
        _gh_request(
            "POST",
            f"/repos/{repo}/issues/{pr}/comments",
            token,
            accept="application/vnd.github+json",
            body={"body": fallback},
        )


def main() -> int:
    repo = _env("GITHUB_REPOSITORY")
    pr = _env("PR_NUMBER")
    token = _env("GITHUB_TOKEN")

    files = get_pr_files(repo, pr, token)
    if not files:
        print("ai_review: no changed files; nothing to review.")
        return 0

    diff_blob, valid = build_diff_blob(files)
    if not diff_blob.strip():
        print("ai_review: no textual diff to review.")
        return 0

    result = call_model(diff_blob)
    post_review(repo, pr, token, result, valid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
