from pathlib import Path
import sqlite3
import shutil

DB_PATH = "database/vpn_bot.db"   # اسم دیتابیس خودت را بگذار
BASE_DIR = Path("transactions")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    moved_count = 0
    skipped_count = 0
    updated_db_count = 0

    for file_path in BASE_DIR.glob("*.jpg"):
        filename = file_path.name

        # انتظار داریم فرمت فایل این باشد:
        # user_id-file_id.jpg
        if "-" not in filename:
            print(f"[SKIP] نامعتبر: {filename}")
            skipped_count += 1
            continue

        user_id, rest = filename.split("-", 1)

        # اگر user_id عددی نبود
        if not user_id.isdigit():
            print(f"[SKIP] user_id نامعتبر: {filename}")
            skipped_count += 1
            continue

        user_folder = BASE_DIR / user_id
        user_folder.mkdir(parents=True, exist_ok=True)

        new_path = user_folder / rest

        # اگر فایل مقصد از قبل وجود داشت
        if new_path.exists():
            print(f"[SKIP] فایل مقصد وجود دارد: {new_path}")
            skipped_count += 1
            continue

        # انتقال فایل
        shutil.move(str(file_path), str(new_path))
        moved_count += 1
        print(f"[MOVE] {file_path} -> {new_path}")

        # آپدیت مسیر در دیتابیس
        old_db_path = str(file_path).replace("\\", "/")
        new_db_path = str(new_path).replace("\\", "/")

        cur.execute(
            "UPDATE transactions SET photo_path = ? WHERE photo_path = ?",
            (new_db_path, old_db_path)
        )

        updated_db_count += cur.rowcount

    conn.commit()
    conn.close()

    print("\n--- DONE ---")
    print(f"Moved files: {moved_count}")
    print(f"Skipped files: {skipped_count}")
    print(f"Updated DB rows: {updated_db_count}")


if __name__ == "__main__":
    main()