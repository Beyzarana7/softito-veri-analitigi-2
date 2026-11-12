"""Yerel yapılandırma ve kilitli dönem yükleme sınırı testleri."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kod.db.engine import create_db_engine,ConfigurationError
from kod.db.results import prepare_result_rows

PROJECT=Path(__file__).resolve().parents[2]


class DatabaseUnitTests(unittest.TestCase):
    def test_missing_env_is_explicit_and_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ConfigurationError):create_db_engine(Path(folder))

    def test_missing_keys_show_only_key_names(self):
        with tempfile.TemporaryDirectory() as folder:
            env=Path(folder)/'.env'
            env.write_text('DB_NAME=wattrota\n',encoding='utf-8')
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
                with self.assertRaises(ConfigurationError) as error:create_db_engine(Path(folder))
            self.assertIn('DB_PASSWORD',str(error.exception))
            self.assertEqual(stream.getvalue(),'')

    def test_result_rows_are_development_only(self):
        batches,_=prepare_result_rows(PROJECT)
        counts={table.name:len(rows) for table,rows in batches}
        self.assertEqual(counts,{'weekly_decision_metrics':136,'method_summaries':4,'net_savings':137})
        self.assertTrue(all(row['decision_origin'].year==2026 and row['decision_origin'].month<=8 for row in batches[0][1]))


if __name__=='__main__':unittest.main()
