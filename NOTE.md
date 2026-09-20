TRAVEL EXPENSE REIMBURSEMENT: NOTE 
by
Satyam Rathod



WHAT I UNDERSTOOD
After a trip, an employee re-types bills into a form (25-30 minutes, error-prone), then chases Finance. 
I built the settlement side: a claim with lines checked against policy NTX-HR-POL-11, routed to the right approvers, verified by Finance and paid, with a full audit trail. I used Chaitanya's trip as the test case: claimed 26,388.44, disallowed 929.60, advance 20,000, payable 6,388.44.

ASSUMPTIONS I MADE
- Approval level is decided by the employee's own spending, not the whole trip cost. So this claim needs Suresh and Meera, then Finance.
- Finance is the payer. Finance verifies every claim, then marks it paid. Payment runs (10th/25th) are not modelled.
- Admin is read-only: sees all claims, policy reference and people, and cannot approve or pay (separation of duties).
- Send back returns the claim to the employee and restarts the whole approval chain on resubmission.
- The 2,255 dinner is flagged for Head of Department approval, not blocked.
- Flights are company-paid, shown as memo lines and never reimbursed. Laundry and mini bar (plus their tax) are disallowed.


WHAT I BUILT
Password login with server-side sessions, per-claim approval chains, a state machine for status changes, role and ownership checks on every endpoint, screens for employee, approver, Finance and Admin, and 42 automated tests. Deployed on Render.

WHAT I LEFT OUT (deliberately, for time)
- Reading the 15 emails and 2 receipts live. The claim lines are prepared data typed from them, including the duplicate Uber and the colleague's ride being excluded by hand. A real version would parse the emails and use an AI model for messy text.
- The pre-trip request, trip approval and advance steps.
- Excel export of the Settlement Form; dinner attendee-name entry.
- Checks not yet enforced: 7-day submission window, proof required on every line, Tier 2 and 3 city limits, duplicate-bill detection in code.




WHERE IT BREAKS
- Money uses floating-point numbers; production needs exact decimals.
- The meal daily cap disallows the whole day's meals when over the limit, rather than only the excess. Not triggered by this dataset.
- Excluded items (such as Deepa's ride) are not shown on screen.
- Shared demo password, no CSRF token, SQLite on temporary disk that resets on restart.

WHAT I CAUGHT REVIEWING AI-WRITTEN CODE
1. The first backend trusted whoever the browser claimed to be, so any manager could approve any claim. I replaced it with real sessions and per-claim approvers, and added tests that try to break it.
2. Finance's "paid" step had no role check, so any user could mark a claim paid. Fixed.
3. The tests only checked typed-in data against typed-in answers, so they proved little. I added permission, workflow and race-condition tests.
4. The extraction file was hard-coded rather than parsing emails. I could not fix it in time, so it is stated above.

