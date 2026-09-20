from dataclasses import dataclass
from datetime import date, time
from typing import Optional

@dataclass
class Trip:
    trip_id: str              # e.g. "TR-2026-0616" - the Travel Request ID from policy §1.1
    employee_code: str        # e.g. "NX-4471" - links to employee_master.csv
    destination_city: str     # e.g. "Bengaluru" - used to check lines match the trip
    start_date: date          # 2026-06-16
    end_date: date            # 2026-06-20
    approved_amount: float    # 48000 - the estimated spend from email 01
    advance_amount: float     # 20000 - from email 03
    status: str               # "approved", "pending", "rejected"


@dataclass
class ExpenseLine:
    line_id: str               # unique id for this line, e.g. "L001"
    claim_id: str               # which settlement claim this belongs to
    trip_id: str                # links back to the Trip above
    date: date                  # when the expense happened
    time: Optional[time]        # when known - needed to tell apart same-day same-fare rides
    merchant: str                # "Uber", "Keys Prime Whitefield", "MakeMyTrip"
    description: str            # raw text as seen in the source, e.g. "Mini Bar"
    item_type: str               # normalized type: "room_charge", "laundry", "taxi_fare"...
    category: str                # broad group: "Lodging", "Meals", "Local Conveyance"...
    amount: float                 # the amount in rupees
    city: str                    # where this expense happened
    paid_by: str                  # "Employee" or "Company"
    proof_ref: str                 # bill/invoice number, or email Message-ID if no bill number
    status: str                    # "allowed", "disallowed", "flagged", "blocked"
    status_reason: Optional[str]   # why, if not allowed - e.g. "Non-reimbursable: mini bar (policy §4)"
    source_email: str              # which .eml file this line came from, for audit trail