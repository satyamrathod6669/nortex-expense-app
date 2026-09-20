from app.extraction import extract_all_lines, build_trip
from app.policy_engine import check_meal_limit, summarize_claim, payable_amount, required_approval_levels


def test_extraction_produces_14_lines():
    lines = extract_all_lines()
    assert len(lines) == 14


def test_duplicate_and_ghost_uber_excluded():
    lines = extract_all_lines()
    # Only 4 Uber rides belong to THIS trip (L009-L012).
    # L014 is also Uber but is Deepa's blocked ride from a different trip -
    # excluded here on purpose, since it's not part of Chaitanya's claim.
    trip_uber_lines = [l for l in lines if l.merchant == "Uber" and l.trip_id == "TR-2026-0616" and l.status != "blocked"]
    assert len(trip_uber_lines) == 4


def test_deepa_ride_blocked():
    lines = extract_all_lines()
    l14 = [l for l in lines if l.line_id == "L014"][0]
    assert l14.status == "blocked"


def test_hotel_disallowed_items():
    lines = extract_all_lines()
    disallowed = [l for l in lines if l.status == "disallowed"]
    disallowed_types = {l.item_type for l in disallowed}
    assert "laundry" in disallowed_types
    assert "mini_bar" in disallowed_types


def test_claim_totals_match_answer_key():
    lines = extract_all_lines()
    lines = check_meal_limit(lines)
    summary = summarize_claim(lines)
    assert summary["total_claimed"] == 26388.44
    assert summary["total_disallowed"] == 929.60


def test_payable_matches_answer_key():
    lines = extract_all_lines()
    lines = check_meal_limit(lines)
    trip = build_trip()
    summary = summarize_claim(lines)
    payable = payable_amount(summary["total_claimed"], trip.advance_amount)
    assert payable == 6388.44


def test_approval_levels_for_this_claim():
    lines = extract_all_lines()
    lines = check_meal_limit(lines)
    summary = summarize_claim(lines)
    levels = required_approval_levels(summary["total_claimed"])
    assert levels == ["Reporting Manager", "Head of Department"]