# 07. Security and integrity design

> **Earlier design (superseded on 2026-11-10).** This document describes the first, git-style design of Case Management: an original repository, clones, branches, commits, reviews, merges and invitations. The owner asked for that to be removed completely and replaced by a plain case (permanent folders made at registration, files with versions, a team the Investigator builds directly, one numbered history). **The current design is in [13-plain-case-design.md](13-plain-case-design.md).** It is kept here for the record: where it says repository, clone, branch, commit, review or invitation, read the plain case instead. Its threats and controls still hold; the history chain of each case (document 13, section 2) replaces the commit hashes.

For security reviewers, legal advisers and IT. It builds on the existing controls in [`docs/SECURITY_REVIEW.md`](../SECURITY_REVIEW.md).

## 1. Who we defend against

| Threat | Example | Main controls |
|---|---|---|
| Outsider on the network | steals a password, sniffs traffic | HTTPS only, MFA for privileged roles, login limits, generic errors |
| Investigator beyond their remit | opens another unit's case, or an older sibling clone | tenant + membership + reachability checks **inside every query**; 404 for anything not visible; audited |
| Contributor escalating | invites themselves as lead, changes their own role | nobody can change their own membership; invitations validated against organisation, clearance and the inviter's role |
| Anyone hiding a mistake | deletes a wrong note, rewrites a commit, swaps a file | no destructive operations; corrections are new versions; append-only tables; content hashes |
| Compromised administrator **account** | tries to delete evidence through the application | no delete function exists even for admins; every attempt is audited |
| Database administrator going around the application | edits rows directly | triggers and privileges stop casual edits. **Detection**: the hash-chained audit with checkpoints kept outside the database, evidence hashes in write-once storage, periodic verification |
| Malicious upload | malware, a disguised script | size limit, content-type check against the bytes, optional ClamAV, never executed or rendered as HTML, downloads as attachments |
| AI misuse | a document tells the assistant to reveal or invent things | Case Intelligence rules: retrieval only from what the user may see, documents treated as data, citations checked, "not found" instead of guessing |

## 2. Immutability: what is guaranteed and what isn't

| Layer | Stops | Doesn't stop |
|---|---|---|
| API without destructive routes; 405 + audit | users, user interface bugs, scripts using the API | someone with database or server access |
| Service code with no update paths | programming mistakes | the same |
| Database triggers + a runtime role without `DELETE`/`UPDATE` on append-only tables | the application, even if compromised | a database **superuser** |
| Write-once object storage (S3 Object Lock, **compliance** mode) | deletion or overwriting of evidence bytes, even by storage administrators, until the retention date | a storage administrator of a store **without** a properly configured compliance mode, hence "verify the actual configuration" |
| Hash chain + signed checkpoints stored write-once | — (it **detects** rather than prevents) | nothing goes undetected: any change to past audit events breaks the chain |

*Built in CM-7:* the runtime role `cm_runtime` and the application's own login, the hash chain with signed checkpoints, and the daily checks of the worker; retention decisions (two people) and legal holds (decision D15).

*Built in CM-8:* live pages say only *that* something changed, as a fingerprint, and only for a page the person may open (the same access rules, checked at every poll); the watched page is recorded in the stream's audit event. A person's work in investigations they can no longer open is shown to them as counts only. The readiness check flags the fictional demonstration case and its accounts: case records can't be deleted, so a database that holds them is for demonstration and training only.

**So the honest claim is:** the application cannot delete or rewrite history. Anyone who changes the database directly is **detected**, provided the checkpoint key and the write-once store are protected **separately** from the database administrators. That separation is an organisational decision (DECISIONS.md, D6 and D11).

## 3. Chain of custody

- Recorded for every evidence version: collected, ingested, transferred, accessed, verified, sealed/unsealed, exported.
- Each event holds who handed over and who received, the time (UTC, plus the original timezone), reason, method, verification hash, acknowledgement and authorisation reference.
- A transfer is complete only when the receiver **acknowledges** it.
- The custody log is append-only and covered by the audit chain.
- **Not court-admissible by itself.** Admissibility depends on the jurisdiction, collection procedure and authorisation. Reports say so.

## 4. Access control

