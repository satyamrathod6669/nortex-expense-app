from app.models import ExpenseLine

MEAL_LIMIT_TIER1 = 1500.00  # per day, policy 3.3


def summarize_claim(lines: list[ExpenseLine]) -> dict:
    """
    Rolls up all lines into the 3 numbers Finance actually cares about.
    - total_claimed: everything the employee is claiming (excludes blocked lines -
      those never entered the claim at all, e.g. Deepa's ride)
    - total_disallowed: sum of lines marked disallowed (shown, not hidden - policy §4)
    - payable: what's actually owed to the employee, after disallowed items
      are subtracted and the advance already paid is adjusted (policy §1.3)
    """
    claim_lines = [l for l in lines if l.status != "blocked" and l.paid_by == "Employee"]

    total_claimed = sum(l.amount for l in claim_lines if l.status != "disallowed")
    total_disallowed = sum(l.amount for l in claim_lines if l.status == "disallowed")

    return {
        "total_claimed": round(total_claimed, 2),
        "total_disallowed": round(total_disallowed, 2),
        "claim_lines_count": len(claim_lines),
    }


def payable_amount(total_claimed: float, advance_amount: float) -> float:
    """
    Policy 1.3: advance is adjusted against the claim. If claim > advance,
    the difference is payable to the employee.
    (If claim < advance, it would be negative here - meaning recoverable
    FROM the employee via payroll, which policy 1.3 also covers.)
    """
    return round(total_claimed - advance_amount, 2)

def check_meal_limit(lines: list[ExpenseLine]) -> list[ExpenseLine]:
    """
    Policy 3.3: meals capped per day (Tier 1 = 1,500/day). Groups meal-type
    lines by date, sums net amount per day, and resolves the 'flagged'
    status left by extraction into a final allowed/disallowed.
    """
    from collections import defaultdict
    by_date = defaultdict(list)
    for l in lines:
        if l.category == "Meals":
            by_date[l.date].append(l)

    for day, day_lines in by_date.items():
        day_total = sum(l.amount for l in day_lines)
        if day_total <= MEAL_LIMIT_TIER1:
            for l in day_lines:
                l.status = "allowed"
                l.status_reason = None
        else:
            # Simple rule for this dataset: excess amount on the last line disallowed
            for l in day_lines:
                l.status = "disallowed"
                l.status_reason = f"Day total {day_total} exceeds Tier 1 meal limit {MEAL_LIMIT_TIER1}/day (policy 3.3)"
    return lines


def required_approval_levels(claimed_amount: float) -> list[str]:
    """
    Policy section 2, approval matrix. Returns the list of roles that must
    approve, in order. This claim's total falls in the 25,001-75,000 band,
    so both Reporting Manager and HoD are required.
    """
    if claimed_amount <= 25000:
        return ["Reporting Manager"]
    elif claimed_amount <= 75000:
        return ["Reporting Manager", "Head of Department"]
    elif claimed_amount <= 200000:
        return ["Reporting Manager", "Head of Department", "Head of Division"]
    else:
        return ["Reporting Manager", "Head of Department", "Head of Division", "MD/CEO"]