#!/usr/bin/env python3
"""Owner-gated, allow-listed GitHub issue task runner. Standard library only."""
from __future__ import annotations

import ast
import json
import os
import pathlib
import platform
import sys
import urllib.error
import urllib.request

OWNER = "Ahmamaher"
ALLOWED = {"health", "self_test", "code_audit"}


def parse_event(event: dict) -> tuple[int, str]:
    issue = event.get("issue") or {}
    sender = event.get("sender") or {}
    if sender.get("login") != OWNER:
        raise ValueError("Rejected: only the repository owner may trigger tasks.")
    if not str(issue.get("title", "")).startswith("[ONEAI-RUN]"):
        raise ValueError("Rejected: issue title must start with [ONEAI-RUN].")
    raw = issue.get("body") or ""
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != {"operation"}:
        raise ValueError('Body must be JSON with exactly one key: {"operation":"..."}')
    operation = payload["operation"]
    if operation not in ALLOWED:
        raise ValueError(f"Unsupported operation. Allowed: {', '.join(sorted(ALLOWED))}")
    number = issue.get("number")
    if not isinstance(number, int):
        raise ValueError("Missing issue number.")
    return number, operation


def health() -> str:
    return (
        "Health check passed.\n"
        f"- Python: {platform.python_version()}\n"
        f"- OS: {platform.system()} {platform.release()}\n"
        "- Dependencies: Python standard library only\n"
        "- Execution: completed; no persistent worker started"
    )


def self_test() -> str:
    cases = [
        ({"sender": {"login": OWNER}, "issue": {"number": 1, "title": "[ONEAI-RUN] test", "body": '{"operation":"health"}'}}, (1, "health")),
    ]
    for event, expected in cases:
        actual = parse_event(event)
        if actual != expected:
            raise AssertionError(f"Expected {expected}, got {actual}")
    try:
        parse_event({"sender": {"login": "untrusted"}, "issue": {"number": 2, "title": "[ONEAI-RUN]", "body": '{"operation":"health"}'}})
    except ValueError:
        pass
    else:
        raise AssertionError("Unauthorized sender was not rejected")
    try:
        parse_event({"sender": {"login": OWNER}, "issue": {"number": 3, "title": "[ONEAI-RUN]", "body": '{"operation":"arbitrary"}'}})
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown operation was not rejected")
    return "Self-test passed: valid task accepted; unauthorized sender rejected; unknown operation rejected."


def code_audit() -> str:
    root = pathlib.Path(".")
    ignored = {".git", ".venv", "venv", "__pycache__", "node_modules"}
    files = [p for p in root.rglob("*.py") if not any(part in ignored for part in p.parts)]
    errors: list[str] = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    if errors:
        return "Python syntax audit FAILED:\n" + "\n".join(f"- {x}" for x in errors[:30])
    return f"Python syntax audit passed: {len(files)} Python files parsed successfully."


def post_comment(issue_number: int, body: str) -> None:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    data = json.dumps({"body": body[:60000]}).encode()
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "oneai-safe-runner",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"GitHub comment API returned HTTP {response.status}")


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("Missing GitHub event payload.", file=sys.stderr)
        return 2
    try:
        event = json.loads(pathlib.Path(event_path).read_text(encoding="utf-8"))
        issue_number, operation = parse_event(event)
        result = {"health": health, "self_test": self_test, "code_audit": code_audit}[operation]()
        body = f"## One AI Cloud Runner\n\n**Operation:** `{operation}`\n\n{result}\n\n_This was a bounded, stateless GitHub Actions job. It did not access private One AI files or credentials._"
        post_comment(issue_number, body)
        print(body)
        return 0
    except Exception as exc:
        print(f"Runner failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
