from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import services.db as db
import services.payment_workflow as payment_workflow


class PaymentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self.temp_dir.name) / "test_bot.db")
        self._original_db_paths = (
            db.DB_PATH,
            payment_workflow.DB_PATH,
        )
        db.DB_PATH = self.db_path
        payment_workflow.DB_PATH = self.db_path
        db.create_tables()
        self._seed_users()

    def tearDown(self):
        db.DB_PATH, payment_workflow.DB_PATH = self._original_db_paths
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _seed_users(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO users (id, first_name, username, role, created_at, balance)
                VALUES (?, ?, ?, 'user', '2026-04-23 10:00', 0)
                """,
                [
                    (1001, "Ali", "ali"),
                    (1002, "Sara", "sara"),
                    (1003, "Nima", "nima"),
                ],
            )
            conn.commit()

    def _create_submitted_transaction(
        self,
        *,
        user_id: int,
        photo_hash: str,
        amount: int,
        transfer_date: str,
        transfer_time: str,
        source_last4: str | None = None,
        destination_card: str = "6037123412341234",
    ) -> int:
        txn_id = payment_workflow.create_transaction_draft(
            user_id=user_id,
            photo_id=f"photo-{user_id}-{photo_hash}-{amount}-{transfer_time}",
            photo_path=f"transactions/{user_id}/{photo_hash}.jpg",
            photo_hash=photo_hash,
        )
        self.assertTrue(payment_workflow.set_claimed_amount(txn_id, user_id, amount))
        self.assertTrue(payment_workflow.set_destination_card_manual(txn_id, user_id, destination_card))
        self.assertTrue(payment_workflow.set_transfer_date(txn_id, user_id, transfer_date))
        self.assertTrue(payment_workflow.set_transfer_time(txn_id, user_id, transfer_time))
        if source_last4 is not None:
            self.assertTrue(payment_workflow.set_source_card_last4(txn_id, user_id, source_last4))
        submitted = payment_workflow.submit_transaction_for_review(txn_id, user_id)
        self.assertIsNotNone(submitted)
        return txn_id

    def test_format_card_number_for_display_keeps_group_order(self):
        formatted = payment_workflow.format_card_number_for_display("6037123412341234")
        cleaned = formatted.replace("\u202A", "").replace("\u202C", "").replace("\u200E", "")
        self.assertEqual(cleaned, "6037-1234-1234-1234")

    def test_same_photo_hash_marks_transaction_as_suspect(self):
        self._create_submitted_transaction(
            user_id=1001,
            photo_hash="hash-shared",
            amount=200_000,
            transfer_date="1405/02/01",
            transfer_time="10:00",
        )
        txn_id = self._create_submitted_transaction(
            user_id=1002,
            photo_hash="hash-shared",
            amount=350_000,
            transfer_date="1405/02/02",
            transfer_time="12:30",
        )

        txn = payment_workflow.get_transaction(txn_id)
        self.assertEqual(int(txn["is_duplicate_suspect"] or 0), 1)
        self.assertIn("same_photo", txn["duplicate_flags"])

        candidates = payment_workflow.get_duplicate_candidates(txn_id)
        self.assertTrue(any("same_photo" in item.get("reasons", []) for item in candidates))

    def test_same_amount_and_exact_datetime_marks_transaction_as_suspect(self):
        self._create_submitted_transaction(
            user_id=1001,
            photo_hash="hash-a",
            amount=400_000,
            transfer_date="1405/02/01",
            transfer_time="14:37",
            source_last4="1111",
        )
        txn_id = self._create_submitted_transaction(
            user_id=1002,
            photo_hash="hash-b",
            amount=400_000,
            transfer_date="1405/02/01",
            transfer_time="14:37",
        )

        txn = payment_workflow.get_transaction(txn_id)
        self.assertIn("same_amount_transfer_datetime", txn["duplicate_flags"])
        self.assertNotIn("exact_amount_datetime_source_last4", txn["duplicate_flags"])

    def test_same_user_same_day_same_last4_is_not_suspect_when_far_apart(self):
        self._create_submitted_transaction(
            user_id=1001,
            photo_hash="hash-c",
            amount=500_000,
            transfer_date="1405/02/03",
            transfer_time="09:10",
            source_last4="2222",
        )
        txn_id = self._create_submitted_transaction(
            user_id=1001,
            photo_hash="hash-d",
            amount=650_000,
            transfer_date="1405/02/03",
            transfer_time="18:45",
            source_last4="2222",
        )

        txn = payment_workflow.get_transaction(txn_id)
        self.assertFalse(txn["duplicate_flags"])
        self.assertEqual(int(txn["is_duplicate_suspect"] or 0), 0)
        self.assertEqual(payment_workflow.get_duplicate_candidates(txn_id), [])

    def test_same_user_same_last4_within_one_minute_is_suspect(self):
        self._create_submitted_transaction(
            user_id=1001,
            photo_hash="hash-c2",
            amount=510_000,
            transfer_date="1405/02/03",
            transfer_time="09:10",
            source_last4="2222",
        )
        txn_id = self._create_submitted_transaction(
            user_id=1001,
            photo_hash="hash-d2",
            amount=650_000,
            transfer_date="1405/02/03",
            transfer_time="09:11",
            source_last4="2222",
        )

        txn = payment_workflow.get_transaction(txn_id)
        self.assertIn("same_user_source_last4_within_one_minute", txn["duplicate_flags"])
        self.assertNotIn("exact_amount_datetime_source_last4", txn["duplicate_flags"])

    def test_same_amount_datetime_and_last4_marks_very_high_suspicion(self):
        self._create_submitted_transaction(
            user_id=1001,
            photo_hash="hash-e",
            amount=600_000,
            transfer_date="1405/02/04",
            transfer_time="11:11",
            source_last4="3333",
        )
        txn_id = self._create_submitted_transaction(
            user_id=1002,
            photo_hash="hash-f",
            amount=600_000,
            transfer_date="1405/02/04",
            transfer_time="11:11",
            source_last4="3333",
        )

        txn = payment_workflow.get_transaction(txn_id)
        self.assertIn("exact_amount_datetime_source_last4", txn["duplicate_flags"])
        self.assertIn("same_amount_transfer_datetime", txn["duplicate_flags"])

    def test_direct_approval_confirms_accounting_immediately(self):
        txn_id = self._create_submitted_transaction(
            user_id=1003,
            photo_hash="hash-g",
            amount=700_000,
            transfer_date="1405/02/05",
            transfer_time="16:20",
            source_last4="4444",
        )

        approved = payment_workflow.approve_transaction_with_accounting(
            txn_id=txn_id,
            reviewer_id=9001,
            amount=700_000,
            accounting_note="approved in one step",
        )

        self.assertIsNotNone(approved)
        self.assertEqual(approved["status"], payment_workflow.STATUS_ACCOUNTING_APPROVED)
        self.assertEqual(int(approved["amount"] or 0), 700_000)
        self.assertIsNotNone(approved["accounting_reviewed_at"])
        self.assertEqual(approved["accounting_reviewed_by"], 9001)

        with self._connect() as conn:
            row = conn.execute("SELECT balance FROM users WHERE id = 1003").fetchone()
        self.assertEqual(int(row["balance"] or 0), 700_000)
        self.assertEqual(
            payment_workflow.list_transactions_by_status(payment_workflow.STATUS_APPROVED_PENDING_ACCOUNTING),
            [],
        )


if __name__ == "__main__":
    unittest.main()
