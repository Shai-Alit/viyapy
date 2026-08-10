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
  the merge. Missing configuration exits non-zero (so setup problems surface
  loudly); a transient model/API error instead posts a short "couldn't complete"
  note and exits zero, so a hiccup doesn't read as a broken required check.
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

The Foundry **v1** API surface is used: ``{endpoint}/openai/v1/responses``
with a ``Bearer`` token and the model named in the request body — no
``api-version`` query string and no ``/deployments/`` path segment. Codex-family
deployments only support the Responses API; ``/chat/completions`` returns HTTP
400 "operation is unsupported" for them.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

GITHUB_API = "https://api.github.com"
# A skip flag in the PR head commit message opts that PR out of review.
SKIP_RE = re.compile(r"\[(skip[- ]review|no[- ]review|skip ai[- ]?review)\]", re.IGNORECASE)
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


def _extract_output_text(data: dict[str, Any]) -> str:
    """Pull the assistant text out of a Responses API payload.

    The Responses API returns an ``output`` list that interleaves reasoning and
    message items; the visible answer lives in ``message`` items as
    ``output_text`` content. Some gateways also surface an aggregated
    ``output_text`` string — prefer it when present.
    """
    aggregated = data.get("output_text")
    if isinstance(aggregated, str) and aggregated.strip():
        return aggregated
    parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for chunk in item.get("content", []):
            if isinstance(chunk, dict) and chunk.get("type") in {"output_text", "text"}:
                text = chunk.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts)


def call_model(diff_blob: str) -> dict[str, Any]:
    endpoint = _env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    model = _env("AZURE_OPENAI_MODEL")
    api_key = _env("AZURE_OPENAI_API_KEY")

    # Codex-family deployments are served by the Responses API — the
    # chat/completions operation is unsupported for them and returns HTTP 400.
    url = f"{endpoint}/openai/v1/responses"
    payload = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": f"Review this pull-request diff:\n\n{diff_blob}",
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reasoning": {"effort": "medium"},
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 (configured host)
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Azure OpenAI call failed ({exc.code}): {detail}") from exc

    content = _extract_output_text(data)
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
    if not isinstance(result, dict):
        result = {}
    summary = str(result.get("summary", "")).strip() or "_No summary provided._"
    raw = result.get("comments")
    raw_comments = raw if isinstance(raw, list) else []

    inline: list[dict[str, Any]] = []
    demoted: list[str] = []
    counts = {s: 0 for s in SEVERITY_ORDER}
    for c in raw_comments:
        if not isinstance(c, dict):  # a malformed entry must not crash the review
            continue
        sev = _sev(c)
        counts[sev] += 1
        label = SEVERITY_LABEL[sev]
        text = str(c.get("body", "")).strip()
        path, line = c.get("path"), c.get("line")
        # bool is an int subclass — exclude it so True/False can't pose as a line.
        anchorable = (
            isinstance(path, str)
            and isinstance(line, int)
            and not isinstance(line, bool)
            and line in valid.get(path, set())
        )
        if anchorable:
            inline.append(
                {"path": path, "line": line, "side": "RIGHT", "body": f"**{label}** — {text}"}
            )
        else:  # keep the finding, just can't anchor it to the diff
            demoted.append(f"- **{path}:{line}** {label} — {text}")

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


def head_commit_has_skip_flag(repo: str, pr: str, token: str) -> bool:
    """Return True when the PR head commit message carries a skip flag.

    Read via the API (not ``git log``) so the flag is taken from the real head
    commit rather than a synthetic merge commit, and so this works without
    checking out the pull-request branch.
    """
    try:
        pull = _gh_request(
            "GET", f"/repos/{repo}/pulls/{pr}", token, accept="application/vnd.github+json"
        )
        head_sha = pull["head"]["sha"]
        commit = _gh_request(
            "GET", f"/repos/{repo}/commits/{head_sha}", token, accept="application/vnd.github+json"
        )
        message = commit["commit"]["message"]
    except (urllib.error.URLError, KeyError, TypeError) as exc:
        print(f"ai_review: could not read head commit message ({exc}); not skipping.")
        return False
    return bool(SKIP_RE.search(str(message)))


def post_failure_note(repo: str, pr: str, token: str, exc: Exception) -> None:
    """Leave a short, non-blocking note when the model call could not complete."""
    print(f"ai_review: model call failed: {exc}", file=sys.stderr)
    body = (
        "## 🤖 Codex review\n\n"
        f"⚠️ The AI reviewer couldn't complete this run (`{type(exc).__name__}`). "
        "This is non-blocking — re-run the job to retry."
    )
    try:
        _gh_request(
            "POST",
            f"/repos/{repo}/issues/{pr}/comments",
            token,
            accept="application/vnd.github+json",
            body={"body": body},
        )
    except urllib.error.URLError as post_exc:
        print(f"ai_review: also failed to post the failure note: {post_exc}", file=sys.stderr)


def main() -> int:
    repo = _env("GITHUB_REPOSITORY")
    pr = _env("PR_NUMBER")
    token = _env("GITHUB_TOKEN")

    if head_commit_has_skip_flag(repo, pr, token):
        print("ai_review: skip flag found in the head commit message; skipping review.")
        return 0

    files = get_pr_files(repo, pr, token)
    if not files:
        print("ai_review: no changed files; nothing to review.")
        return 0

    diff_blob, valid = build_diff_blob(files)
    if not diff_blob.strip():
        print("ai_review: no textual diff to review.")
        return 0

    try:
        result = call_model(diff_blob)
    except (
        urllib.error.URLError,  # includes HTTPError (subclass) and timeouts
        RuntimeError,
        KeyError,
        IndexError,
        ValueError,  # includes json.JSONDecodeError
        TimeoutError,
    ) as exc:
        post_failure_note(repo, pr, token, exc)
        return 0

    post_review(repo, pr, token, result, valid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
