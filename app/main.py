import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.approval_chain import build_chain
from app.auth import (SESSION_COOKIE, SESSION_HOURS, authenticate, create_session,
                      delete_session, get_current_user)
from app.database import BASE_DIR, connection, init_db
from app.policy_info import POLICY_INFO
from app.state_machine import TransitionError, available_actions, decide
from app.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with connection() as conn:
        has_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0
    if not has_users:
        seed_database()    # first start on a fresh server: create demo users and claim C001
    yield


app = FastAPI(title="Nortex Travel Expense System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Finance can see claims once they reach the Finance stage.
FINANCE_VISIBLE = ("awaiting_finance", "ready_for_payment", "paid")
HISTORY_VERB = {"submit": "submitted", "approve": "approved", "send_back": "sent_back",
                "reject": "rejected", "verify": "verified", "pay": "paid"}

COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"   # set to 1 on the deployed HTTPS site


class LoginRequest(BaseModel):
    emp_code: str
    password: str


class ActionRequest(BaseModel):
    # Note what is NOT here: who is acting. The server knows that from the session cookie.
    action: Literal["submit", "approve", "send_back", "reject", "verify", "pay"]
    remarks: str | None = None


# ---------- small helpers ----------

def load_users(conn) -> dict:
    rows = conn.execute("SELECT emp_code, name, role, manager_code FROM users").fetchall()
    return {r["emp_code"]: dict(r) for r in rows}


def fetch_claim(conn, claim_id: str) -> dict:
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return dict(row)


def fetch_chain(conn, claim_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT ca.step_no, ca.approver_code, ca.level, ca.status, ca.acted_at, u.name AS approver_name
           FROM claim_approvers ca JOIN users u ON u.emp_code = ca.approver_code
           WHERE ca.claim_id = ? ORDER BY ca.step_no""", (claim_id,)).fetchall()
    return [dict(r) for r in rows]


def pending_step(chain: list[dict]) -> dict | None:
    return next((s for s in chain if s["status"] == "pending"), None)


def can_view(user: dict, claim: dict, chain: list[dict]) -> bool:
    """ONE rule for who may see a claim, used by both the list and the detail endpoints:
    the owner, an approver in this claim's chain, Finance once it reaches the Finance stage,
    or Admin (read-only oversight of every claim, regardless of stage)."""
    if user["role"] == "Admin":
        return True
    if claim["employee_code"] == user["emp_code"]:
        return True
    if any(s["approver_code"] == user["emp_code"] for s in chain):
        return True
    return user["role"] == "Finance" and claim["status"] in FINANCE_VISIBLE


def waiting_on(claim: dict, chain: list[dict]) -> str | None:
    status = claim["status"]
    if status == "awaiting_approval":
        step = pending_step(chain)
        return f"{step['approver_name']} ({step['level']})" if step else None
    return {"draft": "Employee (not yet submitted)", "sent_back": "Employee (returned for correction)",
            "awaiting_finance": "Finance verification",
            "ready_for_payment": "Finance payment run"}.get(status)


def my_actions(user: dict, claim: dict, chain: list[dict]) -> list[str]:
    # Admin is never the claimant, never a pending approver, never Finance -
    # so available_actions() naturally returns [] for them. No special-casing needed here.
    step = pending_step(chain)
    return available_actions(claim["status"], claim["employee_code"], user,
                             step["approver_code"] if step else None)


def require_admin(user: dict) -> None:
    if user["role"] != "Admin":
        raise HTTPException(status_code=403, detail="Admin access only")


# ---------- login / logout ----------

@app.get("/")
def home():
    return RedirectResponse("/static/login.html")


@app.get("/api/demo-users")
def demo_users():
    """Public on purpose: fills the demo login dropdown. Returns only code, name and role."""
    with connection() as conn:
        rows = conn.execute("SELECT emp_code, name, role FROM users ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/login")
def login(req: LoginRequest, response: Response):
    user = authenticate(req.emp_code, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid employee code or password")
    token = create_session(user["emp_code"])
    # HttpOnly: page JavaScript can't read the cookie. SameSite=Lax: other sites can't send it on POSTs.
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                        max_age=SESSION_HOURS * 3600)
    return {"emp_code": user["emp_code"], "name": user["name"], "role": user["role"]}


@app.post("/api/logout")
def logout(response: Response, session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    delete_session(session)               # the token stops working immediately, not just in this browser
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return {"emp_code": user["emp_code"], "name": user["name"], "role": user["role"]}


# ---------- claims ----------

@app.get("/api/claims")
def list_claims(user: dict = Depends(get_current_user)):
    """Only claims this user is allowed to see, each with who it is waiting on and what they can do."""
    with connection() as conn:
        users = load_users(conn)
        result = []
        for row in conn.execute("SELECT * FROM claims ORDER BY claim_id").fetchall():
            claim = dict(row)
            chain = fetch_chain(conn, claim["claim_id"])
            if not can_view(user, claim, chain):
                continue
            result.append({
                "claim_id": claim["claim_id"], "trip_id": claim["trip_id"],
                "employee_name": users[claim["employee_code"]]["name"],
                "total_claimed": claim["total_claimed"], "payable_amount": claim["payable_amount"],
                "status": claim["status"], "waiting_on": waiting_on(claim, chain),
                "my_actions": my_actions(user, claim, chain),
            })
    return result


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: str, user: dict = Depends(get_current_user)):
    with connection() as conn:
        claim = fetch_claim(conn, claim_id)
        chain = fetch_chain(conn, claim_id)
        if not can_view(user, claim, chain):
            raise HTTPException(status_code=403, detail="You are not allowed to view this claim")
        lines = conn.execute("SELECT * FROM claim_lines WHERE claim_id = ?", (claim_id,)).fetchall()
        history = conn.execute(
            """SELECT h.action, h.remarks, h.timestamp, h.actor_emp_code, u.name AS actor_name, u.role AS actor_role
               FROM approval_history h JOIN users u ON u.emp_code = h.actor_emp_code
               WHERE h.claim_id = ? ORDER BY h.id""", (claim_id,)).fetchall()
        owner = conn.execute("SELECT name FROM users WHERE emp_code = ?", (claim["employee_code"],)).fetchone()
    return {
        "claim": claim, "employee_name": owner["name"],
        "lines": [dict(l) for l in lines], "history": [dict(h) for h in history],
        "chain": chain, "waiting_on": waiting_on(claim, chain),
        "my_actions": my_actions(user, claim, chain),
    }


@app.post("/api/claims/{claim_id}/actions")
def act_on_claim(claim_id: str, req: ActionRequest, user: dict = Depends(get_current_user)):
    """The only way a claim changes status. Every rule lives in state_machine.decide()."""
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")   # take the write lock now, so two people acting at once are handled one at a time
        claim = fetch_claim(conn, claim_id)
        chain = fetch_chain(conn, claim_id)
        users = load_users(conn)

        # On submit the chain is (re)built from the current amount, so a corrected claim is routed correctly.
        new_chain = build_chain(claim["employee_code"], claim["total_claimed"], users) if req.action == "submit" else None
        step = pending_step(chain)
        if req.action == "submit":
            steps_after = len(new_chain)
        else:
            steps_after = max(len([s for s in chain if s["status"] == "pending"]) - 1, 0)

        try:
            new_status = decide(claim["status"], req.action, claim["employee_code"], user,
                                step["approver_code"] if step else None, steps_after, req.remarks)
        except TransitionError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

        now = datetime.now(timezone.utc).isoformat()
        if req.action == "submit":
            conn.execute("DELETE FROM claim_approvers WHERE claim_id = ?", (claim_id,))
            for s in new_chain:
                conn.execute("INSERT INTO claim_approvers (claim_id, step_no, approver_code, level) VALUES (?, ?, ?, ?)",
                             (claim_id, s["step_no"], s["approver_code"], s["level"]))
            conn.execute("UPDATE claims SET submitted_at = ? WHERE claim_id = ?", (now, claim_id))
        elif req.action == "approve":
            conn.execute("UPDATE claim_approvers SET status = 'approved', acted_at = ? WHERE claim_id = ? AND step_no = ?",
                         (now, claim_id, step["step_no"]))
        elif req.action == "send_back":
            # Decision: a returned claim restarts the whole chain when it is resubmitted.
            conn.execute("UPDATE claim_approvers SET status = 'pending', acted_at = NULL WHERE claim_id = ?", (claim_id,))

        # `AND status = ?` makes this update refuse to run if the status changed under us.
        updated = conn.execute("UPDATE claims SET status = ? WHERE claim_id = ? AND status = ?",
                               (new_status, claim_id, claim["status"]))
        if updated.rowcount != 1:
            raise HTTPException(status_code=409, detail="The claim was changed by someone else. Refresh and try again.")

        conn.execute("INSERT INTO approval_history (claim_id, actor_emp_code, action, remarks, timestamp) VALUES (?, ?, ?, ?, ?)",
                     (claim_id, user["emp_code"], HISTORY_VERB[req.action], req.remarks, now))
        conn.commit()
    return {"claim_id": claim_id, "new_status": new_status}


# ---------- admin (read-only oversight) ----------

@app.get("/api/admin/policy")
def admin_policy(user: dict = Depends(get_current_user)):
    """Static policy summary for display. See app/policy_info.py - this is not the
    enforcement logic, just a human-readable mirror of it for the oversight screen."""
    require_admin(user)
    return POLICY_INFO


@app.get("/api/admin/users")
def admin_users(user: dict = Depends(get_current_user)):
    """People and reporting lines. Deliberately selects only non-sensitive columns -
    password_hash is never touched by this query, so there's no risk of it leaking
    even by accident."""
    require_admin(user)
    with connection() as conn:
        rows = conn.execute("SELECT emp_code, name, role, manager_code FROM users ORDER BY name").fetchall()
        users_by_code = {r["emp_code"]: r["name"] for r in rows}
        result = []
        for r in rows:
            result.append({
                "emp_code": r["emp_code"], "name": r["name"], "role": r["role"],
                "manager_name": users_by_code.get(r["manager_code"]) if r["manager_code"] else None,
            })
    return result
