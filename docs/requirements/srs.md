# Software requirements — Hotel A staff application

**Purpose.** Staff must be able to answer three questions from the same records: *Can we promise these rooms for these nights? Can the guest enter them now? What was billed, and what money was actually received?* This specification covers the working application, not the university proposal or final report.

## Basis and boundary

- **Owner-reported:** Hotel A lacks an existing system and permits the study, but has not agreed to be named. This does not establish how work is done, which problems occur or what staff want. No field findings are supplied.
- **Required by the brief:** nine staff-facing modules and seven initial roles. **Build defaults:** the [build contract](../system-design/build_contract.md) sets one property, `Africa/Nairobi`, overnight dates, named physical rooms and KES. One reservation has one primary guest, one arrival/departure interval and one or more rooms. At admission all rooms share one folio (the stay's invoice). These are software decisions, not hotel policy approvals.
- **Outside this build:** guest self-service, multi-property inventory, payment initiation/gateways, automatic refunds and credit checkout. No budget, fieldwork dates or academic proposal are inferred. The [discovery report](../discovery_report.md) supplies the original requirement IDs; the build contract takes precedence over its candidate designs.

## Functional scope and traceability

| ID · module | Required staff outcome | Acceptance cases below |
|---|---|---|
| FR-01 Dashboard | See the local business date, scheduled arrivals/departures, available/occupied/reserved/dirty room counts, guest profile count, posted charges and collections; view recent reservations, orders, tasks and own notifications **only as authorized**. An unavailable feed is not a zero. | QA-12, QA-16 |
| FR-02 Guests | Register, edit and find a guest by name or hotel-issued reference. Preserve optional contact details and a history of reservations and actual arrival/departure; include payment history only under a billing grant. | QA-01, QA-13 |
| FR-03 Reservations & stays | Search availability, create pending or confirmed bookings, amend before arrival, confirm, cancel, check in and check out. Commit all rooms or none; retain the event history. A pending booking is not a hold. | QA-02–04, QA-08–09, QA-13–14 |
| FR-04 Rooms | Manage unique room numbers, active flag, capacity, nightly rate, facilities, description, optional image and category (Single, Double, Twin, Deluxe, Suite, Family). Show date-range availability separately from occupancy, inspection and maintenance. | QA-02–03, QA-13, QA-17 |
| FR-05 Housekeeping & maintenance | Dispatch eligible staff, work assigned cleaning tasks, inspect finished work, and open/resolve repairs. A blocking repair competes with bookings for the same dates; a nonblocking request does not reserve inventory. | QA-02, QA-09–10, QA-12–13, QA-17 |
| FR-06 Restaurant | Maintain menu items with category, description, image, price and availability. Assign and progress department orders; distinguish dine-in from room service. Snapshot item prices; charge exactly once when served, not when ordered. | QA-09, QA-11, QA-13–14, QA-19 |
| FR-07 Billing | Open a folio at check-in with agreed room rate × booked nights per room. Add served items and authorized extra charges. Record real received cash or externally confirmed bank, mobile-money or card tender, with reference and receiver; show itemized bill, payments, receipt and balance. | QA-07, QA-09, QA-13–14, QA-16, QA-19 |
| FR-08 Parking | Register named spaces and guest-linked vehicles, allocate an active space, release it and retain history. A space and a vehicle may each have only one active allocation. | QA-12, QA-15 |
| FR-09 Staff | Administer accounts, department, role and active status. Restrict assignment choices to eligible staff, preserve historical actors and restrict activity history. | QA-05–06, QA-10, QA-18 |

**FR-10 · shared access, not a tenth module.** Provide login, logout and password reset. Enforce active account, action, record and field scope on the server, including search results, counts, media, histories and dashboard projections. Deny undeclared actions. Trace: QA-05–06, QA-12, QA-18.

### Default role boundaries

All seven roles use the dashboard; its contents differ. Guests are affected parties, not account holders.

| Role | Grants and limits |
|---|---|
| Super Administrator | All operations, including staff creation, role changes and deactivation. |
| Hotel Manager | All operational grants, dispatch, inspection, finance and audit; **not** staff account administration. |
| Receptionist | Manage guests, reservations and parking; read rooms/availability and look up folios. No room catalog changes or financial posting. |
| Housekeeping Staff | Read and progress own assigned cleaning tasks. No dispatch, inspection or other worker's queue. |
| Maintenance Staff | Read and work assigned repairs. No general guest, cleaning or finance directory. |
| Restaurant Staff | Manage menu and department orders; minimal active-stay/room lookup for room service. No tender entry or guest directory. |
| Accountant | Access invoices, record charges and confirmed tenders, reconcile receipts. No general guest directory or plates. |

## Acceptance cases

These are **expected results, not executed tests**. Examples are synthetic. For a rejection, check the database after the request as well as the response. QA-01–12 retain the IDs in the [discovery tracker](../../PROJECT_STATUS.md).

| Case | Setup → action → observable result |
|---|---|
| QA-01 · identity | Save a duplicate guest reference or normalized nonblank email → reject it. Save two guests with the same name but distinct keys → retain separate histories. A blank reference is generated, not reused. |
| QA-02 · nights | For a blocking claim `[A,B)`, confirm another stay beginning on B → allowed. Overlap one night on the same room with a booking or blocking repair → reject; a pending claim alone does not exclude that night. |
| QA-03 · contention | On two independent PostgreSQL connections confirm pending bookings for rooms A+B and B+C on the same nights → one confirmation commits. From a fresh connection, the loser remains pending and its unshared room is free. Reverse the winner and force rollback; a rejected amendment must also leave its original allocation intact. |
| QA-04 · input | Submit missing, equal or reversed dates, or no rooms → field error, no reservation or hold. |
| QA-05 · permission | Anonymous client requests protected data; restaurant operator posts a payment; login or authenticated write lacks CSRF → deny each at the API, without a business write. |
| QA-06 · session | Bad or disabled login → no authenticated session. Reset requests do not reveal whether an account exists. A valid reset permits the new password, not reuse of its token; logout prevents further protected access. |
| QA-07 · tender | KES 4,000.00 room + 850.25 service − 2,000.00 received = **2,850.25 due**. Replay the same tender/reference → same receipt, no second payment. Conflicting reuse, nonnumeric, excess precision, zero, negative and overpayment → no new receipt. |
| QA-08 · cancellation | Cancel before admission → release the booking's inventory, retain its history. Attempt check-in → no occupancy or folio. |
| QA-09 · refused departure | Request checkout without an active stay, with an open room order, or with an unpaid balance → no closure, turnover, fabricated payment or partial change. |
| QA-10 · assignment | Select an eligible assignee, deactivate them before saving the assignment → reject at save; earlier work keeps its actor. |
| QA-11 · order validity | Withdraw a menu item before an order containing it is saved → no partial order or posting. For a multi-room stay, omit the room or choose a room outside that stay → reject room service. |
| QA-12 · scope | Assign cleaner A one task, B another → A can progress the first, cannot list, fetch or change the second or infer it from totals. Check equivalent repair scope, own notifications, authorized media, minimal restaurant stay lookups and absence of plates/financial details for unrelated roles. |
| QA-13 · complete stay | Confirm two rooms, then change catalog rates. Admit both → one folio at the agreed rates. Serve room service to a selected booked room, record a confirmed tender, settle and depart → timestamps and history, closed folio, each room dirty with exactly one pending turnover task. Early departure releases only unused nights, without reducing the agreed charge. |
| QA-14 · service vs closure | Race a room order against checkout; repeat a serving request. Existing open orders prevent closure; a closed stay cannot acquire a late order/charge. A successful serve and its uniquely sourced lines commit together, never against the next guest. |
| QA-15 · parking | Compete for the same space with different vehicles, then for the same vehicle across spaces → one active allocation in each race. Release → end time retained, space reusable. Reject duplicate vehicle registration by normalized plate; do not allocate an inactive space. |
| QA-16 · reporting | Confirm a two-room reservation due today, before admission → one scheduled arrival, two reserved rooms, no increase in occupancy. Post a charge on an older invoice and a partial payment today → Nairobi-day **billed** rises only by the line amount, **collected** only by the tender. Distinguish an empty permitted result from failure or an omitted metric. |
| QA-17 · readiness | Progress pending → assigned → in progress → completed. Attempt admission before inspection → reject. Manager inspection does not override occupancy or a blocking repair. Resolve a repair → only its own block ends. An ineligible room prevents the entire check-in. |
| QA-18 · administration | Super Administrator changes/deactivates a staff profile; Hotel Manager attempts the same → only the former succeeds. Disabled staff cannot act or receive new work; historical events remain. |
| QA-19 · dine-in and extras | Serve a dine-in order → standalone invoice, no invented guest/stay. Add a referenced extra service to an open folio → server computes quantity × unit price; retry does not duplicate the line. Neither action records a payment. |

**Test sources, not pass evidence:** [inventory](../../backend/tests/test_inventory.py) and [two-connection contention](../../backend/tests/test_contention.py) cover booking boundaries; [access](../../backend/tests/test_access.py), [operations](../../backend/tests/test_operations.py) and [settlement](../../backend/tests/test_settlement.py) exercise scoped actions, rollback and tender retries. The [browser suite](../../frontend/e2e/) checks the staff-facing flows. Record actual runs and any uncovered cases separately.

## Quality and release evidence

| Requirement | How to verify before acceptance |
|---|---|
| NFR-01 Integrity & audit | Use PostgreSQL for race/rollback cases. Check fixed two-decimal KES strings, source keys and actor/event in the same transaction as the change. No routine DELETE of operational history. |
| NFR-02 Privacy & access | Exercise a permitted and a denied action per role, including direct API and private image access. Inspect audit summaries/logs for unnecessary guest, tender or credential data. |
| NFR-03 Usability | Walk booking, tender and assigned-work flows with the keyboard and at 360 CSS px wide. Check labeled controls, visible focus, textual status/errors and distinct loading, empty, conflict and success states. No mock fallback data. |
| NFR-04 Operation | Verify paginated lists, measure availability/dashboard on a stated workload, and restore a matched database and media backup in isolation. Reconcile room claims, receipts and image access. No live load, service level or recovery target is evidenced. |

**Still to validate with the hotel:** what constitutes its business day, exception/inspection authority, credit/deposit/refund policy, parking practice, access/retention and whether these roles reflect its work. Record any change to a default against a requirement and acceptance case. Use the [research plan](../research/investigation_plan.md) for evidence and the [system design](../system-design/system_design.md) for implementation boundaries.
