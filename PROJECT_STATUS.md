# Project status — Hotel Management System

**Checkpoint:** 2026-11-26 · **Phase:** 1, discovery · **Gate:** [report submitted for owner review](docs/discovery_report.md); reference-image comparison blocked. The approved technology stack is a constraint; none of the proposed hotel policies or detailed designs is approved yet. Implementation is locked.

## Assignment board

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

## Phase and evidence ledger

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

## Current controls

- **Discovery checks executed:** verified the guide's five pages and SHA-256; queried the project agent registry and eight returned session models; parsed the project JSON, checked all 12 report sections (A–L), all 21 local Markdown links across six documents, and sample ignore rules for private research, backups and environment files. No private input file is a discovery deliverable.
- **Project tests:** no application, schema or migrations exist. Zero automated application tests run. Discovery checks do not certify security, backups, usability or accounting accuracy.
- **Known bugs:** no application defect can yet be assessed; unresolved policy and evidence gaps are tracked as blockers, not bugs.
- **Documentation:** [discovery report](docs/discovery_report.md), [decision register](docs/technical/development_decisions.md), [README](README.md), [contribution guide](CONTRIBUTING.md) and [team agreement](AGENTS.md) prepared. SRS, academic proposal/report, SDD, detailed ERD, migrations, final DOCX and deployment instructions belong to later gates.
- **Approvals:** owner to decide project direction before Phase 2; authorize later gates explicitly. No supervisor approval, fieldwork or hotel policies have been verified.

## Test evidence backlog — all application cases **not run**

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

## Blockers, decisions and next owners

| Priority | Owner / next action | Gates affected |
|---|---|---|
| Now | Owner: supply exact dashboard file/path/URL and reproduction permissions; UX: inspect the identified source. | Phase 1 visual comparison; Phase 4 interface approval |
| Now | Owner: accept or amend single property, staff UI, named rooms, nights, `Africa/Nairobi`, KES and sessions; authorize Phase 2 only. | Phase 1 exit → SRS |
| Now / before proposal | Student/supervisor: identify authorized investigation site, approved methodology/proposal, unit, project title, budget ceiling and dates. Supply private cover metadata privately. | Phases 2–3; Chapter 6.2 remains blocked without actual evidence |
| During requirements | Reception/manager, facilities and finance: confirm block/expiry/no-show rules, occupancy, inspections, order milestones, rates/taxes/receipt policy and revenue basis. Approve parking and seven-role matrix with object/field access. | SRS, SDD, DB design and tests |
| Before deployment | Owner/DevOps/Security: choose demo vs live scope, host, data-handling requirements, operating budget, RPO/RTO and tested recovery path. | SDD and release |

Next action after review: record the owner's decisions; then assign the SRS and authorized investigation preparation. Do not turn the preliminary entities into models before the detailed design review.
