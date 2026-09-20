"""
The rules for moving a claim between statuses. Pure logic: no database, no web code.
That makes it easy to test and easy to explain.

Statuses:  draft -> awaiting_approval -> awaiting_finance -> ready_for_payment -> paid
           (an approver or Finance can also send a claim back, or reject it)
Actions:   submit, approve, send_back, reject, verify, pay
"""


class TransitionError(Exception):
    """Carries an HTTP status code so the API can answer 403 (not allowed), 409 (wrong state) or 400 (bad input)."""
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# For each status, which actions make sense at all. Anything else is a 409.
ALLOWED_ACTIONS = {
    "draft":             {"submit"},
    "sent_back":         {"submit"},                          # employee fixes the claim and resubmits
    "awaiting_approval": {"approve", "send_back", "reject"},  # the current approver in the chain
    "awaiting_finance":  {"verify", "send_back", "reject"},   # Finance verification (policy 2.1)
    "ready_for_payment": {"pay"},                             # waiting for the 10th / 25th payment run
    "paid":              set(),
    "rejected":          set(),
}
ALL_ACTIONS = ["submit", "approve", "send_back", "reject", "verify", "pay"]


def check_permission(status: str, action: str, claimant_code: str, actor: dict,
                     pending_approver_code: str | None) -> None:
    """Raises TransitionError if `actor` may not do `action` on a claim in `status`. Returns None if allowed.
    `actor` is the logged-in user, taken from the session, never from the request."""
    if action not in ALLOWED_ACTIONS.get(status, set()):
        raise TransitionError(409, f"Cannot {action.replace('_', ' ')} a claim that is '{status}'")

    if status in ("draft", "sent_back"):
        if actor["emp_code"] != claimant_code:
            raise TransitionError(403, "Only the claim owner can submit it")

    elif status == "awaiting_approval":
        if actor["emp_code"] == claimant_code:
            raise TransitionError(403, "An approver cannot approve their own claim (policy 2.2)")
        if actor["emp_code"] != pending_approver_code:
            raise TransitionError(403, "It is not your turn to act on this claim")

    else:  # awaiting_finance or ready_for_payment
        if actor["role"] != "Finance":
            raise TransitionError(403, "Only Finance can act at this stage")
        if actor["emp_code"] == claimant_code:
            raise TransitionError(403, "Finance cannot process their own claim (policy 2.2)")


def decide(status: str, action: str, claimant_code: str, actor: dict,
           pending_approver_code: str | None, steps_after: int, remarks: str | None) -> str:
    """Returns the claim's NEW status, or raises TransitionError.
    `steps_after` = approval steps still to do once this action is done
    (for 'submit' it's the size of the whole chain)."""
    check_permission(status, action, claimant_code, actor, pending_approver_code)

    if action in ("send_back", "reject") and not (remarks and remarks.strip()):
        raise TransitionError(400, "Remarks are required to send back or reject a claim (policy 2.3)")

    if action in ("submit", "approve"):
        return "awaiting_approval" if steps_after > 0 else "awaiting_finance"
    return {"send_back": "sent_back", "reject": "rejected",
            "verify": "ready_for_payment", "pay": "paid"}[action]


def available_actions(status: str, claimant_code: str, actor: dict,
                      pending_approver_code: str | None) -> list[str]:
    """The actions this user can take on this claim right now. The screens show only these buttons."""
    allowed = []
    for action in ALL_ACTIONS:
        try:
            check_permission(status, action, claimant_code, actor, pending_approver_code)
            allowed.append(action)
        except TransitionError:
            pass
    return allowed
