# Hotel A · investigation plan

**Status:** preparation only. The owner reports that Hotel A lacks an existing system and permits the study, but has not approved naming the hotel. No field findings or approved research method are supplied here. This plan is neither a report of visits nor an academic proposal. The [build contract](../system-design/build_contract.md) describes the software, not present practice.

**Decision sought:** which software defaults fit the work, which need changing, and what evidence would distinguish the two? A person may do several jobs, or a proposed function may not exist. Invite volunteers by the work they know; do not assume the application's roles are Hotel A's departments.

| Learn about | Suggested source, if the work exists | Decisions to check against the [SRS](../requirements/srs.md) |
|---|---|---|
| Arrival, identity and selling rooms | Someone who handles guest enquiries or admission; voluntarily walk through an invented booking | Necessary guest fields, promise vs enquiry, multi-room dates, cancellation, availability vs admission (FR-02–04) |
| Room release and repair | Someone who cleans or resolves room faults and someone able to explain release authority | Handoffs, inspection, blocking vs nonblocking work, unresolved exceptions (FR-04/05) |
| Food service and settlement | People who fulfil orders and who verify money, interviewed separately if appropriate | When an order is chargeable, who records a receipt, partial settlement and checkout decisions (FR-03/06/07) |
| Parking, access and overview | People familiar with parking, work assignment, accounts or shift summaries | Space reuse, information needed/withheld by role, reporting day and meaning of metrics (FR-01/08/09/10) |

## Collection sequence and safeguards

1. **Agree the scope privately first.** Student and supervisor confirm applicable review requirements, site liaison, allowed activities, voluntary recruitment, storage/access, retention/deletion and how participants can raise concerns or withdraw. Explain any point after which anonymous responses cannot be located. If these conditions are not settled, do not collect. Permission to study is not permission to identify staff, inspect live records, record audio, photograph the site or publish quotes.
2. **Invite without pressure.** Explain purpose, audience and the right to skip or stop. Obtain individual informed consent through the agreed private procedure. Do not invite guests or observe live transactions under this plan. Let staff respond without a manager present where feasible; do not share individual responses with employers.
3. **Collect only what is needed.** Offer the blank [questionnaire (Appendix A)](questionnaire.md), then optional [interview prompts (Appendix B)](interview_questions.md) for clarification. If separately permitted, ask for a fictitious walk-through using blank materials. Ask what happens now *before* showing the build default. A suggested feature or hypothetical answer is not an observed event.
4. **Protect the record.** Use non-identifying evidence codes. Keep notes/consent and any recontact key separate in approved, access-controlled storage; keep all completed instruments out of Git. No staff or guest names, contacts, exact stay details, IDs, plates, receipt references, screen captures or source records. If an identifying detail is volunteered, do not transcribe it. Never use real data to test the app.
5. **Check interpretation.** Summarize neutrally; invite correction without attributing one participant's account to another. Compare independent accounts where possible. Keep disagreements, missing roles, unanswered questions and sample limitations visible; do not turn missing answers into “no problem” or extrapolate to the entire hotel. Suppress combinations of duty, quote or count that might identify a person or site.

## Evidence to decision

Use the following fields in the **private** evidence ledger, not in this repository:

`evidence code | method and consent scope | de-identified statement | current practice / preference / hypothetical | basis: reported / seen in permitted walk-through / unresolved | contrary or missing evidence | participant correction if offered | affected FR and QA case`

A walk-through establishes only what was demonstrated. For each proposed change, the investigator records the supported claim and its limits; the product lead records **retain default / propose revision / insufficient evidence**. Only an accepted change updates the contract, requirement and test. If later authorized, use sanitized summaries for academic analysis; a software acceptance test is not field evidence. No participant counts, calendar, cost estimate or conclusion are asserted.
