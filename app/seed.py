"""
Resets the demo database: users from the CSV, and the demo claim C001 in 'draft'.
Run from the project root:   python -m app.seed
Warning: this DELETES data/app.db and starts fresh (that is the point: it makes demos repeatable).
"""
import csv
import os

from app.auth import hash_password
from app.database import BASE_DIR, connection, db_path, init_db
from app.extraction import build_trip, extract_all_lines
from app.policy_engine import check_meal_limit, payable_amount, summarize_claim

EMPLOYEES_CSV = os.path.join(BASE_DIR, "data", "raw", "employee_master.csv")
DEMO_PASSWORD = os.environ.get("NORTEX_DEMO_PASSWORD", "nortex123")


def seed_database(password: str = DEMO_PASSWORD) -> None:
    if os.path.exists(db_path()):
        os.remove(db_path())
    init_db()

    trip = build_trip()
    lines = check_meal_limit(extract_all_lines())
    summary = summarize_claim(lines)
    payable = payable_amount(summary["total_claimed"], trip.advance_amount)

    with connection() as conn:
        with open(EMPLOYEES_CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                conn.execute(
                    "INSERT INTO users (emp_code, name, role, manager_code, password_hash) VALUES (?, ?, ?, ?, ?)",
                    (row["emp_code"], row["name"], row["role"],
                     row["reporting_manager_code"] or None, hash_password(password)))

        # Admin is not in the CSV - it's a separate, system-level account, not an employee
        # on the org chart. No manager_code: an Admin doesn't report to anyone in this claim
        # flow (separation of duties - see policy_info.py for why this role can't approve).
        conn.execute(
            "INSERT INTO users (emp_code, name, role, manager_code, password_hash) VALUES (?, ?, ?, ?, ?)",
            ("NX-9000", "System Admin", "Admin", None, hash_password(password)))

        conn.execute(
            """INSERT INTO claims (claim_id, trip_id, employee_code, total_claimed, total_disallowed,
                                   advance_amount, payable_amount, status)
               VALUES ('C001', ?, ?, ?, ?, ?, ?, 'draft')""",
            (trip.trip_id, trip.employee_code, summary["total_claimed"], summary["total_disallowed"],
             trip.advance_amount, payable))

        for l in lines:
            if l.status == "blocked":      # Deepa's ride never enters the claim (excluded lines get shown in a later step)
                continue
            conn.execute(
                """INSERT INTO claim_lines (line_id, claim_id, date, time, merchant, description, item_type,
                       category, amount, city, paid_by, proof_ref, status, status_reason, source_email)
                   VALUES (?, 'C001', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (l.line_id, str(l.date), str(l.time) if l.time else None, l.merchant, l.description,
                 l.item_type, l.category, l.amount, l.city, l.paid_by, l.proof_ref, l.status,
                 l.status_reason, l.source_email))
        conn.commit()


if __name__ == "__main__":
    seed_database()
    print(f"Database reset at {db_path()}")
    print(f"Log in as any employee code from data/raw/employee_master.csv, password: {DEMO_PASSWORD}")
    print(f"Admin: NX-9000, password: {DEMO_PASSWORD}")