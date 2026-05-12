import sqlite3
import tempfile
import unittest
from pathlib import Path

from services import db as db_service
from services import payment_workflow
from services import runtime_settings


class PhotoHashSubmissionStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_vpn_bot.db"
        self.original_db_paths = {
            db_service: db_service.DB_PATH,
            payment_workflow: payment_workflow.DB_PATH,
            runtime_settings: runtime_settings.DB_PATH,
        }
        for module, original_path in self.original_db_paths.items():
            setattr(module, "DB_PATH", str(self.db_path))
        db_service.create_tables()

    def tearDown(self):
        for module, original_path in self.original_db_paths.items():
            setattr(module, "DB_PATH", original_path)
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def insert_transaction(self, *, photo_hash, status, user_id=1):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO transactions (user_id, status, photo_id, photo_path, photo_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, status, f"photo-{status}", f"/tmp/{status}.jpg", photo_hash),
            )
            conn.commit()

    def test_photo_hash_state_prefers_approved_over_other_statuses(self):
        shared_hash = "hash-approved-priority"

        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_REJECTED)
        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_PENDING_ADMIN)
        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_ACCOUNTING_APPROVED)

        result = payment_workflow.get_photo_hash_submission_state(shared_hash)

        self.assertIsNotNone(result)
        self.assertEqual(result["result"], "approved")
        self.assertEqual(result["transaction"]["status"], payment_workflow.STATUS_ACCOUNTING_APPROVED)

    def test_photo_hash_state_marks_pending_review_as_in_progress(self):
        shared_hash = "hash-in-progress"

        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_DRAFT)
        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_PENDING_ADMIN)

        result = payment_workflow.get_photo_hash_submission_state(shared_hash)

        self.assertIsNotNone(result)
        self.assertEqual(result["result"], "in_progress")
        self.assertEqual(result["transaction"]["status"], payment_workflow.STATUS_PENDING_ADMIN)

    def test_photo_hash_state_allows_retry_when_only_rejected_statuses_exist(self):
        shared_hash = "hash-retryable"

        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_REJECTED)
        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_ACCOUNTING_REJECTED)

        result = payment_workflow.get_photo_hash_submission_state(shared_hash)

        self.assertIsNotNone(result)
        self.assertEqual(result["result"], "retryable")

    def test_photo_hash_state_ignores_incomplete_drafts(self):
        shared_hash = "hash-draft-only"

        self.insert_transaction(photo_hash=shared_hash, status=payment_workflow.STATUS_DRAFT)

        result = payment_workflow.get_photo_hash_submission_state(shared_hash)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
