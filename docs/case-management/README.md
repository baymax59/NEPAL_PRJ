# Knight Hawk Case Management: design documents

This folder explains **what Case Management is**, **how it fits together**, and **how it was built**.

**In one paragraph:** Knight Hawk Case Management keeps every police case as a **plain case**: the **permanent folders** made automatically when it is registered (from its type), the **files** in them (exhibits that never change, and notes and analyses that get a **new version** when corrected), a **team** the Investigator builds directly (a Sub Investigator, an Analyst, a Viewer: they join at once, with no invitation and no approval), **tasks**, **comments**, **links** to other cases, **signed reports**, and **one numbered, tamper-evident history** of everything that happens, which anyone on the case can check. **Nothing is ever deleted**: a mistake is corrected with a new version, or the wrong file is withdrawn with a reason and stays in the history. Administrators see every case, its team, its history and its audit trail. The **Similar Case Search** built in Steps 0–14 is one feature inside the case, called **Case Intelligence**: similar past cases, search, a timeline, offence sections and an assistant that answers from the case's own records.

**The design changed on 2026-11-10.** The module was first built (phases CM-1 to CM-8) like a GitHub repository: an original repository, clones, branches, commits, reviews and merges. The owner then asked for that to be removed completely and replaced by the plain case above, keeping the folders made at registration and letting the Investigator set the Sub Investigator and the Analyst. The rebuild is phases G-1 to G-5. **Document 13 is the current design.** Documents 01 to 05, 07 and 08 describe the earlier git-style design and are kept for the record: where they talk about repositories, clones, branches, commits, reviews, invitations or snapshots, read document 13 instead.

| # | Document | For | What it answers |
|---|---|---|---|
| 13 | [The plain case design](13-plain-case-design.md) | everyone | **The current design:** what a case is, how the permanent record is kept, the team and what each part may do, the data that changed, the build order, and every choice made on the way |
| 12 | [Roles and stations](12-roles-and-stations.md) | the user, administrators, developers | The seven roles, police stations, officer-ID rule, dashboards, hidden SHA-256 and simpler screens (built in phases R-1 to R-6) |
| 06 | [API contracts](06-api-contracts.md) | developers | Every endpoint, generated from the OpenAPI description ([`openapi.json`](openapi.json)), with examples |
| 09 | [Integration contract](09-integration-contract.md) | developers of the other Knight Hawk systems | How the Log Analyzer, CDR/IPDR, OSINT and alert systems add findings to cases (version 2.0: a `case_id`) |
| 10 | [Acceptance and traceability](10-acceptance-and-traceability.md) | the people who accept the system | The specification's 17-step scenario and required tests, traced to the plain design, and how to run every proof |
| 11 | [Production readiness](11-production-readiness.md) | the people who prepare for real records | Known limitations, the checklist, the order of work before the first real record |
| 01 | [What exists today](01-what-exists-today.md) | everyone | What was built in Steps 0–14, in plain words |
| 02 | [Feature correlation](02-feature-correlation.md) | everyone | How each existing feature fits into Case Management, and which requirements are new *(earlier design)* |
| 03 | [High-level design](03-high-level-design.md) | technical readers | The parts of the module, how they connect, which technologies and why *(earlier design)* |
| 04 | [Low-level design](04-low-level-design.md) | developers | How repositories, clones, commits, evidence, reviews and access control worked *(earlier design)* |
| 05 | [Database and ER diagram](05-database-er.md) | developers | Every table, its key fields, and which ones can never change *(earlier design; migration 0019 replaced the repository tables)* |
| 07 | [Security and integrity](07-security-and-integrity.md) | security and legal reviewers | Threats, controls, what immutability can and cannot guarantee, licences |
| 08 | [Implementation plan](08-implementation-plan.md) | everyone | The first build order in 8 phases *(earlier design)* |

**Status (2026-11-10):** built and tested.
- **CM-1 to CM-8** (first design): [`../steps/15-1-repository-core.md`](../steps/15-1-repository-core.md), [15-2](../steps/15-2-evidence.md), [15-3](../steps/15-3-collaboration-and-review.md), [15-4](../steps/15-4-screens.md), [15-5](../steps/15-5-case-intelligence.md), [15-6](../steps/15-6-integrations.md), [15-7](../steps/15-7-reports-and-governance.md), [15-8](../steps/15-8-demo-and-acceptance.md). Their notes describe the screens and endpoints of that design; the evidence, custody, integrity, reports, governance, integrations and Case Intelligence they describe all still exist, now on the plain case.
- **R-1 to R-6** (stations, roles, accounts, People screens, dashboards, hidden SHA-256): [`../steps/16-1-stations-and-roles-database.md`](../steps/16-1-stations-and-roles-database.md) to [16-5](../steps/16-5-dashboards.md).
- **G-1 to G-5** (the plain case): [`../steps/17-1-plain-case-core.md`](../steps/17-1-plain-case-core.md) (database and core), [17-2](../steps/17-2-plain-case-backend.md) (the rest of the backend), [17-3](../steps/17-3-plain-case-screens.md) (the screens), [17-4](../steps/17-4-plain-case-browser-checks-and-guides.md) (browser checks, the demonstration, the guides, the move of the real database).
- The user guides: [administrators](../guides/administrator-guide.md), [investigators](../guides/investigator-guide.md).

What remains before real records are your organisation's decisions: see document 11.

**Source of the requirements:** the "Master development prompt: Knight Hawk, GitHub-inspired immutable police case management system". Its examples (names, case numbers, folder names) are treated as **examples**, not fixed values. The module accepts **every type of case**, not only fraud or cyber crime. Its "GitHub-inspired" structure was replaced on request by the plain case design; document 10 traces every item of the specification to what the plain design provides.
