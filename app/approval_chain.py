from app.policy_engine import required_approval_levels

# Rank of each role in the company. Used for policy 2.2: an employee can't approve their own claim,
# so approval levels at or below the claimant's own rank are skipped.
ROLE_RANK = {"Employee": 0, "Finance": 0, "Reporting Manager": 1,
             "Head of Department": 2, "Head of Division": 3, "MD": 4}


def build_chain(claimant_code: str, claimed_amount: float, users: dict) -> list[dict]:
    """
    Works out WHO must approve a claim, in order (policy section 2).
    `users` is {emp_code: {"role":..., "manager_code":...}} loaded from the database.

    1. The amount decides how many levels are needed (policy_engine.required_approval_levels).
    2. We walk up the management line from the claimant: manager, manager's manager, ...
    3. The Nth level is approved by the Nth person up the line.
    4. If the claimant sits at a level themselves (e.g. a Reporting Manager claiming),
       that level is skipped and the next level up acts (policy 2.2).
    Finance verification is a separate stage after this chain, so it is not in here.
    """
    levels = required_approval_levels(claimed_amount)
    claimant = users[claimant_code]

    above, seen, code = [], {claimant_code}, claimant["manager_code"]
    while code and code in users and code not in seen:      # `seen` stops an accidental loop in the data
        above.append((code, users[code]))
        seen.add(code)
        code = users[code]["manager_code"]

    needed = levels[ROLE_RANK.get(claimant["role"], 0):]    # drop levels the claimant sits at or below
    return [{"step_no": i + 1, "approver_code": code, "level": level}
            for i, (level, (code, _)) in enumerate(zip(needed, above))]
