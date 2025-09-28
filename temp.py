import sqlite3
from config import DB_PATH

def fill_orders_volume():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # فرض می‌کنیم جدول plans هم فیلدی داره به اسم volume_gb
    cur.execute("SELECT id, volume_gb FROM plans")
    plans = {pid: vol for pid, vol in cur.fetchall()}

    cur.execute("SELECT id, plan_id FROM orders WHERE volume_gb IS NULL OR volume_gb = 0")
    orders = cur.fetchall()

    for oid, pid in orders:
        if pid in plans:
            cur.execute("UPDATE orders SET volume_gb = ? WHERE id = ?", (plans[pid], oid))
            print(f"[+] Updated order {oid} with volume {plans[pid]} GB")

    conn.commit()
    conn.close()


fill_orders_volume()

