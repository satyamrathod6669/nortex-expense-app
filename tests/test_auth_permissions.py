import csv
import threading

from fastapi.testclient import TestClient

from app import auth
from app.approval_chain import build_chain
from app.database import BASE_DIR, connection
from app.main import app
from app.state_machine import available_actions
from tests.conftest import (ARVIND, CHAITANYA, DEEPA, KAVITHA, MEERA, PASSWORD, RAVI, SURESH,
                            act, client_for)


def submitted_claim():
    """Helper: Chaitanya submits C001 and we return his logged-in client."""
    chaitanya = client_for(CHAITANYA)
    assert act(chaitanya, "C001", "submit").status_code == 200
    return chaitanya


# ---------- login and sessions ----------

def test_no_session_is_401():
    c = TestClient(app)
    assert c.get("/api/me").status_code == 401
    assert c.get("/api/claims").status_code == 401
    assert c.get("/api/claims/C001").status_code == 401
    assert act(c, "C001", "submit").status_code == 401


def test_wrong_password_and_unknown_user_are_401():
    c = TestClient(app)
    assert c.post("/api/login", json={"emp_code": CHAITANYA, "password": "wrong"}).status_code == 401
    assert c.post("/api/login", json={"emp_code": "NX-0000", "password": PASSWORD}).status_code == 401


def test_login_returns_the_right_user_and_no_password_hash():
    c = TestClient(app)
    body = c.post("/api/login", json={"emp_code": CHAITANYA, "password": PASSWORD}).json()
    assert body == {"emp_code": CHAITANYA, "name": "Chaitanya Reddy", "role": "Employee"}
    assert "password" not in str(c.get("/api/me").json()).lower()


def test_logout_kills_the_session():
    c = client_for(CHAITANYA)
    token = c.cookies.get("nortex_session")
    assert c.post("/api/logout").status_code == 200
    stale = TestClient(app)
    stale.cookies.set("nortex_session", token)          # replay the old token
    assert stale.get("/api/me").status_code == 401


def test_expired_session_is_401():
    c = client_for(CHAITANYA)
    with connection() as conn:
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
        conn.commit()
    assert c.get("/api/me").status_code == 401


def test_passwords_are_salted_and_hashed():
    with connection() as conn:
        hashes = [r["password_hash"] for r in conn.execute("SELECT password_hash FROM users")]
    assert all(h.startswith("pbkdf2_sha256$") and PASSWORD not in h for h in hashes)
    assert len(set(hashes)) == len(hashes)              # same password, different salt, different hash
    assert auth.verify_password(PASSWORD, hashes[0]) and not auth.verify_password("nope", hashes[0])


# ---------- who can see what ----------

def test_owner_sees_own_claim_with_answer_key_numbers():
    body = client_for(CHAITANYA).get("/api/claims/C001").json()
    assert body["claim"]["total_claimed"] == 26388.44
    assert body["claim"]["total_disallowed"] == 929.6
    assert body["claim"]["payable_amount"] == 6388.44


def test_other_employee_cannot_view_the_claim():
    deepa = client_for(DEEPA)
    assert deepa.get("/api/claims/C001").status_code == 403
    assert deepa.get("/api/claims").json() == []


def test_unrelated_manager_cannot_view_or_act():
    submitted_claim()
    arvind = client_for(ARVIND)                          # Head of Division: not in this claim's chain
    assert arvind.get("/api/claims/C001").status_code == 403
    assert act(arvind, "C001", "approve").status_code == 403


def test_approver_cannot_see_a_claim_before_it_is_submitted():
    assert client_for(SURESH).get("/api/claims/C001").status_code == 403
    assert client_for(SURESH).get("/api/claims").json() == []


def test_finance_sees_claims_only_from_the_finance_stage():
    ravi = client_for(RAVI)
    assert ravi.get("/api/claims/C001").status_code == 403       # draft
    submitted_claim()
    assert ravi.get("/api/claims/C001").status_code == 403       # still with the approvers


# ---------- the approval flow and who may act when ----------

def test_full_happy_path_to_paid():
    chaitanya = submitted_claim()
    body = chaitanya.get("/api/claims/C001").json()
    assert [(s["approver_code"], s["level"]) for s in body["chain"]] == \
           [(SURESH, "Reporting Manager"), (MEERA, "Head of Department")]
    assert body["waiting_on"] == "Suresh Iyer (Reporting Manager)"

    assert act(client_for(SURESH), "C001", "approve").status_code == 200
    assert act(client_for(MEERA), "C001", "approve").json()["new_status"] == "awaiting_finance"
    ravi = client_for(RAVI)
    assert act(ravi, "C001", "verify").json()["new_status"] == "ready_for_payment"
    assert act(ravi, "C001", "pay").json()["new_status"] == "paid"

    history = chaitanya.get("/api/claims/C001").json()["history"]
    assert [(h["actor_name"], h["action"]) for h in history] == [
        ("Chaitanya Reddy", "submitted"), ("Suresh Iyer", "approved"), ("Meera Krishnan", "approved"),
        ("Ravi Menon", "verified"), ("Ravi Menon", "paid")]


def test_claim_owner_cannot_approve_own_claim():
    chaitanya = submitted_claim()
    assert act(chaitanya, "C001", "approve").status_code == 403


def test_cannot_pretend_to_be_someone_else_in_the_request():
    chaitanya = submitted_claim()
    res = chaitanya.post("/api/claims/C001/actions",
                         json={"action": "approve", "actor_emp_code": SURESH, "emp_code": SURESH})
    assert res.status_code == 403                        # the server ignores who the body claims to be
    assert chaitanya.get("/api/claims/C001").json()["claim"]["status"] == "awaiting_approval"


