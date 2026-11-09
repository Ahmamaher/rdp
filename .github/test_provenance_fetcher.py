"""Mocked tests for the fixed-origin, read-only provenance fetcher."""
import json
import os
import unittest
from unittest.mock import patch

from provenance_fetcher import (
    MAX_RESPONSE_BYTES, SnapshotFetchError, _get_json, fetch_provenance,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        return self.payload[:size]


def api_fixture():
    issue = {
        "number": 24,
        "title": "[ONEAI-RUN] fresh provenance validation fixture",
        "user": {"login": "Ahmamaher"},
        "body": json.dumps({
            "schema_version": 1,
            "correlation_id": "freshprov_20261109",
            "operation": "self_test",
            "requested_at": "2026-11-09T03:33:00Z",
        }),
        "created_at": "2026-11-09T03:33:48Z",
    }
    comment = {
        "id": 6731589908,
        "html_url": "https://github.com/Ahmamaher/rdp/issues/24#issuecomment-6731589908",
        "user": {"login": "github-actions[bot]"},
        "issue_url": "https://api.github.com/repos/Ahmamaher/rdp/issues/24",
        "created_at": "2026-11-09T03:33:56Z",
        "body": (
            "**Operation:** self_test\n"
            "**Correlation ID:** `freshprov_20261109`\n"
            "**Workflow run:** https://github.com/Ahmamaher/rdp/actions/runs/42557086084\n"
            "**Run ID / attempt:** `42557086084` / `1`\n"
        ),
    }
    run = {
        "id": 42557086084,
        "repository": {"full_name": "Ahmamaher/rdp"},
        "path": ".github/workflows/oneai-safe-runner.yml",
        "workflow_id": 411544924,
        "event": "issues",
        "status": "completed",
        "conclusion": "success",
        "actor": {"login": "Ahmamaher"},
        "triggering_actor": {"login": "Ahmamaher"},
        "run_attempt": 1,
        "run_started_at": "2026-11-09T03:33:51Z",
        "updated_at": "2026-11-09T03:34:01Z",
    }
    jobs = {"total_count": 1, "jobs": [{
        "name": "run-allowlisted-task",
        "status": "completed",
        "conclusion": "success",
        "steps": [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in (
                "Checkout runner source", "Run runner unit tests",
                "Check runner syntax", "Execute fixed operation",
            )
        ],
    }]}
    return [issue, comment, run, jobs]


class ProvenanceFetcherTests(unittest.TestCase):
    def test_fetches_four_fixed_read_only_endpoints_and_verifies(self):
        payloads = [json.dumps(item).encode() for item in api_fixture()]
        urls = []
        def fake_urlopen(request, timeout):
            urls.append(request.full_url)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(timeout, 10)
            return FakeResponse(payloads.pop(0))
        with patch("provenance_fetcher.urlopen", side_effect=fake_urlopen):
            result = fetch_provenance(issue_number=24, comment_id=6731589908, run_id=42557086084)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(len(urls), 4)
        self.assertTrue(all(url.startswith("https://api.github.com/repos/Ahmamaher/rdp/") for url in urls))

    def test_network_error_maps_to_pending(self):
        with patch("provenance_fetcher.urlopen", side_effect=OSError("private detail")):
            result = fetch_provenance(issue_number=24, comment_id=6731589908, run_id=42557086084)
        self.assertEqual(result["status"], "pending_verification")
        self.assertEqual(result["reasons"], ["network_unavailable"])
        self.assertNotIn("private detail", str(result))

    def test_rate_limit_maps_to_pending(self):
        from urllib.error import HTTPError
        error = HTTPError("https://api.github.com", 429, "rate limited", {}, None)
        with patch("provenance_fetcher.urlopen", side_effect=error):
            result = fetch_provenance(issue_number=24, comment_id=6731589908, run_id=42557086084)
        self.assertEqual(result["status"], "pending_verification")
        self.assertEqual(result["reasons"], ["transient_http_429"])

    def test_oversized_response_rejected_as_pending(self):
        with patch("provenance_fetcher.urlopen", return_value=FakeResponse(b"x" * (MAX_RESPONSE_BYTES + 1))):
            with self.assertRaises(SnapshotFetchError) as caught:
                _get_json("/issues/24")
        self.assertEqual(caught.exception.category, "response_too_large")

    def test_invalid_identifiers_never_make_network_call(self):
        with patch("provenance_fetcher.urlopen") as mocked:
            result = fetch_provenance(issue_number="../24", comment_id=6731589908, run_id=42557086084)
        mocked.assert_not_called()
        self.assertEqual(result["status"], "rejected")

    def test_token_is_never_returned_or_logged(self):
        payloads = [json.dumps(item).encode() for item in api_fixture()]
        seen_headers = []
        def fake_urlopen(request, timeout):
            seen_headers.append(request.get_header("Authorization"))
            return FakeResponse(payloads.pop(0))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "DO_NOT_LEAK_THIS"}):
            with patch("provenance_fetcher.urlopen", side_effect=fake_urlopen):
                result = fetch_provenance(issue_number=24, comment_id=6731589908, run_id=42557086084)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(all(value == "Bearer DO_NOT_LEAK_THIS" for value in seen_headers))
        self.assertNotIn("DO_NOT_LEAK_THIS", str(result))


if __ (unittest.main(verbosity=2)):
    pass
