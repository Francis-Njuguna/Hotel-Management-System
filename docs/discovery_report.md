# Hotel Management System — project discovery report

**26 November 2026 · Review copy · Owner approval pending**

The project starts from an empty repository and a verified five-page university guide. The proposed first demonstration follows a guest from booking to checkout and a room through turnover. **The dashboard reference image has not been identified.** Visual direction below comes from the written brief; it is not a screenshot analysis or a visual sign-off.

Evidence labels: **Verified** means inspected during this checkpoint. **Required** means specified in the brief or university guide. **Proposed** means a team recommendation for review. **Open** means the hotel, student, supervisor or project owner must supply evidence or decide. See the [task tracker](../PROJECT_STATUS.md) and [decision register](technical/development_decisions.md).

## A. Understanding of the project

**Required outcome:** a working hotel operations system that staff can demonstrate and developers can test, together with a Chuka University proposal/report and a **separate** engineering System Design Document (SDD). A rendered screen, an invented survey result or a mock successful payment cannot satisfy acceptance.

The front desk needs to know two different things: **can this room be sold for the requested nights, and can the arriving guest enter it now?** Finance likewise needs to distinguish an amount charged from money received. Those distinctions drive the schema, API, permissions and dashboard.

| Discovery evidence | Verified result and scope |
|---|---|
| [Repository](https://github.com/Francis-Njuguna/Hotel-Management-System) | Public, default branch `main`. GitHub reported size 0; `git ls-remote` returned no refs. The initial clone had only `.git`, no tracked or untracked project files, no application, fixtures, migrations, CI, documentation or project agent definitions. This report describes that initial state, before the discovery commit. |
| Inputs | The initiating OpenCode message listed zero file attachments. A local file matching the named university guide was located in Downloads and read in full (see I). No dashboard asset could be identified from the repo, message or bounded project/input search (see B). |
| Local tooling | Git 2.54.0.windows.1; OpenCode 2.3.0; Python 3.12 and 3.14 available; Node 26.4.0/npm 11.17.0 present. Local PostgreSQL x64 18 service reported running, client `psql` 18.4 and a `btree_gist` extension control file were present. No database login, role, installed database extension, production compatibility, deployment or restore is implied. |
| Team and research | Reviewed the local OpenCode agent/model configuration and queried the running service by location without publishing provider credentials. Specialist reports inform this proposal. No hotel field records, student registration, approved methodology, quotations or supervisor approvals were supplied as evidence. |

Stakeholders to consult: guest (affected party), receptionist, housekeeper/inspector, maintenance lead, restaurant operator, cashier/accountant, manager/owner, access administrator, student investigator and academic supervisor. Guests do not need application accounts in the proposed staff-facing first release.

## B. Analysis of the reference design

**Source status:** no image was present in the initial checkout or attached to the initiating message. A filename-focused search covered likely Desktop/Projects, Downloads, Documents and Pictures input locations. Generic captures without an HMS identifier were not treated as the reference. Please attach the original or identify its exact path/URL and usage rights. Its layout, branding, typography, colors and visible metrics cannot be confirmed from the brief alone.

| Written direction | Proposed treatment to verify against the original |
|---|---|
| White/light-grey surfaces, blue accents, sidebar, rounded cards, restrained shadows and clear tables | Use the desktop sidebar for modules. Put arrivals, departures and room exceptions before trend charts. Show the date/property context and link each metric to a filtered worklist. Distinguish a successful zero from a failed or loading query. |
| Guest and room administration; room and food image cards | Use a searchable list for repeated operations, a labeled detail view for history, and image cards for browsing. Provide alternative text and a fallback when no image exists. Use text plus an icon or badge for status, not color alone. |
| Orders and cleaning on mobile | Provide a short role-specific task queue, compact navigation and one clear next action per item. Stack labeled fields instead of shrinking desktop tables. Preserve filters and focus after back navigation. |
| Common interactions | Reuse sidebar/header/navigation, statistic card, table/pagination, search/filter, validated form, modal/confirmation, status badge, notification and chart/table alternative. Keep draft input on validation/conflict errors; expose retry, empty and success states. |

**Gate:** UX compares desktop, tablet and mobile task flows with the actual reference, noting which elements were retained or changed and why. At 360 CSS px, a cleaner must be able to find an assigned room and update it without a horizontally scrolling form. These are proposed checks, not observed image features.

## C. Proposed technology stack

| Layer | Direction |
|---|---|
| Frontend | **Required:** React, strict TypeScript, Vite, Tailwind CSS, React Router. **Proposed:** Zod for form validation, Lucide for icons, Recharts only where a chart adds information over the underlying table. Feature folders own workflows; shared components own presentation. |
| API | **Required:** Python, Django, Django REST Framework, Django ORM/auth/permissions and migrations. **Proposed:** a supported Django LTS/DRF pair, `psycopg`, versioned REST, and OpenAPI generated from the reviewed API (candidate: drf-spectacular). Pin compatible, supported versions at setup; the installed local versions are not a production lockfile. |
| Storage and hosting | **Required:** PostgreSQL. **Proposed:** one database and one application release; HTTPS reverse proxy, static Vite build, Django production web process, private durable media and restricted PostgreSQL. No Redis/Celery unless measured caching or durable background work warrants them. |
| Verification | Pytest/pytest-django against **PostgreSQL**, Vitest/React Testing Library and Playwright for cross-domain paths; Git/GitHub for change review. Domain tests, constraints and API tests precede UI sign-off. |

## D. Multi-agent team and responsibilities

**Verified orchestration:** the initial home location exposed `build`/`plan` as visible primaries and `general`/`explore` as callable children; title/summary/compaction are hidden maintenance agents. The active primary was `build`, explicitly running `agentrouter-direct/gpt-6.2-astra` (medium). Filesystem, shell/Git, web, session and asynchronous subagent tools were available; the MCP resource/template catalog was empty. No GitHub-specific integration was assumed. Children start with fresh context and return completion reports to the parent.

Before the repo had profiles, the principal delegated four read-only briefs: UX to `explore`; academic evidence, product rules and data invariants to separate `general` children. After [project-local configuration](../opencode.json), the running `/api/agent` registry at **this checkout** returned the following additional roster. `hms-principal` explicitly selects the same Astra model; each of the ten child profiles has **no model override**, so inherits the invoking session model. No eleven distinct models or simultaneous implementers are implied.

| Role/profile | Responsibility and handoff |
|---|---|
| Principal · `hms-principal` | Own decisions, review source and specialist evidence, lock file ownership, update tracker and obtain approvals. This already-running discovery session retained `build`; new project sessions have the named primary as default. |
| Product · `hms-product` | Stakeholders, stories, policy matrix and acceptance criteria → SRS. Product work in this checkpoint used `general`. |
| Architect · `hms-architect` | Domain ownership, dependencies, API and transaction boundaries → SDD/ADRs; called for independent discovery review. |
| UI/UX · `hms-ux` | Reference comparison, information hierarchy, responsive tasks and accessibility → interface specification. Reference search used `explore`. |
| Database · `hms-data` | ERD, cardinalities, dictionary, constraints, indexes and migration review → DB design gate. Invariant study used `general`. |
| Backend · `hms-backend` | Domain services, DRF, auth, transactions and API tests → reviewed contract implementation after design approval. |
| Frontend · `hms-frontend` | Feature flows, forms, API states and component tests → integrated views after contracts and visual review. |
| Security · `hms-security` | Independent control and privacy review → findings, retest and eventual release report; called for discovery review. |
| QA · `hms-qa` | Independent requirements-to-test traceability, PostgreSQL races, browser journeys and regression evidence; called for discovery review. |
| DevOps · `hms-devops` | Reproducible environments, deployment, media, logging, backup and restore; called for recovery-design review. |
| Documentation · `hms-docs` | Guide compliance, instruments, bibliography, technical documents and checked DOCX output. Source audit used `general`. |

All eight discovery assignments had no writable paths. The principal alone integrated their reports and verified the recorded model for each actual child session: `agentrouter-direct/gpt-6.2-astra`, variant `medium`, in all eight. The ten named specialist profiles deny edit, shell, Code Mode and nested delegation during discovery; grant narrowly scoped permissions only after the appropriate later gate. See the [team agreement](../AGENTS.md).

## E. Preliminary system architecture

**Request path:** staff browser → one HTTPS origin → static React client or `/api/v1/` → DRF authentication, permissions and serializer → application workflow and domain services → one PostgreSQL transaction. Restricted media has its own access checks. In development Vite can proxy API calls to Django; in production the origin serves the built client. Separate frontend/backend source does not require cross-origin sessions.

**Ownership:** `accounts`/`staff` own identity and employment; `guests` owns profiles; `rooms`/inventory own room metadata and the claims calendar; `reservations` owns commercial lifecycle and actual stays; `housekeeping` owns cleaning/inspection; `maintenance` owns work orders; `restaurant` owns orders; `billing` owns charge/payment/receipt records; `parking`, `notifications` and `audit` own their respective histories. A reporting selector reads from these domains and returns authorized aggregates. A workflow coordinator calls the relevant domain services; no business-critical write relies on a second browser request, dashboard refresh or asynchronous notification.

**Three transactions that determine correctness:**

1. **Book or amend.** Validate date range and capacity, lock old/new rooms in a stable order, recheck calendar and insert/update all room claims atomically. The DB exclusion rule protects against another writer even after a successful availability search. A conflict returns `409 room_conflict`, preserving the previous reservation and every sibling allocation.
2. **Check in or out.** Check-in requires an eligible room line, vacancy, the agreed cleaning release and no blocking maintenance. Atomically record actual arrival and history. Checkout re-reads the stay, orders and invoice under lock, applies the agreed balance/open-order rule, ends occupancy, preserves consumed nights and opens exactly one turnover task. It does not issue a fictional payment or mark the room sale-ready.
3. **Serve and post.** Accept restaurant orders before they are billable; proposed milestone is **served**. For room service, validate the active stay and authorized occupant at ordering and again at posting. The serving transition and uniquely sourced charge are one write transaction. All commands affecting closure use the same stay lock and a documented lock order. If checkout wins the race, reject the late charge or route it for authorized reconciliation; never charge the next occupant. Retry of a committed posting returns its original result.

**Interface convention (illustrative, not a signed API):** `GET /api/v1/rooms/availability/`, `POST /api/v1/reservations/`, `POST /api/v1/reservations/{id}/confirm/`, `POST /api/v1/stays/{id}/checkout/`, `POST /api/v1/orders/{id}/serve/` and `GET /api/v1/dashboard/`. Use paginated scoped collections, bounded search/filter/sort, field errors, stable error codes, human-readable detail and a request ID. Use `201` for creation, `400` for invalid data, `403` for disallowed actions (also DRF session-only unauthenticated denial), `404` for a record outside the authorized lookup scope and `409` for stale state or collisions. Document every action, role, response and error in OpenAPI at design time.

**Authentication recommendation:** Django server-side sessions, a Secure/HttpOnly/SameSite session cookie and CSRF verification on unsafe methods **including login**. Rotate on login, POST logout, apply expiry/invalidation, use Django password hashing/reset tokens, generic rate-limited reset responses and a verified recovery channel. Role grants use Groups/Permissions; every collection, detail, transition, nested record, dashboard and export also checks row and field scope. Browser navigation reflects permissions for usability only. JWT adds refresh and revocation without a demonstrated need for an independent client. See [ADRs 002–006](technical/development_decisions.md).

## F. Preliminary database entities and relationships

These are candidate relations, **not Django models or an approved schema**. Phase 4 must specify every column/type, PK/FK, uniqueness, delete policy, transition, index and migration dependency and produce a reviewed Mermaid ERD before code.

| Owner | Candidate relationships and rules |
|---|---|
| Accounts and staff | User M:N Django Group; Group M:N Permission. Department 1:N StaffProfile; User 1:0..1 StaffProfile. Deactivation revokes access while preserving the actor on financial and operational events. No additional role truth in the frontend. |
| Guests and stays | Guest 1:N Reservation as booking contact. Reservation 1:N reservation-room lines at confirmation; each line has 0..1 Stay for the proposed no-room-move baseline. Stay M:N Guest via StayOccupant; validate the ordering guest belongs to the room-service stay. Record planned dates separately from actual arrival/departure. Consider ReservationParty if named companions are required before arrival. |
| Inventory | RoomCategory 1:N Room; Room 1:N RoomImage; Room M:N Facility through RoomFacility. Unique room number in property, positive capacity and nonnegative price. Categories: Single, Double, Twin, Deluxe, Suite and Family. Inventory claim is the calendar row for **either** a reservation-room line **or** a blocking maintenance window; exactly one owning purpose/source. Room 1:N claims. Avoid duplicate date/status sources across parent reservation and calendar. |
| Rate and reservation history | Room line 1:N AgreedNightRate with unique service night; price at booking is not overwritten by later price edits. Reservation/line 1:N StateTransition (actor, time, prior/new state, reason). Explicit release and retained history; protect consumed nights on early departure. |
| Housekeeping and maintenance | Room 1:N CleaningTask and MaintenanceRequest. Tasks have eligible staff assignment and ordered progress/inspection events. A repair request need not block inventory; a blocking window does. An emergency creates an incident and escalates conflicting claims/occupants for authorized relocation, not silent cancellation. |
| Restaurant | FoodCategory 1:N MenuItem; menu image/description, fixed-precision current price and active flag. Order 1:N OrderItem → MenuItem; snapshot order price and quantity. Assignment → active staff. Dine-in can be standalone; room service → active Stay, from which eligible occupants and room follow. Order status history records who changed what. |
| Billing | Invoice 1:N InvoiceItem; post a specific room-night, order line or additional service once. Link invoices to the liable guest/reservation/stay as applicable; standalone restaurant bills need not create fake hotel guests. Proposed baseline: each received Payment applies to one Invoice; Receipt uniquely identifies its Payment. Enforce a stable tender/reference key, positive amounts, atomic posting and protected corrections. Split folios, credits, reversals and deposit allocation need policy sign-off. |
| Parking | Guest → Vehicle association (ownership/use policy to confirm); ParkingAllocation links Space, Vehicle and guest/stay for a time interval. Retain release history. Enforce at most one overlapping active allocation per space **and** per vehicle. |
| Notifications and audit | Notification → recipient User (and read time); AuditEvent → actor, subject reference, action, time and reason. Restricted append-only events; no passwords, tokens, identity documents or payment payloads in logs. Record business changes in the same transaction. |

**Critical DB rule:** finite, nonempty room intervals with `arrival < departure`; use `[arrival, departure)` in hotel-local calendar days. A conditional PostgreSQL GiST exclusion using `btree_gist` and equality on room plus overlap on interval must see the **blocking state on the claim row**, not a join to a parent reservation. Confirmed stays/closures share the same calendar; drafts and released unused lines do not block. Do not release all consumed nights on checkout. Independently serialize occupancy/inspection changes on the room; one open stay per physical room. Exact representation of source exclusivity and the open-stay key must be proved in the reviewed physical design. If scalar equality support cannot be provisioned on the host, evaluate unique room-night claims before implementation.

**Normalization and access paths:** keep stable reference data, M:N links and business events separate; immutable price snapshots capture a transaction-time fact, not a second current price. Compute balances and dashboard counts from source facts. Propose indexes for guest lookup keys, claim ranges, active stays, assigned task/status, order status/time, invoice source/tender references and unread notifications. Justify new indexes against measured query plans. Protect financial/history FKs from destructive cascades; design retention/anonymization separately from operational deletion.

## G. Functional requirements and candidate acceptance cases

These examples are observable requirements for a future SRS. The figures in examples are **synthetic test inputs**, not property statistics or actual receipts.

| ID / module | Required behavior and a proposed acceptance check |
|---|---|
| FR-01 Dashboard | Query today's scheduled check-ins/outs, available, occupied, reserved and cleaning rooms, total guests, financial summaries, recent reservations, orders, housekeeping activity and notifications. Agree business date, whether actuals are shown beside expected arrivals, distinct rooms/guests, status inclusions and reporting window. Change a qualifying record: the authorized tile and its drill-down reconcile. An empty database shows zero/empty states. Posted charges and cash received are labeled separately. |
| FR-02 Guests | Register, edit, search, filter and show booking, payment and actual check-in/out histories to authorized roles. Reject a duplicate approved unique key and make creation retries safe; flag likely matches rather than merging by name or assuming relatives cannot share a phone. Two different guests with the same name retain separate histories. |
| FR-03 Reservations | Create, modify, confirm, cancel, check in/out and retain history; search availability before commitment. A 10–12 stay can be followed by 12–13. A second 11–13 claim on that room conflicts. Two concurrent confirmations cannot both win; cancellation releases only eligible inventory. Invalid dates and checkout without an open stay leave no changes. |
| FR-04 Rooms | Register/edit rooms, six categories, capacity, rate, descriptions, images, facilities, maintenance and inventory/occupancy views. Editing the current rate does not rewrite a prior agreed charge. A room may be vacant and yet unavailable to admit a guest. |
| FR-05 Housekeeping | Create jobs, assign eligible active staff, track **Pending → Assigned → In Progress → Completed → Inspected** and handle failed inspection/rework per policy. Record maintenance requests and blocked work independently. Refuse assignment to an inactive worker. Completing cleaning alone does not clear an open repair or occupied stay. |
| FR-06 Restaurant | Manage categories, descriptions, images, prices, availability, orders, assignment and history. Support **Pending, Confirmed, Preparing, Ready, Served, Cancelled** with authorized transitions; cancellation points need sign-off. Reject unavailable items without partially inserting an order. Repeated serving of the same room order cannot duplicate its charge. |
| FR-07 Billing | Produce invoices for room, restaurant and extra services, record real tenders, issue receipts and provide balances, payment history and financial summaries. KES 4,000.00 room + KES 850.25 service gives KES 4,850.25 charged; verified receipt of KES 2,000.00 leaves KES 2,850.25 due. Replaying the same tender does not reduce the balance again. Reject zero/negative payment amounts; no funds are inferred from a checkout, a button press or a browser callback. |
| FR-08 Parking | Register spaces, vehicles and guest associations; allocate, release, query availability and view history. Under the numbered-space proposal, a second active vehicle cannot take an occupied space; two simultaneous attempts leave one allocation. |
| FR-09 Staff | Register profiles, assign departments and roles, activate/deactivate accounts and retain activity history. Disabled staff cannot act or be newly assigned; historical work keeps the correct actor. A manager cannot grant themselves super-administrator access. |
| FR-10 Access | Secure login/logout/reset and backend grants for **Super Administrator, Hotel Manager, Receptionist, Housekeeping Staff, Restaurant Staff, Accountant, Maintenance Staff**. Proposed: reception handles stays/parking; facilities staff act on assigned work; restaurant handles orders but cannot record payments; finance reconciles payments. Default deny. The final role/action/object/field matrix, including inspection and cash authority, requires owner approval. |

## H. Non-functional requirements and verification

| Quality | Candidate release evidence |
|---|---|
| Consistency and auditability | Two independent PostgreSQL connections contend for the same free room; exactly one conflicting allocation commits and the losing multi-room request leaves no partial claims. Race order posting vs checkout and payment vs retry. Audit/history, charge lines and balances agree after commit and rollback. SQLite or two sequential HTTP calls cannot establish this. |
| Security and privacy | Anonymous and unauthorized requests are denied; assigned-only lists, details, counts and media disclose no neighboring worker's records. Test invalid login, CSRF, expiration, logout/reset, disabled staff and privilege changes. ORM parameterization, validated sorting, safe React text rendering, restricted upload types/sizes and image decoding/re-encoding, sanitized audit logs, per-action throttling and deployment secret management are design requirements. Review file authorization and data retention, including backups. |
| Usability and accessibility | Target WCAG 2.2 AA, subject to stakeholder approval: keyboard-operable flows, visible focus, programmatic labels, text error summary and field messages, meaningful captions, normal-text contrast ≥4.5:1. Verify at phone, tablet and desktop sizes; test slow, empty, failed and conflicting responses as well as success. No accessibility certification is claimed. |
| Performance | Establish representative room, stay and staff counts with the hotel. Illustrative design target only: p95 ≤2 s for availability search/dashboard at 25 simultaneous staff and 10,000 historical stays on an agreed host. Record data volume, hardware and method; inspect query plans/N+1 behavior. Never satisfy a target by hardcoding statistics. |
| Operability and recovery | Least-privilege runtime DB role, separate migration privileges, HTTPS, redacted structured logs/request IDs, error and backup alerts. Protect DB **and media** in encrypted off-host backups. Restore a matched set into isolation, check booking/finance baselines and media integrity; measure loss window/time to usable service against owner-approved RPO/RTO. Rehearse rollback without losing post-upgrade payments. |
| Maintainability | One owner per domain, explicit service entry points, reviewed migrations, OpenAPI contracts, version lockfiles, traceability from requirement to verification, CI and independent QA/security reviews. A feature is accepted only with business logic, authorized API, integrated UI and applicable passing tests. |

## I. Academic proposal structure and source reconciliation

**Primary source (read 5/5 pages):** Chuka University, Department of Computer Science, `ACSC 483  and COSC 482 END OF SEMESTER PROJECT DOCUMENTATION.pdf` (two spaces after `483`), 346,636 bytes; SHA-256 `1b50ceaac6bbc8f3a5cc7348fc602787fabaeb78912de1aa5dbe406488c9a72b`. A documentation reviewer checked page renders and text; the principal independently checked file identity and all five pages' layout-preserving text. No raw PDF or logo is redistributed here.

| Guide evidence | Outline and production instruction |
|---|---|
| p. 1, project and assessment | Topic identification, proposal, investigation/analysis/requirements and design; the guide calls for combining the three phase documents. Plan proposal + investigation + design within the university's **Phase 1 report**, separate from this project's eight delivery phases. Oral panel **30%**, documentation **70%**, and attendance signature after presentation/hand-in. The title says `ASCS 483: SOFTWARE PROJECT 1`; the body/footer/filename say `ACSC 483`. The other title is `COSC 482: COMPUTER SYSTEMS PROJECT 1`. Confirm the student's registered code and name for the singular cover field. |
| pp. 2–3, preliminary pages | Cover: **CHUKA UNIVERSITY** with official logo, **FACULTY OF SCIENCE AND TECHNOLOGY**, **DEPARTMENT OF COMPUTER SCIENCE**, student name, student registration number, unit code: unit name, project topic, supervisor. Then **Table of Contents → List of Tables → List of Figures**. Obtain identity and logo privately; do not infer them from a GitHub username. |
| p. 3, Chapter 1: Introduction | **1.0 Introduction; 1.1 Background to the Study; 1.2 Problem Statement; 1.3 Proposed Solution; 1.3.1 Aim; 1.3.2 Objectives; 1.4 Significance of Project.** Frame the aim around reliable coordination of booking, room readiness and settlement. Until fieldwork, describe the local problem as a question to investigate, not an observed failure. |
| p. 3, Chapter 2: Literature Review | Compare published research and documented systems: reservation conflict handling, staff handoffs, room service/billing and fit with the investigated context. Cite feature evidence and limits of comparison; absence of a feature from a marketing page is not evidence the product lacks it. Use APA in-text citations and references. |
| p. 3, Chapter 3: Methodology | Use the approach in the approved proposal. If none exists, propose iterative, incrementally verified development plus a consent-based case study (interviews, questionnaire and approved observation). Explain selection, collection, analysis and limitations. Do not claim instruments were administered. |
| p. 3, Chapters 4 and 5 | **Resources Required / Budget:** separate available equipment, estimated KES costs, quantities/basis and dated actual quotations. **Time Plan:** day-by-day schedule **and Gantt chart** with dependencies, milestones and deliverables. Dates, budget ceiling and quotations are not provided. |
| p. 3, Chapter 6 (complete report) | **6.1 Introduction:** purpose and actual method consistent with Chapter 3. **6.2 The Current Existing System / Environment:** evidence of actual workflows and gaps. **6.3 The Intended System:** map each verified shortcoming to proposed behavior and functional/non-functional requirements. No local findings have been verified. |
| p. 4, Chapter 7 and end matter | **7.1 Introduction; 7.2 Process Flow Design; 7.3 Interface Design; 7.4 Database Design** (ERD, normalization, table specifications and relationships). **7.X** only under supervisor guidance. **Appendices precede References**: Appendix A Questionnaire, Appendix B Interview Questions, other justified evidence; APA references for works actually used. The brief requests A and B even though the guide calls appendices optional. |
| p. 5, formatting/submission | Times New Roman, 12 pt, black; main headings centered, remaining content justified; line spacing 1.15; caption/label and reference tables/diagrams; each chapter starts on a new page; page numbers bottom center; spelling and grammar check; APA; **“Single Page Printing”** and **spiral binding with clear front cover**. Follow these explicit rules rather than copying the guide's own bottom-right footer. APA edition, margins and preliminary numbering scheme are not specified. |

**Starting sources verified for later Chapter 2 review, not completed literature findings:** Buhalis, D., & Leung, R. (2018). Smart hospitality—Interconnectivity and interoperability towards an ecosystem. *International Journal of Hospitality Management, 71*, 41–50. [DOI](https://doi.org/10.1016/j.ijhm.2017.11.011) (bibliographic metadata checked). The [Oracle Hospitality help center](https://docs.oracle.com/en/industries/hospitality/opera-cloud/) and [QloApps user guide](https://docs.qloapps.com/) are primary vendor sources for product comparisons, not independent performance evidence. Retrieve/document versions and consult the full research sources when writing the proposal.

**Research and document handoff:** after approval, prepare the investigation plan and instruments under `docs/research/`; obtain authorization/consent before collection. Keep raw evidence private. Assign evidence IDs and link findings → requirements → design → tests. Generate `docs/academic/project_proposal.md` and DOCX at Phase 3; `system_investigation.md`, `complete_project_report.md` and final DOCX on actual evidence. Update and visually check TOC/list fields, captions, section breaks, page numbering and print layout in Word or a compatible renderer. These publication steps have not been run at discovery.

## J. Risks and assumptions

| Status / risk | Consequence and resolution owner |
|---|---|
| Open: image identity and rights | No image-specific comparison or visual approval. Owner supplies exact source; UX records its provenance before design sign-off. |
| Open: field access, academic identity, approved methodology and dates | Chapter 6.2, final cover and academic schedule cannot be truthfully completed. Student/supervisor confirm site access, evidence handling, unit and deadlines. No confidential details needed in a public issue or PR. |
| Proposed: one property, physical rooms, overnight inventory, `Africa/Nairobi` | Multi-property, category-only sales, room moves and hourly use change keys, constraints or scoping. Manager/reception must decide before the ERD. |
| Open: business date, holds/no-shows, inspection/overrides, early departures and outage displacement | Availability, staffing, KPIs and admissions may otherwise disagree. Product and hotel leads walk a same-day turnover with a blocking repair. |
| Open: deposits, tax/rounding, room-service posting, cash authority, credit checkout, adjustments/refunds | Financial statements can double-count or misstate revenue. Accountant signs off examples and evidence; distinguish charge, actual tender and correction. No gateway in baseline. |
| Open: hosting, extension privileges, recovery, retention and public-repo boundaries | Local binaries do not establish production readiness. DevOps checks hosting cost/rights and proves restore; security defines least privilege, approved retention and redacted publication. |
| Delivery risk: nine modules before a fixed but unknown deadline | Build cross-domain vertical slices; demonstrate the core stay first, then expand. Prioritization is not permission to omit a module. Agree milestones and document scope changes. |

## K. Implementation roadmap and gates

| Phase | Dependency → reviewable deliverable → exit check |
|---|---|
| 1. Discovery (current) | Inspect repo/sources/running OpenCode → this report, tracker, ADRs → owner reviews direction; image comparison outstanding. |
| 2. Requirements analysis | Direction approved → SRS, stakeholder stories, policy/permission matrix, KPI definitions and acceptance tests; prepare research protocol → reviewed by owner, with unknowns assigned. |
| 3. Academic proposal | Agreed scope/methodology, budget basis, accessible sources and calendar → Chapters 1–5, daily Gantt and proposal MD/DOCX → academic structure and rendering checked. |
| 4. System design | Reviewed requirements and proposal → separate SDD under `docs/system-design/`, `docs/diagrams/` (context, architecture, use cases, data/process/activity flows, complete ERD), dictionary, REST contract, security and deployment design → architect, data, product and owner review; **no models before this gate**. |
| 5. Implementation | Approved SDD → (a) identity/RBAC, room catalog and guests; (b) calendar/reservations under concurrency; (c) stays, inspection/maintenance, baseline billing and checkout; (d) restaurant, parking and staff-management completion; (e) role-specific dashboard/read models → each slice includes API, integrated UI and tests. Assignment and migrations have one owner. |
| 6. Quality assurance | Integrated increments → independent QA and security reports, fixes/retests, performance results, integrity and recovery drill. Reconcile UI/role scope against database truth on synthetic test fixtures; block release on critical failures. |
| 7. Academic documentation | Actual investigation plus implemented design → complete Chapters 6–7, appendices, references, diagrams, full MD/DOCX; compare academic summary with the detailed SDD and check print layout. |
| 8. Final review and handover | Verified modules + academic/technical evidence → HTTPS deployment, rollback/restore and demonstration instructions, final report and panel/print checklist. Release requires observable business and operational evidence. |

The technical SDD will cover the 28 requested areas: objectives/scope/stakeholders; context/use cases/activity/data/process flows; frontend/backend/database architecture and rationale; ERD, normalization, dictionary; API/auth/authz/security/errors; monitoring, recovery, deployment and testing. It is not a substitute for Chapter 7. The full development/testing/deployment guides and environment template follow the reviewed implementation. **No delivery dates or spending commitments are inferred.**

## L. Questions requiring decisions

**For the next gate:**

1. Can you attach the dashboard reference or give its exact local path/authorized URL? May it be reproduced in the private academic submission, and if so may any version be published on GitHub?
2. Approve or amend the planning baseline: **one property, staff-only UI, named physical rooms, overnight reservations, KES, same-origin Django sessions**. Do you authorize **Phase 2 requirements analysis only** on this basis while any image/fieldwork gaps are resolved?
3. Which hotel/site or anonymized case is authorized? Is there an existing approved proposal/methodology? What permission exists to interview/observe staff, and who can validate finance and room policies? If access is pending, keep local findings pending.
4. Which registered unit/code/title, supervisor-approved project title, proposal/defense dates and budget ceiling apply? Supply identity/registration/supervisor and official logo privately when preparing the cover. Confirm APA edition, margins or preliminary page numbering only if the department has additional rules.

**For the requirements workshops, before detailed design:**

5. What is the business-day cutoff? Are holds, no-shows, group bookings, moves, early/late stays or day use needed? Who can inspect/release a room or authorize relocation around emergency maintenance?
6. When does an order become billable? Who records or verifies each tender? Which taxes, deposits, reversals/refunds or credit checkouts are permitted? How should management distinguish income, billed charges, actual cash received and amounts owing?
7. Are parking spaces numbered, capacity-based or chargeable? Which staff may see guest/payment history, work others' queues, inspect rooms, grant roles or export data? What retention and anonymization rules apply?
8. Is the deployment a local panel demonstration or a live hotel service? What host, load, uptime expectations, backup loss/recovery limits, media handling and ongoing operating budget can the owner support?

**Stop condition:** the principal will record the owner's decisions in the tracker before advancing. Requirements approval alone does not authorize modeling, migrations or implementation.
