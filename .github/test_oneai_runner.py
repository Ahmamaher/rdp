"""Unit tests for the safe cloud runner."""
import unittest
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

if __name__ == "__main__":
    unittest.main(verbosity=2)
