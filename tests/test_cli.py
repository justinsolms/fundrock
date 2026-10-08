import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from fundrock.__main__ import main
from fundrock.nav_report_manager import UpdateResult


class CliTest(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        patcher = patch("fundrock.__main__.configure_logging")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("fundrock.__main__.NAVReportFileManager")
        self.manager = patcher.start().return_value
        self.manager.db_connection_string = "sqlite:///x.db"
        self.addCleanup(patcher.stop)

    def test_version_and_help(self):
        for flag in ("-v", "--version"):
            result = self.runner.invoke(main, [flag])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("fundrock", result.output)
        for flag in ("-h", "--help"):
            result = self.runner.invoke(main, [flag])
            self.assertEqual(result.exit_code, 0)
            for name in ("set-up", "tear-down", "update"):
                self.assertIn(name, result.output)

    def test_set_up(self):
        self.assertEqual(self.runner.invoke(main, ["set-up"]).exit_code, 0)
        self.manager.set_up.assert_called_once()
        self.manager.update.assert_not_called()

    def test_set_up_refuses_existing(self):
        self.manager.set_up.side_effect = FileExistsError("exists; use tear_down()")
        result = self.runner.invoke(main, ["set-up"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("exists", result.output)

    def test_tear_down_requires_phrase(self):
        result = self.runner.invoke(main, ["tear-down"], input="no\n")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("WARNING", result.output)
        self.manager.tear_down.assert_not_called()

        result = self.runner.invoke(main, ["tear-down"], input="please proceed\n")
        self.assertEqual(result.exit_code, 0)
        self.manager.tear_down.assert_called_once()

    def test_tear_down_yes_skips_prompt(self):
        self.assertEqual(self.runner.invoke(main, ["tear-down", "--yes"]).exit_code, 0)
        self.manager.tear_down.assert_called_once()

    def test_update_summary_and_failure_exit_code(self):
        self.manager.update.return_value = UpdateResult(added=[Path("a")])
        result = self.runner.invoke(main, ["update"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Added 1", result.output)

        self.manager.update.return_value = UpdateResult(failed=[Path("bad")])
        self.assertEqual(self.runner.invoke(main, ["update"]).exit_code, 1)

        self.manager.update.side_effect = FileNotFoundError("no db")
        self.assertEqual(self.runner.invoke(main, ["update"]).exit_code, 1)