- **Tenant isolation:** every query filters by organisation, and a cross-organisation request is a 404. Tested for every endpoint group.
- **Roles:** organisation roles plus per-repository roles ([04 §6](04-low-level-design.md)), with least privilege by default. Contributors are not copied into new clones automatically.
- **Clearance** against case and evidence classification, as today. **Sealed** evidence is visible only with the seal permission.
- **Revocation** takes effect on the next request. Tokens carry the user ID only, and permissions are read fresh every time.
- **Privileged actions** need MFA and are recorded twice: as an audit event and as an authorisation event. These are approvals, merges, sealing, role changes and legal holds.

## 5. Sessions and authentication

- The existing login: Argon2 password hashes, 60-minute tokens, account lockout, per-computer limit, generic errors.
- **TOTP MFA** (`pyotp`, MIT) is required for platform admins and supervisors, and optional for others. Secrets are encrypted at rest. *Built in CM-7:* secrets encrypted with `MFA_KEY` (Fernet); each code works once; required for privileged actions when `CM_MFA_REQUIRED=true` (decision D16).
- **Single sign-on** (OpenID Connect) when the Knight Hawk platform provides it.

## 6. Data protection

| Topic | Design |
|---|---|
| In transit | HTTPS only (Caddy); HSTS once the address is final |
| At rest | Full-disk encryption on every server disk and backup disk (BitLocker / LUKS). Optionally, AES-256-GCM per evidence object, with keys held outside the database (`cryptography`, Apache-2.0/BSD), for stores without built-in encryption |
| Backups | Database + evidence store + checkpoints, on encrypted storage that is not cloud-synced, with a monthly restore check (Step 14.3) |
| Logging | Case content never in application logs; searches and questions as fingerprints (as today) |
| Retention | **No automatic deletion of case records.** Retention is a compliance workflow (`retention_decisions`) with legal holds. Any conflict between "never delete" and a legal erasure duty is recorded and decided formally, never handled silently |
| Personal data | Protected identities as in Step 14.4 (confidential, names withheld); sealing; access logging |

## 7. Upload and download safety

- Size limits (web server and backend); streaming hashes; content type checked against the bytes; optional malware scan before evidence is accepted.
- *CM-2:* a file whose bytes contradict its name is refused (415). Honestly named programs (e.g. malware samples in cyber cases), scripts, HTML and SVG are accepted, marked as active content, never previewed, and downloaded only as plain data; `EVIDENCE_ACCEPT_PROGRAMS=false` refuses programs (D14). Malware scanning is not built yet.
- Stored outside the web root under its hash, never executed.
- Previews are safe renderings only: text, server-re-encoded images, PDF text and page images. **No inline HTML or SVG.**
- Downloads need a 5-minute signed token bound to the user and version, are sent as attachments, and are logged as custody events.

## 8. Licences of new components

| Component | Licence | Note |
|---|---|---|
| React Flow (`@xyflow/react`) | MIT | lineage graph |
| `diff` (npm) | BSD-3 | comparison views |
| Recharts | MIT | dashboards |
| ReportLab | BSD | PDF reports |
| pyotp | MIT | MFA |
| cryptography | Apache-2.0 / BSD | optional object encryption, signatures |
| Valkey | BSD-3 | queue (instead of Redis, whose newer versions are not open-source licensed) |
| RQ | BSD-2 | background worker |
| ClamAV | GPL-2.0 | optional; runs as a separate service, not linked |
| MinIO | **AGPL-3.0** | optional S3 store. Needs your legal team's approval, and a check of how its free edition is currently distributed. Any S3 store with Object Lock in compliance mode will do |
| boto3 | Apache-2.0 | S3 client |

## 9. Known limitations (to be stated in the handover)

- **Detection, not prevention,** against database superusers. Keeping the checkpoint key and write-once storage separate is essential.
- **No legal-admissibility claims.**
- Local AI on a CPU is slow (2–4 minutes per assistant answer); a GPU server is recommended.
- **Integrations are built against a fictional test source** until the real Log Analyzer, CDR/IPDR and OSINT systems are available. *Built in CM-6:* each source has a key (stored only as a SHA-256, shown once, replaceable) and a fixed policy with its legal basis; CDR and IPDR results need a legal authority reference by default; the key and the identifiers are never written to the audit log. Turn the test source off in production (`CM_TEST_SOURCE=false`).
- MFA is TOTP only; hardware keys (WebAuthn) can be added later.
