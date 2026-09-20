# Nortex Travel Expense Reimbursement

Employees claim travel expenses, the claim is checked against company policy, routed through approvers, then verified and paid by Finance.

**Live app:** https://nortex-expense-app.onrender.com/static/login.html
(Free hosting: the first load after idle takes up to a minute. Data resets when the server restarts.)

## Demo logins
Password for everyone: `nortex123`

| Person | Code | Role |
|---|---|---|
| Chaitanya Reddy | NX-4471 | Employee (owns claim C001) |
| Suresh Iyer | NX-2210 | Reporting Manager (approver 1) |
| Meera Krishnan | NX-1108 | Head of Department (approver 2) |
| Ravi Menon | NX-3305 | Finance (verify and pay) |
| Deepa Nair | NX-5182 | Employee (cannot see Chaitanya's claim) |
| System Admin | NX-9000 | Admin (read-only) |

## Flow
Draft -> Submit -> Suresh approves -> Meera approves -> Finance verifies -> Finance marks paid.
Any approver or Finance can send a claim back (remarks required) or reject it.
Claims up to 25,000 need only the reporting manager; above that, the Head of Department too (policy section 2).

## Run locally (Python 3.10+)
    pip install -r requirements.txt
    python -m app.seed          # resets the database with demo users and claim C001
    uvicorn app.main:app --reload
    python -m pytest            # 42 tests

## Structure
- `app/state_machine.py` : status rules (who can do what, when)
- `app/approval_chain.py` : builds each claim's approvers from the amount and manager links
- `app/auth.py` : password hashing and sessions (identity comes only from the session cookie)
- `app/policy_engine.py` : policy checks and totals
- `app/main.py` : API endpoints; `static/` : plain HTML screens; `data/raw/` : the provided pack

## Known limits
See NOTE.md. In short: claim lines are prepared data, not parsed from the emails live.
