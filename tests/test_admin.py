"""
Tests for the read-only Admin role. Admin can see everything, do nothing.
Uses the same client_for()/act() helpers as the rest of the suite.
"""
from tests.conftest import CHAITANYA, SURESH, MEERA, RAVI, DEEPA, client_for, act

ADMIN = "NX-9000"


def test_admin_sees_draft_claim_but_deepa_does_not():
    admin = client_for(ADMIN)
    deepa = client_for(DEEPA)

    res_admin = admin.get("/api/claims/C001")
    assert res_admin.status_code == 200

    res_deepa = deepa.get("/api/claims/C001")
    assert res_deepa.status_code == 403


def test_admin_claims_list_includes_draft_claim():
    admin = client_for(ADMIN)
    res = admin.get("/api/claims")
    assert res.status_code == 200
    claim_ids = [c["claim_id"] for c in res.json()]
    assert "C001" in claim_ids


def test_admin_cannot_submit_someone_elses_draft_claim():
    admin = client_for(ADMIN)
    res = act(admin, "C001", "submit")
    assert res.status_code == 403


def test_admin_cannot_act_once_claim_is_awaiting_approval():
    # Get the claim into awaiting_approval first (as the real owner), then try as Admin
    chaitanya = client_for(CHAITANYA)
    admin = client_for(ADMIN)

    res = act(chaitanya, "C001", "submit")
    assert res.status_code == 200
    assert res.json()["new_status"] == "awaiting_approval"

    for action in ("approve", "send_back", "reject"):
        res = act(admin, "C001", action, remarks="test")
        assert res.status_code == 403, f"Admin should get 403 on '{action}', got {res.status_code}"


def test_admin_cannot_verify_or_pay_at_finance_stage():
    # Walk the claim all the way to awaiting_finance, then to ready_for_payment,
    # trying Admin actions at each stage.
    chaitanya = client_for(CHAITANYA)
    suresh = client_for(SURESH)
    meera = client_for(MEERA)
    ravi = client_for(RAVI)
    admin = client_for(ADMIN)

    assert act(chaitanya, "C001", "submit").status_code == 200
    assert act(suresh, "C001", "approve").status_code == 200
    res = act(meera, "C001", "approve")
    assert res.status_code == 200
    assert res.json()["new_status"] == "awaiting_finance"

    # Admin tries to verify - should be blocked, only Finance can act here
    res = act(admin, "C001", "verify")
    assert res.status_code == 403

    # Now let Finance actually verify, reaching ready_for_payment
    res = act(ravi, "C001", "verify")
    assert res.status_code == 200
    assert res.json()["new_status"] == "ready_for_payment"

    # Admin tries to pay - should still be blocked
    res = act(admin, "C001", "pay")
    assert res.status_code == 403


def test_non_admin_blocked_from_admin_policy_endpoint():
    for emp_code in (CHAITANYA, SURESH, RAVI):
        client = client_for(emp_code)
        res = client.get("/api/admin/policy")
        assert res.status_code == 403, f"{emp_code} should not be able to read admin policy"


def test_non_admin_blocked_from_admin_users_endpoint():
    for emp_code in (CHAITANYA, SURESH, RAVI):
        client = client_for(emp_code)
        res = client.get("/api/admin/users")
        assert res.status_code == 403, f"{emp_code} should not be able to read admin users list"


def test_admin_can_read_policy():
    admin = client_for(ADMIN)
    res = admin.get("/api/admin/policy")
    assert res.status_code == 200
    data = res.json()
    assert "approval_bands" in data
    assert "lodging_limits_per_night" in data


def test_admin_users_list_has_no_password_data():
    admin = client_for(ADMIN)
    res = admin.get("/api/admin/users")
    assert res.status_code == 200
    users = res.json()
    assert len(users) > 0
    for u in users:
        assert "password_hash" not in u
        assert "password" not in u
        assert set(u.keys()) == {"emp_code", "name", "role", "manager_name"}