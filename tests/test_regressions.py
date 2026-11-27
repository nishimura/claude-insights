import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from verification_commands import is_verification_command


class VerificationCommandsTest(unittest.TestCase):
    def test_command_positions_and_shell_quoting(self):
        cases = {
            "echo '|' pytest": False,
            r"echo \| pytest": False,
            """python -c 'print("pytest")'""": False,
            "python app.py test": False,
            "grep -rn phpunit .": False,
            "cat >pytest": False,
            "cat <<'EOF'\npytest\nEOF": False,
            """echo '<<EOF'\npytest""": True,
            "cat <<A <<B\npytest\nA\nruff\nB": False,
            "echo '|' pytest && python -m pytest": True,
            """bash -lc 'cd project && pytest -q'""": True,
            "npm run " + "\\\n" + "test": True,
            "/usr/bin/php7.3 vendor/bin/phpunit": True,
            "php artisan test": True,
            "timeout 5s cargo test": True,
            "./run-tests.sh": True,
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(is_verification_command(command), expected)


class CollectorTest(unittest.TestCase):
    def test_packet_and_aggregate_share_latest_branch(self):
        session_id = "12345678-1234-1234-1234-123456789abc"

        def entry(uid, parent, minute, kind, content, **fields):
            return {
                "uuid": uid,
                "parentUuid": parent,
                "timestamp": "2026-01-01T00:%02d:00Z" % minute,
                "type": kind,
                "message": {"content": content},
                "sessionId": session_id,
                "cwd": "/demo",
                **fields,
            }

        def call(tool_id, command):
            return [{"type": "tool_use", "id": tool_id, "name": "Bash",
                     "input": {"command": command}}]

        rows = [
            entry("root", None, 0, "user", "Start"),
            entry("rewound", "root", 1, "assistant", call("old", "phpunit")),
            entry("retry", "root", 2, "user", "New request"),
            entry("compact", None, 3, "system", "", logicalParentUuid="retry"),
            entry("first", "compact", 4, "assistant", call("one", "pytest")),
            entry("second", "compact", 4, "assistant", call("two", "python -c 'print(\"pytest\")'")),
            entry("result", "first", 5, "user",
                  [{"type": "tool_result", "tool_use_id": "one", "content": "1 passed"}]),
            entry("reply", "second", 6, "assistant", "Done"),
            entry("away", "reply", 12, "system", "Away summary"),
        ]
        for row in rows[4:6]:
            row["message"]["id"] = "parallel"

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "projects" / "demo" / (session_id + ".jsonl")
            source.parent.mkdir(parents=True)
            source.write_text("".join(json.dumps(row) + "\n" for row in rows))
            out = base / "out"
            subprocess.run([
                sys.executable, str(ROOT / "bin" / "collect-project-packets.py"),
                "--claude-home", tmp, "--out", str(out), "/demo",
            ], check=True, capture_output=True, text=True)
            aggregate = json.loads((out / "aggregate.json").read_text())
            packet_path, = (out / "packets").glob("*.md")
            packet = packet_path.read_text()

        session, = aggregate["sessions"]
        self.assertEqual(session["verification_count"], 1)
        self.assertEqual(session["verification_success_count"], 1)
        self.assertEqual(session["wall_duration_minutes"], 6)
        self.assertIn("Main verification commands: 1 (success 1", packet)
        self.assertIn("Duration minutes: 6", packet)
        self.assertIn("New request", packet)
        self.assertNotIn("phpunit", packet)
