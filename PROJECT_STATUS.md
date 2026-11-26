# Project status — Hotel Management System

**Checkpoint:** 2026-11-26 · **Current direction:** owner requested the working system after reviewing discovery. Build the anonymized Hotel A application using the specified stack. Academic submissions and still-unknown field findings are deferred. The owner reports no existing system; this is not evidence about particular manual procedures. The original discovery checkpoint below is historical.

## Software delivery and verification — 2026-11-26

All nine staff areas are implemented. Start the [local demo](README.md#run-the-local-demo); the optional starter catalog has six rooms, one synthetic guest, menu items and parking spaces. Setup creates no booking or tender. The following observations are from the integrated application with synthetic fixtures.

| Gate | Evidence observed by the principal |
|---|---|
| PostgreSQL schema | Migrated the separate PostgreSQL **18.4** cluster on loopback. `manage.py check`: 0 issues. `makemigrations --check --dry-run`: no changes. SQL inspection showed `btree_gist` 1.8, a GiST exclusion on `room_id` and half-open `daterange(start,end,'[)') WHERE blocking`, and independent unique indexes on active parking space and vehicle. |
| API contract | `manage.py spectacular --validate --fail-on-warn` passed after adding explicit enum names; `pip check` found no broken requirements. |
| Targeted business regressions | **36 passed**, plus **21 subtests**, on PostgreSQL. Includes booking contention in both commit orders and forced rollback; concurrent settlement and parking; two-room check-in → room-service posting → final settlement → checkout → inspection; verified recovery and the targeted reception folio. [Traceability matrix](backend/tests/README.md). |
| Full backend release gate | At software commit `6be169c`, the entire `backend/` suite ran on a fresh, migrated PostgreSQL 18.4 test database: **132 passed, 75 subtests passed**, zero errors, failures or skips (636.89 s). The JUnit report includes both reset/disable lock orders. An issued link remained invalid after reactivation, and disabling first prevented issuance. Both corrected streamed-image tests passed. |
| Frontend | `npm run build` passed (TypeScript + Vite); **74/74 component and service tests** passed across 15 files, including seven delayed-session regressions. The browser harness type-checked separately. Earlier runs were 67/67 before the session fix and 72/74 with two one-second component-query timeouts. An increased async-query budget preserved the assertions in the passing retest. |
| Demo isolation | Principal reran **12/12** launcher guards in an isolated Python process. A conflicting inherited DB, proxy or mail target did not launch child processes; the local configuration was accepted. Production settings separately rejected a disabled STARTTLS flag in an import-only check. |
| Main demo smoke test | Through `http://127.0.0.1:5187` on the Windows workstation: anonymous bootstrap → administrator sign-in → dashboard (six available rooms, one guest, **KES 0.00 billed / 0.00 received**) → logout → anonymous bootstrap. PostgreSQL accepted connections on the project's `127.0.0.1:55488`; the web and API listeners were loopback only. |
| Real browser | After the session fix, all **six regular Edge/Playwright journeys passed** on a fresh PostgreSQL database (3.7 min; the separately gated keyboard case was skipped in this run). The write journey booked and admitted one room, observed HTTP 409 for unpaid checkout, recorded one synthetic received tender, checked out and verified the closed folio, dirty room and pending turnover. The others covered dashboard data, catalog/search recovery, session protection and mobile navigation/logout. |
| 360 CSS px keyboard | On a separate fresh fixture, **1/1 passed** in installed Edge. Using the keyboard, the operator confirmed a prepared booking, saw an unpaid-checkout refusal, reviewed and acknowledged the synthetic cash amount before recording it, and located its receipt. The assigned housekeeper completed cleaning with manager inspection still required. The test checked visible focus and horizontal overflow on the exercised controls and surfaces. |
| Native matched restores | After **each** browser run, the runner stopped both scratch web processes and restored a `pg_dump` archive and matching media in isolation. Each restore matched **11 database checks**, including hashes over every room-claim and receipt row, and the relative path and SHA-256 of one image. Restored billed/received totals: **KES 3,600.00 / 3,600.00** (regular) and **KES 25.00 / 25.00** (keyboard). Both scratch fixtures were removed. |
| Packaged cold start and restore | [GitHub Actions recovery run 45852055494](https://github.com/Francis-Njuguna/Hotel-Management-System/actions/runs/45852055494) passed the [six-stage drill](deploy/rehearse.py) at `3a9473c` on Ubuntu. A second Compose project restored into separate, empty DB/media volumes. Model row counts, image inventory, the receipt identifier and **KES 24.70 billed / 10.00 received** matched. On source and restore, restaurant staff retrieved the same JPEG via both protected URLs; the accountant and anonymous client were denied. The Windows Docker Desktop rehearsal was interrupted; the packaged result is from CI. |
| Hosted regression checks | [GitHub Actions verification run 45852057182](https://github.com/Francis-Njuguna/Hotel-Management-System/actions/runs/45852057182) at `3a9473c`: both `api` (including PostgreSQL migration, schema and tests) and `web` (production build, E2E type-check and component tests) succeeded. |
| Synthetic read timings | On Windows / PostgreSQL 18.4, the [workload probe](backend/benchmarks/workload.py) used a fresh test database with **60 rooms, 600 guests and 1,200 confirmed stays** across 40 nights. One authenticated client used fresh loopback sockets; after three warm-up pairs it measured 30 reads per endpoint. **Dashboard:** median **198.7 ms**, nearest-rank p95 **314.5 ms**. **Dated availability** (alternating 25-row and five-row pages): median **191.1 ms**, p95 **288.6 ms**. Response counts were asserted; these timings describe one warm, single-client sample. |

**Independent reviews:** QA accepted the native QA-01–19 gate at `6be169c` after reconciling the full backend and current frontend results with its source review. Security closed its two original local blockers (reset/revocation and launcher isolation) and the shared-workstation display finding. These dispositions cover a trusted, single-workstation demo with synthetic data.

**Regression history:** narrowed reception’s invoice register; required signed-in mailbox verification; bounded permission grants by canonical role; applied per-account session versioning; removed upload metadata carried through image conversion; corrected rollback boundaries and two-actor race fixtures. The initial backend integration recorded 107 passes, 10 failures and 19 errors, including a database outage. A subsequent full run had 127 passes, three failures and 71 passing subtests; two media tests finalized already-consumed responses twice. Their assertions now check Django's own stream closure. Another cluster interruption affected pre-handover runs; the later fresh 132-test run above supersedes them.

The first post-restart keyboard attempt timed out on the **anonymous API request through Vite**, before Playwright started. The rehearsal now waits for the proxy to return the expected anonymous JSON as well as waiting for the shell. The earlier workload attempt expired before reporting measurements. The browser, restore and timing figures above are from completed, separate runs.

**Operational boundary:** these are local software results. Live TLS and SMTP, operator training and policy acceptance, off-host backup/retention objectives and the original UI screenshot have not been validated by Hotel A. The university report still needs authorized field evidence.

## Build assignments and integration gates

The principal owns contracts, project settings, integration, migrations, dashboard, verification and publication. Review the physical model before model creation. All work targets the single-property staff application; policy defaults are engineering choices, not claims of hotel approval.

**B1 design review accepted:** lead checked the 27-relation dictionary and ERD, including the room-claim XOR, exclusion predicate, two partial parking keys and financial locks. Amendment: add `InvoiceItem.created_at` for the posting date rather than coupling the financial report to audit rows. B3–B5 model writers released. B4 is split among three separate children, one app each (housekeeping, restaurant, parking). No two agents share a writable app.

| Task / owner | Exclusive writable paths | Input → acceptance / verification |
|---|---|---|
| B1 Data engineer | `docs/system-design/database_design.md`, `docs/diagrams/erd.mmd` | Frozen contract → typed dictionary, normalized relations, constraints, indexes and contention review before models |
| B2 DevOps | `deploy/`, `compose.yaml`, `docs/technical/deployment_guide.md` | Environment contract → reproducible, same-origin launch and recovery instructions; configuration checked by lead |
| B3 Backend (lodging) | `backend/apps/lodging/` | Reviewed DB/API contract → guest and room catalog, multi-room booking/admission/checkout, history, conflict/rollback tests |
| B4 Backend (operations) | `backend/apps/housekeeping/`, `backend/apps/restaurant/`, `backend/apps/parking/` | Same contract → authorized task, work order, restaurant and parking lifecycles; tests for rejected transitions |
| B5 Backend (finance) | `backend/apps/billing/` | Same contract → decimal invoices, additional charges, real tender records and idempotent receipts; reconciliation tests |
| B6 Frontend (shell) | `frontend/src/app/`, `frontend/src/styles/`, `frontend/src/features/dashboard/`, `frontend/src/features/auth/`, `frontend/src/main.tsx` | Reviewed endpoints → responsive navigation, login/recovery, live overview, accessible UI; type/build/browser checks |
| B7 Frontend (front desk) | `frontend/src/features/frontdesk/` | Contracts → guests, rooms, availability, reservation and stay workflows; build/browser verification |
| B8 Frontend (operations) | `frontend/src/features/operations/` | Contracts → housekeeping, repairs, menu/orders and parking; build/browser verification |
| B9 Frontend (finance/staff) | `frontend/src/features/office/` | Contracts → invoices, actual tender entry, receipts, staff, history; build/browser verification |
| B10 Security and QA | `backend/tests/`, `frontend/e2e/`, independent read-only security review | Integrated source → PostgreSQL/API and browser evidence; review CSRF, scopes, uploads, logs, fix/retest defects |
| B11 Documentation/product | `docs/requirements/`, `docs/research/`, `docs/system-design/system_design.md`, `docs/diagrams/` except ERD | Brief → traceable SRS, technical flows, honest research instruments; verify vs app before handover |

**Integration review assignments:** B10 browser QA additionally owns `frontend/e2e/stay.spec.ts` for an explicit opt-in *disposable-database* write journey; acceptance is an actual staff browser booking/admission, folio settlement and turnover check against the cloned development DB. Principal owns the isolated launcher, checks and schema fixes. B6 connects recovery mailbox verification only after B10 security's finding. These assignments add no production data.

**Pre-handover reviews:** Security (read only; writable paths **none**) rechecks core identity, the role ceiling, image processing and billing scopes against the original findings and the loopback deployment boundary. QA (read only; writable paths **none**) reconciles the executed database/API, browser and restore evidence with QA-01–19. Each reviewer must distinguish local-demo acceptance from live operational approval, identify any remaining local blocker, and return a disposition to the principal for independent checking.

**B2 Compose rehearsal:** DevOps owns `deploy/rehearse.py` only. Input: the packaged stack, `deploy/snapshot_check.py` and recovery runbook. Output: an opt-in executable synthetic cold-start and isolated DB/media restore check using unique Compose projects and private generated secrets. Principal runs it on the local Docker context and records what actually completes.

**Security rework:** Principal owns reset issuance, activation-version changes and PostgreSQL regression evidence. B6 owns `frontend/src/services/session.tsx` and `frontend/src/services/session.test.tsx` only: ensure a superseded identity read cannot rebind the screen/operator after logout or operator change (delayed-response component tests). Launcher engineer owns `scripts/{run_local,native_db,local_db,demo_config,test_demo_config}.py` only: validate one explicitly loopback configuration for all demo subprocesses and reject stale overrides before migrations, seeding or proxying. Principal independently runs the launcher guard tests, the PostgreSQL regression and the UI build/test gates; security then reviews the integrated fixes.

**Nonfunctional checks:** Browser QA owns only `frontend/e2e/keyboard.spec.ts`: a disposable, opt-in 360 CSS px keyboard walkthrough of booking, reviewed tender and assigned cleaning, with focus and horizontal overflow checks. Use real staff APIs only for disposable fixtures; do not change the regular six journeys. Principal checks source, types and actual Edge result. Principal owns the bounded synthetic workload probe for dashboard and dated availability; report collection method, workload and observed results rather than a hotel-wide performance promise.

## Owner answers — discovery follow-up

1. **Proposal structure:** the owner confirmed the five-page Chuka University guide reviewed in discovery is the intended source.
2. **Registered unit:** the owner selected **ACSC 483 — Software Project 1** for the proposal cover.
3. **Proposal status:** the student is starting from the university guide and has no written HMS proposal yet.
4. **Investigation site:** the student reports selecting a hotel and receiving its permission to conduct the study. Fieldwork status is still open.
5. **Hotel anonymity:** the student reports that the hotel has not agreed to be named. Use **Hotel A** in the proposal, report and shared project materials.

## Archived discovery assignment board

The principal is the sole writer in this checkpoint. All specialist assignments are advisory, with exclusive writable paths **none**. The artifact is a seven-part report returned to the principal for integration into `docs/discovery_report.md`; the acceptance column defines how to verify it. Scope: staff-operated HMS using Django/DRF, React/TypeScript and PostgreSQL; nine operational modules and seven initial roles.

| ID / owner | Objective and inputs | Acceptance / check | State |
|---|---|---|---|
| D01 Principal | Inspect target remote, checkout, current session inputs, config and models | Inspect refs and entire checkout, query running service and project roster | Baseline verified |
| D02 UX via `explore` | Locate likely hotel image, compare desktop/mobile interfaces to brief; no attachment in initiating message | Inspect identifiable source or report bounded search and uncertainty | Search reviewed; original requested, visual review blocked |
| D03 Docs via `general` | Inspect named local university PDF, exact section order, formatting, evaluation requirements | Account for every page; lead independently reads source | Accepted: 5/5 pages, hash and structure verified |
| D04 Product via `general` | Translate brief into observable front-desk/room/financial outcomes | Back-to-back stay, checkout, bill vs cash, permission boundaries; no invented interviews | Accepted as proposals; hotel validation pending |
| D05 Data via `general` | Preliminary relational structure; interval, maintenance, finance invariants | Inspect constraint placement and transaction boundaries; two-session test design | Accepted for design review; no schema approved |
| D06 `hms-architect` | Review cross-domain contracts, deployment shape, consistency in checkout/room service using approved stack | Identify owners, atomic boundary, one alternative and trigger for change; no models or code | Accepted with posting-milestone reconciliation below |
| D07 `hms-security` | Review proposed same-origin staff sessions, role scope, upload/privacy boundaries of public repo | Clear default-deny behavior and verifiable design acceptance checks; no live target testing | Design criteria accepted; operational sign-off pending |
| D08 `hms-qa` | Independent design of end-to-end verification from brief | Cover twelve named failure cases, reproducible concurrency fixture and role checks; distinguish planned/executed | Design coverage reviewed; additional parking/dashboard cases retained |
| D09 `hms-devops` | Review deployment/recovery assumptions; local PostgreSQL 18 service and 18.4 client observed; remote public/empty initially | Specify extension preflight, same-origin delivery, test restore/rollback and identify decisions; no system changes | Accepted as release-gate proposals, not a recovery result |
| D10 Principal | Reconcile reviews, record proposals/risks and deliver discovery-only snapshot | Check sources, project agent registry, links, scoped file list; verify publication against remote ref for handoff | Discovery deliverables assembled; owner review pending |

The named profiles are project-local. D02–D05 began with the available built-in agents before the project profiles existed. Eight child sessions returned reports. The principal checked session model metadata: all eight used `agentrouter-direct/gpt-6.2-astra`, variant `medium`, as did the active principal session. The running registry confirmed one named primary plus ten named specialists. Backend and frontend engineers have no implementation assignment at this gate.

## Principal review and architectural decisions

| Reports | Independent check or reconciliation | Disposition |
|---|---|---|
| D02–03: sources | Lead checked initial Git tree/refs and message attachment count. Verified the named PDF's bytes/hash and read all pages' text, including the contradictory title and submission footer. The generic capture filenames do not establish an HMS image. | Use the guide, not an invented template. Mark image comparison and cover metadata open. See report B and I. |
| D04–05: operations/data | Traced adjacent nights, early release and the example KES 4,850.25 charge less KES 2,000.00 received. Checked Django's documented range exclusion mechanism: a parent-only predicate would not protect room-line inserts. | Keep committed booking/closure on a shared room calendar, with actual stays and readiness distinct. Reject a single `room.status` or `invoice.paid` as the source of truth. |
| D06: order vs checkout | The proposed application must support pending restaurant orders; charging unconditionally on creation would conflate an accepted order with fulfilled service. Traced posting first vs closure first under the same stay lock, including idempotent retry. | Recommend a synchronous **serve-and-post** command and an explicit policy for pending orders at checkout. The billing milestone and credit checkout require owner sign-off. |
| D07: access boundaries | Checked DRF session behavior, including CSRF protection for login, and compared list/aggregate vs detail/field scope for assigned room A and unrelated room B. | Require paired allowed/denied API cases. Proposed timeout/upload limits are not approved values. |
| D08: QA coverage | Compared the twelve named scenarios with the brief. An absence of UI controls is not evidence of authorization. Added parking allocation contention and dashboard reconciliation to the future suite. | Coverage design accepted; no runtime test conducted. |
| D09: operations | Distinguished `psql` client version, running Windows service and extension-file presence from actual target DB privileges or an installed database extension. | Require real migration, isolated DB+media restore and rollback evidence. No provider, budget or recovery objective assumed. |

Decision record: [ADR-001–007](docs/technical/development_decisions.md). Mandated: modular monolith, approved stack, decimal KES and no simulated payments. Proposed: same-origin session auth, half-open room claims, per-stay serialized posting/checkout, separate readiness axes, one property and minimal infrastructure. No architecture change or release has been approved.

## Archived discovery phase and evidence ledger

| Phase | Deliverable / prerequisite | Status |
|---|---|---|
| 1 Discovery | Report, reviewer feedback, decision requests and tracker | Submitted; image review pending and gate not signed |
| 2 Requirements | SRS, stakeholder map, policy and permission matrix, measurable acceptance cases; needs owner direction | Pending |
| 3 Proposal | Source-compliant Chapters 1–5 in Markdown and DOCX, references, cost basis and daily Gantt; needs methodology and calendar | Pending |
| 4 System design | Separate SDD, diagrams, normalized ERD and complete dictionary, REST/OpenAPI contracts; review **before models** | Pending |
| 5 Implementation | Independently tested API/UI increments after SRS, proposal and design review | Locked |
| 6 QA | Independent PostgreSQL/API/UI/E2E/security findings and retest evidence | Pending |
| 7 Academic completion | Chapters 6–7 grounded in actual investigation and implemented design; final DOCX/MD | Pending |
| 8 Handover | Acceptance, restore drill, deployment, demo and required academic packaging | Pending |

## Controls at the discovery checkpoint

- **Discovery checks executed:** verified the guide's five pages and SHA-256; queried the project agent registry and eight returned session models; parsed the project JSON, checked all 12 report sections (A–L), all 21 local Markdown links across six documents, and sample ignore rules for private research, backups and environment files. No private input file is a discovery deliverable.
- **Project tests:** no application, schema or migrations exist. Zero automated application tests run. Discovery checks do not certify security, backups, usability or accounting accuracy.
- **Known bugs:** no application defect can yet be assessed; unresolved policy and evidence gaps are tracked as blockers, not bugs.
- **Documentation:** [discovery report](docs/discovery_report.md), [decision register](docs/technical/development_decisions.md), [README](README.md), [contribution guide](CONTRIBUTING.md) and [team agreement](AGENTS.md) prepared. SRS, academic proposal/report, SDD, detailed ERD, migrations, final DOCX and deployment instructions belong to later gates.
- **Approvals:** owner to decide project direction before Phase 2; authorize later gates explicitly. No supervisor approval, fieldwork or hotel policies have been verified.

## Test evidence backlog as recorded at discovery

| Future evidence | Expected boundary / owner |
|---|---|
| QA-01 duplicate guest | One approved identity key cannot create two profiles; same name alone cannot cause a merge. Product/Data/QA. |
| QA-02–04 reserved room, concurrent booking, invalid dates | Overlap rejected, adjacent stays permitted; two independent DB transactions race and a fresh connection checks the committed result. Reverse winner, force rollback, and check losing multi-room requests create no partial claims. Missing/equal/reversed dates leave no hold. Data/Backend/QA. |
| QA-05–06 unauthorized API, invalid login | Denial for anonymous and out-of-role clients; invalid credentials establish no session; reset/login responses do not enumerate accounts. Security/QA. |
| QA-07 invalid payments | Zero, negative, nonnumeric or disallowed precision do not issue a receipt. Verify stable tender references and decimal reconciliation. Billing/QA. |
| QA-08–09 cancellation, premature checkout | Cancelled booking cannot check in. An attempt to check out without an active stay changes neither room nor bill nor cleaning queue. Backend/QA. |
| QA-10 disabled assignee | Staff disabled after selection cannot receive the task on save. Backend/QA. |
| QA-11 unavailable food | Item withdrawn before order commit produces neither partial order nor charge; order fulfillment and invoice posting roll back together on failure. Restaurant/QA. |
| QA-12 unauthorized record | Assigned housekeeper can update A; B is absent from list, direct detail, totals, download and mutation. Cover all seven roles and scoped histories. Security/QA. |
| Cross-domain evidence | Synthetic guest → reservation → actual stay → room service → payment record → checkout → dirty/inspected room. Reconcile dashboard to source DB, run parking contention and browser tests incl. keyboard/mobile/error/double submit. Test funds are fixtures only. QA/UX. |
| Release evidence | Production-like deployment/migration checks, HTTPS and secret controls, private media, measured restore/rollback/reconciliation. DevOps/Security/QA. |

## Historical blockers and decision requests at discovery

| Priority | Owner / next action | Gates affected |
|---|---|---|
| Now | Owner: supply exact dashboard file/path/URL and reproduction permissions; UX: inspect the identified source. | Phase 1 visual comparison; Phase 4 interface approval |
| Now | Owner: accept or amend single property, staff UI, named rooms, nights, `Africa/Nairobi`, KES and sessions; authorize Phase 2 only. | Phase 1 exit → SRS |
| Now / before proposal | Student/supervisor: confirm fieldwork status at Hotel A, project title, methodology, budget ceiling and dates. Supply private cover metadata privately. | Phases 2–3; Chapter 6.2 remains blocked without actual evidence |
| During requirements | Reception/manager, facilities and finance: confirm block/expiry/no-show rules, occupancy, inspections, order milestones, rates/taxes/receipt policy and revenue basis. Approve parking and seven-role matrix with object/field access. | SRS, SDD, DB design and tests |
| Before deployment | Owner/DevOps/Security: choose demo vs live scope, host, data-handling requirements, operating budget, RPO/RTO and tested recovery path. | SDD and release |

Next action after review: record the owner's decisions; then assign the SRS and authorized investigation preparation. Do not turn the preliminary entities into models before the detailed design review.
