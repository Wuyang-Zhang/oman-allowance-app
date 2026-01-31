import os
import tempfile
import unittest


class WebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db = tempfile.NamedTemporaryFile(delete=False)
        cls.temp_db.close()
        os.environ["OMA_DB_PATH"] = cls.temp_db.name

        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            cls.skip_reason = f"fastapi testclient not available: {exc}"
            cls.client = None
            return

        from oma.web.app import app

        cls.client = TestClient(app)
        cls.skip_reason = ""

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp_db", None):
            try:
                os.unlink(cls.temp_db.name)
            except FileNotFoundError:
                pass

    def setUp(self):
        if not self.client:
            self.skipTest(self.skip_reason)
        from oma.web import db
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM allowance_records")
            conn.execute("DELETE FROM baggage_payments")
            conn.execute("DELETE FROM calculation_runs")
            conn.execute("DELETE FROM students")
            conn.commit()
        finally:
            conn.close()

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_import_validation(self):
        csv_content = "foo,bar\n1,2\n"
        resp = self.client.post(
            "/students/import",
            files={"file": ("bad.csv", csv_content, "text/csv")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue("Missing columns" in resp.text or "缺少列" in resp.text)

    def test_october_study_allowance_included(self):
        from oma.web import db
        from oma.web.app import _monthly_records_for_student
        from oma.web.app import _parse_settlement_month
        from oma.config import AllowanceConfig
        from oma.models import DegreeLevel, Status
        from datetime import date

        student = db.WebStudent(
            student_id="S100",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 9, 1),
            graduation_date=None,
            withdrawal_date=None,
            status=Status.IN_STUDY,
        )
        config = AllowanceConfig.default()
        records, _warnings = _monthly_records_for_student(
            student=student,
            settlement_month=_parse_settlement_month("2024-10"),
            config=config,
            pay_baggage=False,
            pay_withdrawal_living=False,
            lang="en_US",
        )
        study = [r for r in records if r.allowance_type.value == "Study"]
        self.assertEqual(len(study), 1)

    def test_baggage_paid_only_once(self):
        from oma.web import db
        from oma.models import DegreeLevel, Status
        from datetime import date

        student = db.WebStudent(
            student_id="S200",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2023, 1, 1),
            graduation_date=date(2024, 6, 30),
            withdrawal_date=None,
            status=Status.GRADUATED,
        )
        conn = db.get_connection()
        try:
            db.upsert_student(conn, student)
        finally:
            conn.close()

        resp = self.client.post(
            "/settlement/run",
            data={"settlement_month": "2024-07", "baggage_pay": student.student_id},
        )
        self.assertEqual(resp.status_code, 303)

        resp = self.client.post(
            "/settlement/run",
            data={"settlement_month": "2024-08", "baggage_pay": student.student_id},
        )
        self.assertEqual(resp.status_code, 303)

        conn = db.get_connection()
        try:
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM allowance_records WHERE allowance_type = ?", ("ExcessBaggage",))
            count = cur.fetchone()["cnt"]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_withdrawal_month_living_toggle(self):
        from oma.web import db
        from oma.models import DegreeLevel, Status
        from datetime import date

        student = db.WebStudent(
            student_id="S300",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2023, 1, 1),
            graduation_date=None,
            withdrawal_date=date(2024, 5, 20),
            status=Status.WITHDRAWN,
        )
        conn = db.get_connection()
        try:
            db.upsert_student(conn, student)
        finally:
            conn.close()

        resp = self.client.post(
            "/settlement/run",
            data={"settlement_month": "2024-05", "withdrawal_living_pay": student.student_id},
        )
        self.assertEqual(resp.status_code, 303)

        conn = db.get_connection()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) AS cnt FROM allowance_records WHERE allowance_type = ?",
                ("Living",),
            )
            count = cur.fetchone()["cnt"]
        finally:
            conn.close()
        self.assertGreaterEqual(count, 1)

    def test_settlement_month_stored(self):
        from oma.web import db
        from oma.models import DegreeLevel, Status
        from datetime import date

        student = db.WebStudent(
            student_id="S400",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2023, 1, 1),
            graduation_date=None,
            withdrawal_date=None,
            status=Status.IN_STUDY,
        )
        conn = db.get_connection()
        try:
            db.upsert_student(conn, student)
        finally:
            conn.close()

        resp = self.client.post(
            "/settlement/run",
            data={"settlement_month": "2024-09"},
        )
        self.assertEqual(resp.status_code, 303)

        conn = db.get_connection()
        try:
            cur = conn.execute("SELECT settlement_month FROM calculation_runs ORDER BY run_id DESC LIMIT 1")
            row = cur.fetchone()
        finally:
            conn.close()
        self.assertEqual(row["settlement_month"], "2024-09")


if __name__ == "__main__":
    unittest.main()
