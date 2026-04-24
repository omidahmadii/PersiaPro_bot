from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jdatetime

import services.db as db
import services.runtime_settings as runtime_settings
import services.scheduler_services.notifier as notifier


class ExpiryOfferNotifierTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self.temp_dir.name) / "test_bot.db")
        self.fixed_now = jdatetime.datetime(1405, 2, 3, 12, 0)

        self._original_db_paths = (
            db.DB_PATH,
            runtime_settings.DB_PATH,
        )
        db.DB_PATH = self.db_path
        runtime_settings.DB_PATH = self.db_path

        db.create_tables()
        self._seed_base_data()
        self._configure_offer_settings()

    def tearDown(self):
        db.DB_PATH, runtime_settings.DB_PATH = self._original_db_paths
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _seed_base_data(self):
        created_at = "2026-04-21 10:00"
        in_5_days = (self.fixed_now + jdatetime.timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
        in_8_days = (self.fixed_now + jdatetime.timedelta(days=8)).strftime("%Y-%m-%d %H:%M")
        in_15_days = (self.fixed_now + jdatetime.timedelta(days=15)).strftime("%Y-%m-%d %H:%M")

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (id, first_name, username, role, created_at, message_name)
                VALUES (1001, 'Test', 'tester', 'user', ?, 'کاربر تست')
                """,
                (created_at,),
            )
            cursor.executemany(
                """
                INSERT INTO plans (id, name, volume_gb, duration_days, price, group_name, is_archived)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                [
                    (1, "پلن فعلی", 20, 30, 100000, "STD-30"),
                    (27, "پلن پیشنهادی", 40, 30, 180000, "PRO-30"),
                ],
            )
            cursor.executemany(
                """
                INSERT INTO orders (
                    id,
                    user_id,
                    plan_id,
                    username,
                    status,
                    price,
                    created_at,
                    expires_at,
                    last_notif_level
                )
                VALUES (?, ?, ?, ?, 'active', 0, ?, ?, 0)
                """,
                [
                    (1, 1001, 1, "need-offer", created_at, in_5_days),
                    (2, 1001, 27, "already-target", created_at, in_8_days),
                    (3, 1001, 1, "too-early", created_at, in_15_days),
                ],
            )
            conn.commit()

    def _configure_offer_settings(self):
        runtime_settings.set_setting("renewal_offer_notification_enabled", "1", value_type="bool")
        runtime_settings.set_setting("renewal_offer_target_plan_id", "27", value_type="integer")
        runtime_settings.set_setting("renewal_offer_days_threshold", "10", value_type="integer")

    def test_sends_expiry_offer_only_once_for_eligible_order(self):
        sent_payloads = []

        def fake_send(*args, **kwargs):
            sent_payloads.append(kwargs)
            return True

        with patch.object(notifier, "get_current_jdatetime", return_value=self.fixed_now), patch.object(
            notifier,
            "send_scheduler_notification",
            side_effect=fake_send,
        ):
            notifier.notifier()
            notifier.notifier()

        self.assertEqual(len(sent_payloads), 1)
        self.assertEqual(sent_payloads[0]["chat_id"], 1001)
        self.assertIn("پلن پیشنهادی", sent_payloads[0]["text"])

        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_renewal_offer_notification_at FROM orders WHERE id = 1"
            ).fetchone()
        self.assertTrue(str(row["last_renewal_offer_notification_at"] or "").strip())

    def test_does_not_send_when_target_plan_is_missing(self):
        runtime_settings.set_setting("renewal_offer_target_plan_id", "9999", value_type="integer")

        with patch.object(notifier, "get_current_jdatetime", return_value=self.fixed_now), patch.object(
            notifier,
            "send_scheduler_notification",
            return_value=True,
        ) as mocked_send:
            notifier.notifier()

        self.assertEqual(mocked_send.call_count, 0)


if __name__ == "__main__":
    unittest.main()
