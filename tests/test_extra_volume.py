import sys
import unittest
from types import ModuleType


start_stub = sys.modules.setdefault("handlers.user.start", ModuleType("handlers.user.start"))
start_stub.is_user_member = lambda user_id: True
start_stub.join_channel_keyboard = lambda: None

main_menu_stub = sys.modules.setdefault("keyboards.main_menu", ModuleType("keyboards.main_menu"))
main_menu_stub.main_menu_keyboard_for_user = lambda user_id: None

admin_notifier_stub = sys.modules.setdefault("services.admin_notifier", ModuleType("services.admin_notifier"))
admin_notifier_stub.send_message_to_admins = lambda *args, **kwargs: None

if "services.db" not in sys.modules:
    db_stub = ModuleType("services.db")
    db_stub.get_active_volume_packages = lambda *args, **kwargs: []
    db_stub.get_volume_services_for_user = lambda *args, **kwargs: []
    sys.modules["services.db"] = db_stub

if "services.order_workflow" not in sys.modules:
    order_workflow_stub = ModuleType("services.order_workflow")
    order_workflow_stub.purchase_volume_package = lambda *args, **kwargs: {"ok": False}
    sys.modules["services.order_workflow"] = order_workflow_stub

if "services.runtime_settings" not in sys.modules:
    runtime_settings_stub = ModuleType("services.runtime_settings")
    runtime_settings_stub.get_bool_setting = lambda *args, **kwargs: True
    runtime_settings_stub.get_text_setting = lambda *args, **kwargs: ""
    sys.modules["services.runtime_settings"] = runtime_settings_stub

from handlers.user import extra_volume


class ExtraVolumeUiTests(unittest.TestCase):
    def test_sort_volume_packages_orders_by_volume_ascending(self):
        packages = [
            {"id": 3, "name": "30GB", "volume_gb": 30, "price": 300_000, "sort_order": 0},
            {"id": 1, "name": "5GB", "volume_gb": 5, "price": 70_000, "sort_order": 0},
            {"id": 2, "name": "10GB", "volume_gb": 10, "price": 120_000, "sort_order": 99},
        ]

        sorted_packages = extra_volume.sort_volume_packages(packages)

        self.assertEqual([package["id"] for package in sorted_packages], [1, 2, 3])

    def test_packages_keyboard_uses_sorted_volume_order(self):
        keyboard = extra_volume.packages_keyboard(
            [
                {"id": 3, "name": "30GB", "volume_gb": 30, "price": 300_000, "sort_order": 0},
                {"id": 1, "name": "5GB", "volume_gb": 5, "price": 70_000, "sort_order": 0},
                {"id": 2, "name": "10GB", "volume_gb": 10, "price": 120_000, "sort_order": 0},
            ]
        )

        callbacks = [
            row[0].callback_data
            for row in keyboard.inline_keyboard
            if (row[0].callback_data or "").startswith("extra_volume|package|")
        ]

        self.assertEqual(
            callbacks,
            ["extra_volume|package|1", "extra_volume|package|2", "extra_volume|package|3"],
        )


if __name__ == "__main__":
    unittest.main()
