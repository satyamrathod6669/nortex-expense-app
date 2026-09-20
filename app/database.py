import os
import sqlite3
from contextlib import contextmanager

# BASE_DIR = the project root, worked out from this file's own location.
# This means the app finds its files no matter which folder you launch it from.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "app.db")


def db_path() -> str:
    """The tests point NORTEX_DB at a temporary file so they never touch the real database."""
    return os.environ.get("NORTEX_DB", DEFAULT_DB_PATH)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=10)  # wait up to 10s if another request holds the lock
    conn.row_factory = sqlite3.Row                 # rows behave like dicts: row["column_name"]
    conn.execute("PRAGMA foreign_keys = ON")       # SQLite ignores foreign keys unless this is switched on, per connection
    return conn


@contextmanager
def connection():
    """Use as `with connection() as conn:`. The connection always closes, even if an error is raised.
    If we never called commit(), closing rolls back any half-finished changes."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


SCHEMA = """
-- USERS: who can log in. Org data (role, manager) comes from employee_master.csv when we seed.
CREATE TABLE IF NOT EXISTS users (
    emp_code      TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL,
    manager_code  TEXT,                    -- reporting manager's emp_code, NULL for the MD
    password_hash TEXT NOT NULL            -- salted PBKDF2 hash, never the plain password
);

-- SESSIONS: one row per logged-in browser. The random token in the cookie points at this row.
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    emp_code   TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (emp_code) REFERENCES users(emp_code)
);

-- CLAIMS: one row per settlement claim (the header)
CREATE TABLE IF NOT EXISTS claims (
    claim_id         TEXT PRIMARY KEY,
    trip_id          TEXT NOT NULL,
    employee_code    TEXT NOT NULL,
    total_claimed    REAL,
    total_disallowed REAL,
    advance_amount   REAL,
    payable_amount   REAL,
    status           TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','awaiting_approval','awaiting_finance',
                          'ready_for_payment','sent_back','rejected','paid')),
    submitted_at     TEXT,
    FOREIGN KEY (employee_code) REFERENCES users(emp_code)
);

-- CLAIM_LINES: one row per expense line (the detail rows)
CREATE TABLE IF NOT EXISTS claim_lines (
    line_id       TEXT PRIMARY KEY,
    claim_id      TEXT NOT NULL,
    date          TEXT,
    time          TEXT,
    merchant      TEXT,
    description   TEXT,
    item_type     TEXT,
    category      TEXT,
    amount        REAL,
    city          TEXT,
    paid_by       TEXT,
    proof_ref     TEXT,
    status        TEXT,
    status_reason TEXT,
    source_email  TEXT,
    FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
);

-- CLAIM_APPROVERS: the approval chain for ONE claim (who must approve, in what order).
-- Built when the employee submits, from the amount band and the manager links in the CSV.
CREATE TABLE IF NOT EXISTS claim_approvers (
    claim_id      TEXT NOT NULL,
    step_no       INTEGER NOT NULL,        -- 1 = first approver, 2 = second, ...
    approver_code TEXT NOT NULL,
    level         TEXT NOT NULL,           -- e.g. "Reporting Manager", "Head of Department"
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved')),
    acted_at      TEXT,
    PRIMARY KEY (claim_id, step_no),
    FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
    FOREIGN KEY (approver_code) REFERENCES users(emp_code)
);

-- APPROVAL_HISTORY: audit log. One row per action, added to but never edited by the app.
CREATE TABLE IF NOT EXISTS approval_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id       TEXT NOT NULL,
    actor_emp_code TEXT NOT NULL,
    action         TEXT NOT NULL,          -- submitted / approved / verified / paid / sent_back / rejected
    remarks        TEXT,
    timestamp      TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(claim_id),
    FOREIGN KEY (actor_emp_code) REFERENCES users(emp_code)
);
"""


def init_db() -> None:
    """Creates the tables if they don't exist. Safe to run twice.
    NOTE: this does not change tables that already exist, so after a schema change run `python -m app.seed`."""
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    with connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
