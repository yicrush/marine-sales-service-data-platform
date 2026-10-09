"""CLI validation/report behavior that does not require a running database."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import Workbook
import psycopg

from etl.pipeline import main
from etl.load.__main__ import main as load_main


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sample.xlsx"
        self.report = Path(self.directory.name) / "report.json"
        book = Workbook()
        sheet = book.active
        sheet.title = "Quotation"
        for coordinate, value in {
            "A1": "REF. NO. KP-M-Q-26-001", "A2": "TO : Sample Customer",
            "B15": "No.", "C15": "Item", "H15": "Qty",
            "I15": "U/PRICE(USD)", "J15": "AMOUNT(USD)",
            "B16": 1, "C16": "Sample part", "H16": 2, "I16": 10, "J16": 20,
            "H18": "TOTAL", "J18": 20,
        }.items():
            sheet[coordinate] = value
        book.save(self.path)
        book.close()

    def args(self, *extra):
        return [str(self.path), "--sheet", "Quotation", "--report", str(self.report), *extra]

    def test_dry_run_never_connects_and_retains_raw_staging(self):
        with redirect_stdout(StringIO()), patch("etl.load.cli.psycopg.connect", side_effect=AssertionError("Dry run connected")):
            self.assertEqual(main(self.args("--dry-run")), 0)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["load"]["accepted"], 1)
        self.assertEqual(report["transformed"]["records"][0]["raw"]["items"][0]["quantity"], 2)
        self.assertEqual(report["transformed"]["records"][0]["quotation"]["document_total_amount"], "20")

    def test_absent_database_binding_has_report_without_connecting(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(StringIO()), patch("etl.load.cli.psycopg.connect", side_effect=AssertionError("No DSN connected")):
            self.assertEqual(main(self.args()), 2)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["status"], "failed")
        self.assertIn("DATABASE_URL", report["error"])

    def test_connection_errors_never_log_dsn_password(self):
        sentinel = "synthetic-do-not-log-password"
        dsn = f"postgresql://synthetic:{sentinel}@invalid.example/test"
        stdout = StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": dsn}), redirect_stdout(stdout), patch("etl.load.cli.psycopg.connect", side_effect=psycopg.OperationalError(dsn)):
            self.assertEqual(main(self.args()), 2)
        self.assertNotIn(sentinel, stdout.getvalue())
        self.assertNotIn(sentinel, self.report.read_text())

    def test_existing_report_and_source_workbook_are_preserved(self):
        original_source = self.path.read_bytes()
        self.report.write_text("Existing report", encoding="utf-8")
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            main(self.args("--dry-run"))
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.report.read_text(), "Existing report")
        self.assertEqual(self.path.read_bytes(), original_source)

    def test_empty_staging_is_a_failed_validation_without_database_access(self):
        source = Path(self.directory.name) / "empty.json"
        source.write_text('{"records": []}')
        with redirect_stdout(StringIO()), patch("etl.load.cli.psycopg.connect", side_effect=AssertionError("Empty batch connected")):
            self.assertEqual(load_main([str(source), "--report", str(self.report), "--dry-run"]), 1)
        self.assertEqual(json.loads(self.report.read_text())["status"], "validation_failed")


if __name__ == "__main__":
    unittest.main()
