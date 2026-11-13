# 11. Known limitations and production-readiness checklist

For the people preparing Knight Hawk Case Management for real police records: what it does not do yet, and what must happen before real records go in. This is deliverable 20 of the master specification.

The system is **built and tested**:
- every phase CM-1 to CM-8 is done, and the case was rebuilt as a plain case in phases G-1 to G-5 ([13-plain-case-design.md](13-plain-case-design.md): folders, files, a team the Investigator builds directly, one numbered history);
- the 17-step acceptance scenario passes as one automated test and in a browser (document 10).

It is **not yet ready for real police records**. Most of what remains are decisions only your organisation can take, and they are listed below.

## 1. How to see where you stand

```powershell
cd C:\case-search\backend
uv run python -m scripts.readiness_check
```

The check reads the decisions form ([../DECISIONS.md](../DECISIONS.md)), the settings and the database, and lists every go-live item as **done** or **OPEN**, with what to do. It never prints a secret. Real records may go in only when it says "READY".

## 2. The checklist

### Decisions your organisation must sign (DECISIONS.md)

| Decision | About |
|---|---|
| D1 | the legal basis for processing case data, and who authorises access |
| D3, D5 | protected identities; who may see what (roles, clearances) |
| D4, D15 | retention periods; legal holds; how an approved disposal is actually carried out (the system records decisions, never deletes) |
| D6, D7, D12 | where the system runs; the network, the organisation's certificate and HSTS; where the project and its data live |
| D8 | backups: where they are kept, how often, and how a restore is checked |
| D10 | how the local AI assistant may be used (its answers cite the records and must be checked by a person) |
| D11 | an independent security review (the internal one is [../SECURITY_REVIEW.md](../SECURITY_REVIEW.md)) |
| D13 | the organisation, the case-number prefix (the placeholder is KH) and the roles |
| D14 | the evidence storage: write-once protection that administrators can't switch off from the application |
| D16 | two-step verification, who holds the keys, the application's database login |

### Settings and checks a computer can verify (the readiness check)

| Item | What "done" means |
|---|---|
| A fresh database | No fictional demonstration case in the production database. Case records can't be deleted, so a database that holds KH-2026-0001 is for demonstration and training only (CM-8) |
| Demonstration accounts | `demo.admin`, `demo.supervisor`, `demo.arun`, `demo.meena`, `demo.dev` absent or deactivated (CM-8) |
| Officers creating their own login | Decide whether the log in page may offer it (`SELF_REGISTRATION`, on by default): a new login is view-only and only for an officer in the register, but whoever knows an officer's ID and exact name could claim it first (security review F8). Enter the real officers in the register before anyone signs up |
| Development accounts | The live application has one account, the Super Admin `superadmin`. Keep its password in a password manager, then delete `.dev-credentials.txt` (or change the password): the check reports it until then |
| `CM_TEST_SOURCE=false` | the fictional integration test source is off |
| `CM_MFA_REQUIRED=true` | administrators and supervisors use two-step verification for privileged actions (turn it on once they have set it up under Account) |
| Keys | `CM_CHECKPOINT_KEY` (signs audit checkpoints) and `MFA_KEY` (protects two-step secrets) set, 32 characters or more. The checkpoint key is held by someone other than the database administrators |
| The application's database login | `POSTGRES_APP_USER` / `POSTGRES_APP_PASSWORD` set: the application can't delete case records |
| The worker | its daily checks (audit checkpoint, audit chain, evidence sweep) ran in the last 48 hours |
| TLS | the organisation's certificate instead of Caddy's own authority; HSTS turned on in `deploy/Caddyfile` |
| Backups | a recent backup, proven restorable, outside cloud-synced folders |
| Folders | the project, the evidence store and the backups outside cloud-synced folders |
| Secrets | long, different from each other and from the examples |
| Audit retention | `AUDIT_RETENTION_DAYS` set for the similar-case search's own events (Case Management events are permanent) |
| Search labels, police connector | reviewed by a legal expert; adapted to the real export (Steps 9 and 14.4) |

## 3. Known limitations

What the system does not do, or does only partly. Each item says why, and what would change it.

| Area | Limitation | Why / what would change it |
|---|---|---|
| **Evidence storage** | The default store is a folder of read-only files. Someone with administrator access to the server's disk could still alter or remove a file. That would be **detected** (integrity checks, the daily sweep, the report check) but not **prevented** | Real prevention needs write-once storage outside the application's control, such as hardware WORM or object storage with a retention lock (decision D14). The store sits behind an interface, so it can be swapped |
| **Database administrators** | The application's own login can't delete or rewrite case records, and the audit trail is hash-chained with signed checkpoints. The database owner account can still change the database rules | That is in the nature of a database. Edits are detected by the chain and checkpoint checks; keep the owner login and the checkpoint key with different people (D16) |
| **Platform integration** | There is no single sign-on and no screen of the wider Knight Hawk platform. Outside systems connect through the documented contract ([09](09-integration-contract.md)); the only source today is the fictional test source | No platform code was supplied (decision 1 in document 08) |
| **Scanned documents** | Scanned pages without text can't be read by Case Intelligence: there is no OCR | Case Intelligence reports such files as "no text". OCR would be an extra component |
| **PDF fonts** | Signed reports print Latin text. Names in Indian scripts need an extra font | Add a font such as Noto Sans for the scripts in use (CM-7) |
| **Court use** | A report is evidence of what the records said as of an entry of the case's history, with hashes. It is **not automatically admissible**, and court-specific formats are not built in | Formats per court or jurisdiction need your legal team (document 08) |
| **People taken off a team** | Taking someone off a case's team ends their access at once; they can't be put back by anyone but the Investigator or an overseer adding them again. What they did stays credited to them (as counts on their contributions page, without showing the case) | By design: access follows the team as it is today, with that day's checks. Nothing is copied or inherited |
| **Times inside files** | The system records times with their time zone and shows them in local time. Times *inside* an uploaded file (a bank log in UTC, a CDR in IST) are kept exactly as the file has them | Evidence must never be changed. The demonstration case shows what a misread time zone does, and how it is corrected without rewriting history |
| **Live pages** | Pages update within about 5 seconds (administration pages within 15). Each open page makes one small database query every 5 seconds | Fine for a police unit's numbers. At a much larger scale, PostgreSQL notifications could replace the polling |
| **The AI assistant** | It runs locally (Ollama), can be slow without a graphics card, and can be wrong: answers cite their sources, and "not found in the records" is allowed | Decision D10 sets how it may be used |
| **Scale and availability** | One server, one database: no high-availability set-up | Hosting decision D6 |
| **Language** | The screens are in English | Labels are kept in one file per area, ready for translation |
| **Demonstration case** | KH-2026-0001 can't be removed from the database it was seeded into | By design. Seed it only into development or training databases; the readiness check flags it |

## 4. Before the first real record: the order of work

1. Sign the decisions form with the people named in it (D1 to D16).
2. Install on the chosen server, from a **fresh** database. Set the case-number prefix before the first case (`scripts.organisation --set-up`).
3. Set the keys and logins (`.env`, see `.env.example`). Turn the test source off and two-step verification on, once administrators and supervisors have set it up.
4. Put the organisation's certificate in place and turn on HSTS. Set up backups and check a restore.
5. Configure the write-once evidence storage (D14).
6. Create the real accounts; deactivate or remove the development and demonstration accounts.
7. Run `scripts.readiness_check` until it says READY, then run the acceptance test (`pytest tests/test_cm_acceptance.py`) against a copy as a last check.
