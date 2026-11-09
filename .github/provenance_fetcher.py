"""Read-only, fixed-origin GitHub snapshot fetcher for One AI provenance.

Accepts numeric identifiers only (never caller-provided URLs), uses only the
fixed api.github.com repository, caps response size/timeouts, and never logs
or returns authorization headers. Temporary failures map to pending.
"""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from provenance_validator import validate_provenance

REPOSITORY = "Ahmamaher/rdp"
API_ROOT = "https://api.github.com/repos/" + REPOSITORY
MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT_SECONDS = 10
IDENTIFIER_RE = re.compile(r"[1-9][0-9]{0,19}\Z")
TRANSIENT_HTTP = {403, 408, 425, 429, 500, 502, 503, 504}


class SnapshotFetchError(Exception):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


def _identifier(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid_" + name)
    text = str(value)
    if not IDENTIFIER_RE.fullmatch(text):
        raise ValueError("invalid_" + name)
    return int(text)


def _get_json(path: str) -> dict | list:
    # Exact endpoint allow-list: no arbitrary paths, hosts, or query strings.
    allowed_path = re.fullmatch(
        r"/(?:issues/[1-9][0-9]{0,19}|issues/comments/[1-9][0-9]{0,19}|"
        r"actions/runs/[1-9][0-9]{0,19}|actions/runs/[1-9][0-9]{0,19}/jobs\\?per_page=100)",
        path,
    )
    if not allowed_path:
        raise ValueError("invalid_fixed_api_path")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OneAI-Provenance-ReadOnly/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(API_ROOT + path, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code in TRANSIENT_HTTP:
            raise SnapshotFetchError("transient_http_" + str(exc.code)) from None
        if exc.code in {401, 404}:
            raise SnapshotFetchError("unavailable_or_unauthorized") from None
        raise SnapshotFetchError("http_error") from None
    except (URLError, TimeoutError, OSError):
        raise SnapshotFetchError("network_unavailable") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SnapshotFetchError("response_too_large")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SnapshotFetchError("invalid_api_response") from None
    if not isinstance(parsed, (dict, list)):
        raise SnapshotFetchError("invalid_api_response_shape")
    return parsed


def fetch_provenance(*, issue_number: int, comment_id: int, run_id: int) -> dict:
    """Fetch four fixed GitHub API resources and validate their snapshots."""
    try:
        issue_number = _identifier(issue_number, "issue_number")
        comment_id = _identifier(comment_id, "comment_id")
        run_id = _identifier(run_id, "run_id")
        issue = _get_json(f"/issues/{issue_number}")
        comment = _get_json(f"/issues/comments/{comment_id}")
        run = _get_json(f"/actions/runs/{run_id}")
        jobs_payload = _get_json(f"/actions/runs/{run_id}/jobs?per_page=100")
        if not all(isinstance(item, dict) for item in (issue, comment, run)):
            raise SnapshotFetchError("invalid_api_response_shape")
        if not isinstance(jobs_payload, dict) or not isinstance(jobs_payload.get("jobs"), list):
            raise SnapshotFetchError("invalid_jobs_response")
        if jobs_payload.get("total_count", len(jobs_payload["jobs"])) > 100:
            raise SnapshotFetchError("job_page_limit_exceeded")
        if (
            issue.get("number") != issue_number
            or comment.get("id") != comment_id
            or run.get("id") != run_id
        ):
            return {
                "status": "rejected",
                "checks": {"fetched_resource_identity": False},
                "reasons": ["fetched_resource_identifier_mismatch"],
            }
        return validate_provenance(
            repository_full_name=REPOSITORY,
            expected_comment_id=comment_id,
            issue=issue,
            comment=comment,
            run=run,
            jobs=jobs_payload["jobs"],
        )
    except SnapshotFetchError as exc:
        return {"status": "pending_verification", "checks": {}, "reasons": [exc.category]}
    except ValueError as exc:
        return {
            "status": "rejected",
            "checks": {"input_identifiers": False},
            "reasons": [str(exc)],
        }
