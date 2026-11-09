"""Tests for independent GitHub workflow provenance snapshot validation."""
import json
import unittest

from provenance_validator import validate_provenance


def fixture():
    body = {
        "schema_version": 1,
        "correlation_id": "freshprov_20261109",
        "operation": "self_test",
        "requested_at": "2026-11-09T03:33:00Z",
    }
    comment_body = (
        "## One AI Cloud Runner\n\n"
        "**Operation:** self_test\n"
        "**Correlation ID:** `freshprov_20261109`\n"
        "**Workflow run:** https://github.com/Ahmamaher/rdp/actions/runs/42557086084\n"
        "**Run ID / attempt:** `42557086084` / `1`\n"
    )
    return {
        "repository_full_name": "Ahmamaher/rdp",
        "issue": {
            "number": 24,
            "title": "[ONEAI-RUN] fresh provenance validation fixture",
            "user": {"login": "Ahmamaher"},
            "body": json.dumps(body),
            "created_at": "2026-11-09T03:33:48Z",
        },
        "comment": {
            "user": {"login": "github-actions[bot]"},
            "issue_url": "https://api.github.com/repos/Ahmamaher/rdp/issues/24",
            "created_at": "2026-11-09T03:33:56Z",
            "body": comment_body,
        },
        "run": {
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
        },
        "jobs": [{
            "name": "run-allowlisted-task",
            "status": "completed",
            "conclusion": "success",
            "steps": [
                {"name": "Checkout runner source", "status": "completed", "conclusion": "success"},
                {"name": "Run runner unit tests", "status": "completed", "conclusion": "success"},
                {"name": "Check runner syntax", "status": "completed", "conclusion": "success"},
                {"name": "Execute fixed operation", "status": "completed", "conclusion": "success"},
            ],
        }],
    }


class ProvenanceValidatorTests(unittest.TestCase):
    def validate(self, data):
        return validate_provenance(**data)

    def test_accepts_independently_fetched_positive_fixture(self):
        self.assertEqual(self.validate(fixture())["status"], "verified")

    def test_rejects_stale_request(self):
        data = fixture()
        payload = json.loads(data["issue"]["body"])
        payload["requested_at"] = "2026-11-09T03:00:00Z"
        data["issue"]["body"] = json.dumps(payload)
        result = self.validate(data)
        self.assertFalse(result["checks"].get("freshness", True))
        self.assertEqual(result["status"], "rejected")

    def test_rejects_wrong_repository(self):
        data = fixture()
        data["run"]["repository"]["full_name"] = "someone-else/rdp"
        self.assertEqual(self.validate(data)["status"], "rejected")

    def test_rejects_wrong_workflow_identity(self):
        data = fixture()
        data["run"]["path"] = ".github/workflows/other.yml"
        self.assertEqual(self.validate(data)["status"], "rejected")

    def test_rejects_failed_expected_job(self):
        data = fixture()
        data["jobs"][0]["conclusion"] = "failure"
        self.assertEqual(self.validate(data)["status"], "rejected")

    def test_rejects_missing_or_failed_runner_step(self):
        data = fixture()
        data["jobs"][0]["steps"][2]["conclusion"] = "failure"
        self.assertEqual(self.validate(data)["status"], "rejected")

    def test_rejects_comment_correlation_mismatch(self):
        data = fixture()
        data["comment"]["body"] = data["comment"]["body"].replace("freshprov_20261109", "otherprov_20261109")
        self.assertEqual(self.validate(data)["status"], "rejected")

    def test_rejects_noncanonical_run_url(self):
        data = fixture()
        data["comment"]["body"] = data["comment"]["body"].replace(
            "https://github.com/Ahmamaher/rdp/actions/runs/42557086084",
            "https://example.com/Ahmamaher/rdp/actions/runs/42557086084",
        )
        self.assertEqual(self.validate(data)["status"], "rejected")

    def test_rejects_comment_after_workflow_completion(self):
        data = fixture()
        data["comment"]["created_at"] = "2026-11-09T03:34:10Z"
        self.assertEqual(self.validate(data)["status"], "rejected")


if __name__ == "__main__":
    unittest.main(verbosity=2)
