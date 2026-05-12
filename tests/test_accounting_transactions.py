import unittest
import sys
from types import ModuleType


main_menu_stub = ModuleType("keyboards.main_menu")
main_menu_stub.admin_main_menu_keyboard = lambda: None
sys.modules.setdefault("keyboards.main_menu", main_menu_stub)

from handlers.admin import accounting_transactions


def make_txn(
    txn_id: int,
    *,
    card_number: str,
    amount: int,
    transfer_date: str = "1405/02/22",
    transfer_time: str = "14:35",
    first_name: str = "",
    last_name: str = "",
    username: str = "",
    bank_name: str = "",
    owner_name: str = "",
    duplicate: int = 0,
) -> dict:
    return {
        "id": txn_id,
        "user_id": 100 + txn_id,
        "amount": amount,
        "destination_card_number": card_number,
        "destination_bank_name": bank_name,
        "destination_card_owner": owner_name,
        "transfer_date": transfer_date,
        "transfer_time": transfer_time,
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "is_duplicate_suspect": duplicate,
    }


class AccountingTransactionsUiTests(unittest.TestCase):
    def test_build_accounting_card_groups_aggregates_by_destination_card(self):
        transactions = [
            make_txn(11, card_number="6037123412341234", amount=120_000, bank_name="ملت"),
            make_txn(12, card_number="6037123412341234", amount=180_000, bank_name="ملت"),
            make_txn(13, card_number="5892100011112222", amount=90_000, bank_name="سپه"),
        ]

        groups = accounting_transactions.build_accounting_card_groups(transactions)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["key"], "6037123412341234")
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual(groups[0]["total_amount"], 300_000)
        self.assertEqual([txn["id"] for txn in groups[0]["transactions"]], [11, 12])
        self.assertEqual(groups[1]["key"], "5892100011112222")
        self.assertEqual(groups[1]["count"], 1)

    def test_build_accounting_card_groups_sorts_transactions_by_transfer_time(self):
        transactions = [
            make_txn(41, card_number="6037123412341234", amount=100_000, transfer_date="1405/02/23", transfer_time="11:10"),
            make_txn(42, card_number="6037123412341234", amount=110_000, transfer_date="1405/02/22", transfer_time="15:45"),
            make_txn(43, card_number="6037123412341234", amount=120_000, transfer_date="1405/02/22", transfer_time="09:15"),
        ]

        groups = accounting_transactions.build_accounting_card_groups(transactions)

        self.assertEqual([txn["id"] for txn in groups[0]["transactions"]], [43, 42, 41])

    def test_accounting_queue_keyboard_lists_only_cards_with_transactions(self):
        transactions = [
            make_txn(21, card_number="6037123412341234", amount=50_000, bank_name="ملت"),
            make_txn(22, card_number="6037123412341234", amount=70_000, bank_name="ملت"),
            make_txn(23, card_number="5892100011112222", amount=80_000, bank_name="سپه"),
        ]

        keyboard = accounting_transactions.accounting_queue_keyboard(transactions)
        card_callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if (button.callback_data or "").startswith("acct|card|")
        ]

        self.assertEqual(card_callbacks, ["acct|card|6037123412341234", "acct|card|5892100011112222"])

    def test_accounting_card_transactions_keyboard_has_quick_approve_button(self):
        card_key = "6037123412341234"
        keyboard = accounting_transactions.accounting_card_transactions_keyboard(
            card_key,
            [
                make_txn(
                    31,
                    card_number=card_key,
                    amount=125_000,
                    bank_name="ملت",
                    duplicate=1,
                )
            ],
        )

        first_row = keyboard.inline_keyboard[0]
        self.assertEqual(len(first_row), 2)
        self.assertEqual(first_row[0].callback_data, "acct|open|31|6037123412341234")
        self.assertEqual(first_row[1].callback_data, "acct|approve|31|6037123412341234")
        self.assertEqual(first_row[1].text, "✅")
        self.assertIn("1405/02/22 14:35", first_row[0].text)
        self.assertIn("125,000", first_row[0].text)
        self.assertIn("!", first_row[0].text)
        self.assertNotIn("31", first_row[0].text)
        self.assertNotIn("علی", first_row[0].text)
        self.assertNotIn("|", first_row[0].text)


if __name__ == "__main__":
    unittest.main()