def test_wrong_person_for_the_stage_gets_403():
    submitted_claim()
    assert act(client_for(MEERA), "C001", "approve").status_code == 403     # not her turn yet
    assert act(client_for(RAVI), "C001", "approve").status_code == 403      # Finance is not a manager
    assert act(client_for(SURESH), "C001", "verify").status_code == 409     # verify makes no sense at this stage


def test_manager_cannot_act_at_the_finance_stage():
    submitted_claim()
    act(client_for(SURESH), "C001", "approve")
    act(client_for(MEERA), "C001", "approve")
    assert act(client_for(SURESH), "C001", "verify").status_code == 403
    assert act(client_for(CHAITANYA), "C001", "verify").status_code == 403


def test_cannot_skip_stages_or_repeat_actions():
    chaitanya = client_for(CHAITANYA)
    assert act(chaitanya, "C001", "pay").status_code == 409                 # draft cannot be paid
    assert act(chaitanya, "C001", "submit").status_code == 200
    assert act(chaitanya, "C001", "submit").status_code == 409              # already submitted


def test_only_the_owner_can_submit():
    assert act(client_for(SURESH), "C001", "submit").status_code == 403
    assert act(client_for(DEEPA), "C001", "submit").status_code == 403


def test_send_back_needs_remarks_then_employee_can_resubmit():
    submitted_claim()
    suresh = client_for(SURESH)
    assert act(suresh, "C001", "send_back").status_code == 400
    assert act(suresh, "C001", "send_back", "   ").status_code == 400
    assert act(suresh, "C001", "send_back", "Please add dinner attendee names").json()["new_status"] == "sent_back"

    chaitanya = client_for(CHAITANYA)
    assert act(chaitanya, "C001", "submit").status_code == 200              # resubmit under the same claim id
    body = chaitanya.get("/api/claims/C001").json()
    assert body["waiting_on"] == "Suresh Iyer (Reporting Manager)"          # the chain restarted
    assert [h["action"] for h in body["history"]] == ["submitted", "sent_back", "submitted"]
    assert body["history"][1]["remarks"] == "Please add dinner attendee names"


def test_reject_needs_remarks_and_is_final():
    submitted_claim()
    suresh = client_for(SURESH)
    assert act(suresh, "C001", "reject").status_code == 400
    assert act(suresh, "C001", "reject", "Not a business trip").json()["new_status"] == "rejected"
    assert act(client_for(CHAITANYA), "C001", "submit").status_code == 409


def test_unknown_claim_is_404_and_unknown_action_is_422():
    c = client_for(CHAITANYA)
    assert c.get("/api/claims/C999").status_code == 404
    assert c.post("/api/claims/C001/actions", json={"action": "teleport"}).status_code == 422


def test_screens_get_only_the_actions_the_user_may_take():
    chaitanya = client_for(CHAITANYA)
    assert chaitanya.get("/api/claims/C001").json()["my_actions"] == ["submit"]
    act(chaitanya, "C001", "submit")
    assert chaitanya.get("/api/claims/C001").json()["my_actions"] == []
    assert client_for(SURESH).get("/api/claims/C001").json()["my_actions"] == ["approve", "send_back", "reject"]
    assert client_for(MEERA).get("/api/claims/C001").json()["my_actions"] == []       # her turn comes later
    assert client_for(SURESH).get("/api/claims").json()[0]["waiting_on"] == "Suresh Iyer (Reporting Manager)"


def test_two_simultaneous_approvals_only_one_wins():
    submitted_claim()
    results = []
    clients = [client_for(SURESH), client_for(SURESH)]

    def go(c):
        results.append(act(c, "C001", "approve").status_code)

    threads = [threading.Thread(target=go, args=(c,)) for c in clients]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results)[0] == 200 and results.count(200) == 1
    assert all(code in (200, 403, 409) for code in results)
    with connection() as conn:
        approved = conn.execute("SELECT COUNT(*) FROM claim_approvers WHERE status = 'approved'").fetchone()[0]
    assert approved == 1


# ---------- the approval chain (policy section 2) ----------

def load_users():
    with open(f"{BASE_DIR}/data/raw/employee_master.csv", newline="", encoding="utf-8-sig") as f:
        return {r["emp_code"]: {"role": r["role"], "manager_code": r["reporting_manager_code"] or None}
                for r in csv.DictReader(f)}


def codes(chain):
    return [s["approver_code"] for s in chain]


def test_chain_depends_on_the_amount_band():
    users = load_users()
    assert codes(build_chain(CHAITANYA, 25000, users)) == [SURESH]                       # up to 25,000
    assert codes(build_chain(CHAITANYA, 25000.01, users)) == [SURESH, MEERA]             # just over
    assert codes(build_chain(CHAITANYA, 75001, users)) == [SURESH, MEERA, ARVIND]
    assert codes(build_chain(CHAITANYA, 200001, users)) == [SURESH, MEERA, ARVIND, "NX-1000"]


def test_manager_claiming_skips_their_own_level():
    users = load_users()
    chain = build_chain(SURESH, 30000, users)            # Suresh is the Reporting Manager for level 1
    assert codes(chain) == [MEERA] and SURESH not in codes(chain)
    assert chain[0]["level"] == "Head of Department"


def test_nobody_ever_approves_their_own_claim():
    users = load_users()
    for emp in users:
        for amount in (10000, 50000, 150000, 500000):
            assert emp not in codes(build_chain(emp, amount, users))
