"""Unit tests for the safe cloud runner."""
import unittest
import os
import pathlib
import tempfile
import oneai_runner as runner

class ParseEventTests(unittest.TestCase):
    def event(self, sender="Ahmamaher", title="[ONEAI-RUN] test", body='{"operation":"health"}', number=1):
        return {"sender": {"login": sender}, "issue": {"number": number, "title": title, "body": body}}

    def test_accepts_valid_owner_request(self):
        self.assertEqual(runner.parse_event(self.event()), (1, "health"))

    def test_rejects_non_owner(self):
        with self.assertRaises(ValueError):
            runner.parse_event(self.event(sender="someone-else"))

    def test_rejects_wrong_title_prefix(self):
        with self.assertRaises(ValueError):
            runner.parse_event(self.event(title="run this"))

    def test_rejects_unknown_operation(self):
        with self.assertRaises(ValueError):
            runner.parse_event(self.event(body='{"operation":"shell"}'))

    def test_rejects_extra_payload_keys(self):
        with self.assertRaises(ValueError):
            runner.parse_event(self.event(body='{"operation":"health","command":"whoami"}'))

    def test_rejects_non_string_operation(self):
        with self.assertRaises(ValueError):
            runner.parse_event(self.event(body='{"operation":7}'))

    def test_rejects_invalid_issue_number(self):
        with self.assertRaises(ValueError):
            runner.parse_event(self.event(number=0))

    def test_rejects_invalid_json(self):
        with self.assertRaises(ValueError):
            runner.parse_event(self.event(body="not-json"))

    def test_self_test_executes_all_guard_cases(self):
        self.assertIn("Self-test passed", runner.self_test())

    def test_handlers_do_not_require_third_party_packages(self):
        self.assertIn("standard library only", runner.health())

    def test_diagnostic_findings_fail_the_job(self):
        self.assertTrue(runner.operation_failed("code_audit", "Python syntax audit FAILED:\\n- broken.py"))
        self.assertTrue(runner.operation_failed("repo_integrity", "Potential repository hygiene issue detected"))

    def test_clean_diagnostics_do_not_fail_the_job(self):
        self.assertFalse(runner.operation_failed("code_audit", "Python syntax audit passed: 2 Python files parsed successfully."))
        self.assertFalse(runner.operation_failed("repo_integrity", "Repository integrity scan passed."))
        self.assertFalse(runner.operation_failed("health", "Health check passed."))

    def test_env_examples_are_not_flagged(self):
        for name in (".env.example", ".env.sample", ".env.template"):
            self.assertFalse(runner.is_sensitive_path(pathlib.Path(name)))

    def test_env_variants_and_database_files_are_flagged(self):
        for name in (".env.production", "app.db", "credentials.json", "mcp_bridge.token"):
            self.assertTrue(runner.is_sensitive_path(pathlib.Path(name)))

    def test_integrity_scan_does_not_follow_symlinks(self):
        original = pathlib.Path.cwd()
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.chdir(root)
            try:
                target = pathlib.Path(outside) / "outside.txt"
                target.write_text("SYMLINK_TARGET_CONTENT_MUST_NOT_BE_READ", encoding="utf-8")
                pathlib.Path("linked.txt").symlink_to(target)
                report = runner.repo_integrity()
                self.assertIn("Text files scanned: 0", report)
                self.assertNotIn("SYMLINK_TARGET_CONTENT_MUST_NOT_BE_READ", report)
            finally:
                os.chdir(original)

    def test_integrity_scan_reports_sensitive_paths_without_values(self):
        original = pathlib.Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            try:
                pathlib.Path(".env.production").write_text("EXAMPLE_SECRET_VALUE_DO_NOT_PRINT", encoding="utf-8")
                pathlib.Path("safe.txt").write_text("ordinary text", encoding="utf-8")
                report = runner.repo_integrity()
                self.assertIn(".env.production", report)
                self.assertNotIn("EXAMPLE_SECRET_VALUE_DO_NOT_PRINT", report)
            finally:
                os.chdir(original)

if __name__ == "__main__":
    unittest.main(verbosity=2)
