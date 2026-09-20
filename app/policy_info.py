"""
Read-only summary of Nortex policy NTX-HR-POL-11, for the Admin oversight screen only.
This does NOT drive any enforcement - the real rules live in policy_engine.py and
state_machine.py. This file exists so the Admin can see "what's configured" without
being able to change it (Admin in this system is oversight-only, not editable config).
"""

POLICY_INFO = {
    "document": "NTX-HR-POL-11 Rev 4, effective 01 Apr 2026",

    "approval_bands": [
        {"range": "Up to INR 25,000", "approvals": ["Reporting Manager"]},
        {"range": "INR 25,001 - 75,000", "approvals": ["Reporting Manager", "Head of Department"]},
        {"range": "INR 75,001 - 2,00,000", "approvals": ["Reporting Manager", "Head of Department", "Head of Division"]},
        {"range": "Above INR 2,00,000, or any international travel", "approvals": ["Reporting Manager", "Head of Department", "Head of Division", "MD/CEO"]},
    ],
    "finance_verification": "Required on every claim regardless of value, after business approvals are complete (policy 2.1).",

    "lodging_limits_per_night": {
        "Tier 1 (Bengaluru, Mumbai, Delhi NCR, Hyderabad, Chennai, Pune, Kolkata)": 6000,
        "Tier 2": 4000,
        "Tier 3 and others": 2800,
    },

    "meal_limits_per_day": {
        "Tier 1 cities": 1500,
        "Tier 2 and below": 1000,
    },

    "non_reimbursable_items": [
        "Laundry, mini bar, in-room entertainment, spa, gym",
        "Personal phone or data charges",
        "Alcohol, except where part of an approved business entertainment claim",
        "Fines, penalties, and traffic challans",
        "Travel insurance purchased independently",
        "Expenses incurred by any person other than the claimant",
    ],

    "submission_window_days": 7,
    "payment_runs": ["10th of each month", "25th of each month"],
    "business_entertainment": "Above INR 2,000 requires prior Head of Department approval (policy 3.5).",
}
