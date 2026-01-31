import os
import tempfile
import unittest
from datetime import date

from oma.storage import db
from oma.models import DegreeLevel, Status
from oma.storage.paths import app_data_dir


class StorageBaggageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["APPDATA"] = self.temp_dir.name
        self.conn = db.connect()
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_baggage_paid_only_once(self):
        student = db.StudentRow(
            student_id="S1",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 1, 1),
            status=Status.GRADUATED,
            graduation_date=date(2024, 6, 1),
            withdrawal_date=None,
        )
        db.upsert_student(self.conn, student)
        run = db.create_run(self.conn, 1, "2024-07", "7.10")
        db.record_baggage_paid(self.conn, student.student_id, run.run_id, "2024-07")
        db.record_baggage_paid(self.conn, student.student_id, run.run_id, "2024-07")
        cur = self.conn.execute("SELECT COUNT(*) AS cnt FROM baggage_payments WHERE student_id = ?", (student.student_id,))
        self.assertEqual(cur.fetchone()["cnt"], 1)


if __name__ == "__main__":
    unittest.main()
