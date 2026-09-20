import os
import re
from datetime import date, time
from app.models import Trip, ExpenseLine

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def read_email(filename: str) -> str:
    """Read one .eml file as plain text."""
    path = os.path.join(RAW_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_trip() -> Trip:
    """
    Trip details come from email 01 (request) + 02 (approval) + 03 (advance).
    Hardcoded parsing since these are fixed, known emails - not a generic parser.
    """
    return Trip(
        trip_id="TR-2026-0616",
        employee_code="NX-4471",
        destination_city="Bengaluru",
        start_date=date(2026, 6, 16),
        end_date=date(2026, 6, 20),
        approved_amount=48000.00,
        advance_amount=20000.00,
        status="approved",
    )


def extract_flight_lines(trip_id: str) -> list[ExpenseLine]:
    """
    Email 04: flight e-ticket. Per policy 3.2, air travel is booked centrally
    and billed to the company - employee does NOT claim these.
    We still record them (paid_by=Company) so they show in the audit trail,
    but they will never appear as a payable amount to the employee.
    """
    return [
        ExpenseLine(
            line_id="L001", claim_id="C001", trip_id=trip_id,
            date=date(2026, 6, 16), time=time(7, 55),
            merchant="IndiGo / MakeMyTrip", description="Flight PNQ-BLR 6E-6284",
            item_type="air_fare", category="Air Travel", amount=5016.00,
            city="Bengaluru", paid_by="Company",
            proof_ref="NF9119735", status="allowed",
            status_reason="Booked centrally, billed to company - not employee claim",
            source_email="04_flight_eticket.eml",
        ),
        ExpenseLine(
            line_id="L002", claim_id="C001", trip_id=trip_id,
            date=date(2026, 6, 20), time=time(19, 15),
            merchant="IndiGo / MakeMyTrip", description="Flight BLR-PNQ 6E-6491",
            item_type="air_fare", category="Air Travel", amount=5540.00,
            city="Bengaluru", paid_by="Company",
            proof_ref="NF9119735", status="allowed",
            status_reason="Booked centrally, billed to company - not employee claim",
            source_email="04_flight_eticket.eml",
        ),
    ]
def extract_hotel_lines(trip_id: str) -> list[ExpenseLine]:
    """
    Email 12 + hotel_invoice_1188.png: one hotel invoice, split into 6 lines
    (one per folio item), per policy 3.1 and 4.
    GST (12% combined CGST+SGST) is split proportionally per line so every
    line's gross amount is self-contained and audit-traceable.
    Reconciliation: sum of net amounts = 19,200 (matches invoice subtotal).
    """
    GST_RATE = 0.12
    invoice_no = "KPW/26-27/1188"
    src = "12_hotel_invoice.eml"

    raw_items = [
        # (line_id, date, item_type, description, net_amount)
        ("L003", date(2026, 6, 16), "room_charge", "Room Charge", 5750.00),
        ("L004", date(2026, 6, 17), "room_charge", "Room Charge", 5750.00),
        ("L005", date(2026, 6, 17), "laundry", "Laundry", 450.00),
        ("L006", date(2026, 6, 18), "room_charge", "Room Charge", 5750.00),
        ("L007", date(2026, 6, 18), "mini_bar", "Mini Bar", 380.00),
        ("L008", date(2026, 6, 18), "in_room_dining", "In Room Dining", 1120.00),
    ]

    # Policy 3.1: Bengaluru is Tier 1, limit INR 6,000/night room tariff (excl. tax)
    LODGING_LIMIT_TIER1 = 6000.00
    NON_REIMBURSABLE = {"laundry", "mini_bar"}  # policy section 4

    lines = []
    for line_id, ln_date, item_type, desc, net in raw_items:
        gross = round(net * (1 + GST_RATE), 2)

        if item_type == "room_charge":
            category = "Lodging"
            if net <= LODGING_LIMIT_TIER1:
                status, reason = "allowed", None
            else:
                status = "flagged"
                reason = f"Room tariff {net} exceeds Tier 1 limit {LODGING_LIMIT_TIER1}/night (policy 3.1)"
        elif item_type == "in_room_dining":
            category = "Meals"
            status, reason = "flagged", "In-room dining - check against daily meal limit (policy 3.3)"
        elif item_type in NON_REIMBURSABLE:
            category = "Disallowed"
            status = "disallowed"
            reason = f"Non-reimbursable item: {desc.lower()} (policy section 4)"
        else:
            category, status, reason = "Other", "flagged", "Unrecognized item type"

        lines.append(ExpenseLine(
            line_id=line_id, claim_id="C001", trip_id=trip_id,
            date=ln_date, time=None,
            merchant="Keys Prime Whitefield", description=desc,
            item_type=item_type, category=category, amount=gross,
            city="Bengaluru", paid_by="Employee",
            proof_ref=invoice_no, status=status, status_reason=reason,
            source_email=src,
        ))
    return lines

def extract_local_conveyance_lines(trip_id: str) -> list[ExpenseLine]:
    """
    Emails 06, 07, 08, 09, 10, 15 - all Uber rides.
    Key trap: 08 is a FAILED payment (ghost, never charged), 09 is the real
    receipt for that same ride, 10 is just an email resend of 09 - same
    ride, same amount, same time. Only ONE line should be created for it.
    Duplicate check uses date + time + amount + merchant (not bill number,
    since Uber emails have no invoice number) - matches your rule 3.
    """
    src_map = {
        "06": "06_uber_receipt_1.eml",
        "07": "07_uber_receipt_2.eml",
        "09": "09_uber_receipt_3.eml",
        "15": "15_return_cab.eml",
    }

    rides = [
        # (line_id, date, time, amount, route, source_key)
        ("L009", date(2026, 6, 16), time(5, 20), 1415.02, "Baner, Pune -> PNQ Airport", "06"),
        ("L010", date(2026, 6, 16), time(9, 52), 743.00, "BLR Airport -> Keys Prime Hotel", "07"),
        ("L011", date(2026, 6, 17), time(19, 35), 172.00, "Vertex Technologies -> Keys Prime Hotel", "09"),
        ("L012", date(2026, 6, 20), time(21, 5), 1229.02, "PNQ Airport -> Baner, Pune", "15"),
    ]
    # Note: email 08 (failed payment) and 10 (resend of 09) are deliberately
    # excluded here - never turned into lines at all. 08 never charged, so
    # there's no real expense. 10 is the same ride as 09, already counted.

    lines = []
    for line_id, ln_date, ln_time, amount, route, key in rides:
        lines.append(ExpenseLine(
            line_id=line_id, claim_id="C001", trip_id=trip_id,
            date=ln_date, time=ln_time,
            merchant="Uber", description=f"Ride: {route}",
            item_type="taxi_fare", category="Local Conveyance", amount=amount,
            city="Bengaluru" if "BLR" in route or "Vertex" in route or "Keys Prime" in route else "Pune",
            paid_by="Employee",
            proof_ref=f"uber-{key}", status="allowed", status_reason=None,
            source_email=src_map[key],
        ))
    return lines

def extract_business_entertainment_lines(trip_id: str) -> list[ExpenseLine]:
    """
    Email 11 + dinner_bill_18jun.png: dinner with Vertex procurement team,
    4 people. Per policy 3.5, hosted client meals are Business Entertainment,
    NOT meal allowance - and need HoD pre-approval if above INR 2,000.
    Bill total (from receipt image) = 2,255.00, which is above that
    threshold, so this line is FLAGGED for HoD approval, not auto-allowed.
    """
    return [
        ExpenseLine(
            line_id="L013", claim_id="C001", trip_id=trip_id,
            date=date(2026, 6, 18), time=time(21, 38),
            merchant="Spice Terrace", description="Dinner - Vertex procurement team (4 pax)",
            item_type="business_entertainment", category="Business Entertainment",
            amount=2255.00, city="Bengaluru", paid_by="Employee",
            proof_ref="4471", status="flagged",
            status_reason="Above INR 2,000 - requires HoD pre-approval confirmation (policy 3.5)",
            source_email="11_dinner_bill.eml",
        ),
    ]


def extract_rejected_lines(trip_id: str) -> list[ExpenseLine]:
    """
    Email 13: Deepa's Chennai ride, forwarded to Chaitanya to add to HIS claim.
    Rejected on two independent grounds - both worth recording:
    1. Policy section 4: "Expenses incurred by any person other than the
       claimant" are never reimbursed - this was Deepa's ride, not Chaitanya's.
    2. It doesn't match this trip at all - wrong city (Chennai, not Bengaluru)
       and wrong dates (12 May, trip is 16-20 Jun). This is the city/date
       cross-check against Trip we discussed earlier.
    """
    return [
        ExpenseLine(
            line_id="L014", claim_id="C001", trip_id=trip_id,
            date=date(2026, 5, 12), time=time(8, 10),
            merchant="Uber", description="Ride: Guindy, Chennai -> MAA Airport (Deepa Nair's trip)",
            item_type="taxi_fare", category="Local Conveyance", amount=640.00,
            city="Chennai", paid_by="Employee",
            proof_ref="uber-deepa-2211", status="blocked",
            status_reason="Not claimant's expense (policy §4) and outside trip city/dates (policy cross-check)",
            source_email="13_colleague_forward.eml",
        ),
    ]
    
def extract_all_lines(trip_id: str = "TR-2026-0616") -> list[ExpenseLine]:
    """
    Combines all 5 extractors into one list - this is what the rest of the
    app (policy_engine, API, screens) will call. One single entry point.
    """
    lines = []
    lines += extract_flight_lines(trip_id)
    lines += extract_hotel_lines(trip_id)
    lines += extract_local_conveyance_lines(trip_id)
    lines += extract_business_entertainment_lines(trip_id)
    lines += extract_rejected_lines(trip_id)
    return lines