import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException

from app.database import connection

SESSION_COOKIE = "nortex_session"
SESSION_HOURS = 8
PBKDF2_ITERATIONS = 200_000   # deliberately slow, so guessing passwords is expensive

# A real hash used when the employee code doesn't exist, so a wrong code and a wrong
# password take about the same time and an attacker can't tell which one was wrong.
_DUMMY_HASH = None


# ---------- passwords ----------

def hash_password(password: str) -> str:
    """Returns 'pbkdf2_sha256$iterations$salt$hash'. The salt is random per user,
    so two users with the same password get different hashes."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), expected)   # constant-time comparison


def authenticate(emp_code: str, password: str) -> dict | None:
    """Returns the user (without the password hash) if the code and password match, else None."""
    global _DUMMY_HASH
    with connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE emp_code = ?", (emp_code,)).fetchone()
    if row is None:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password("not-a-real-password")
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return public_user(row)


def public_user(row) -> dict:
    return {"emp_code": row["emp_code"], "name": row["name"], "role": row["role"],
            "manager_code": row["manager_code"]}


# ---------- sessions ----------

def create_session(emp_code: str) -> str:
    """Makes a random, unguessable token and remembers who it belongs to."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    with connection() as conn:
        conn.execute("INSERT INTO sessions (token, emp_code, expires_at) VALUES (?, ?, ?)",
                     (token, emp_code, expires.isoformat()))
        conn.commit()
    return token


def delete_session(token: str | None) -> None:
    if not token:
        return
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def get_user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    with connection() as conn:
        row = conn.execute(
            """SELECT u.*, s.expires_at FROM sessions s
               JOIN users u ON u.emp_code = s.emp_code WHERE s.token = ?""", (token,)).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))   # expired: clean it up
            conn.commit()
            return None
        return public_user(row)


# ---------- the one thing every protected endpoint uses ----------

def get_current_user(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    """FastAPI runs this before any endpoint that lists it as a dependency.
    Who is calling is decided ONLY by the session cookie the server issued at login.
    Nothing in the request body or URL can name the caller."""
    user = get_user_for_token(session)
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user
