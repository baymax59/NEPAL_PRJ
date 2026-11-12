# Go-live decisions: sign-off form

For: the project owner, legal adviser, data protection officer and IT, who decide **before real police records are loaded**.

Each decision has a recommendation to start from, but the decision itself belongs to your organisation: the system can't make it. When one is made, fill in the three blanks and change its **Status** line from `open` to `decided`. `uv run python -m scripts.readiness_check` (from `backend/`) counts them, together with the technical checks.

The recommendations are a starting point from the development team, **not legal advice**.

---

## D1. Legal basis and authorisation

**Question:** On what legal basis, by whose authority and for what purpose may police records be processed in this system?
**Recommendation:** Written authorisation from the competent authority, naming the purpose: "similar-case research by authorised staff", not decisions about individuals. Your legal adviser confirms which ground of the Digital Personal Data Protection Act, 2023 applies (for example the exemptions concerning the prevention, detection, investigation or prosecution of offences) and which internal police data policies apply.
**Applied in the system:** every import needs `--authorisation "<who, reference>"`. It is stored with the import and in the audit log.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D2. The real export

**Question:** Exactly what will the data owner send: file, columns, codes, identity, updates, deletions, documents?
**Recommendation:**
1. Ask for a small authorised sample (about 50 rows).
2. Run `uv run python -m scripts.police_inspect --folder <sample>` together with the data owner. It shows no personal data.
3. Agree the `format.json` it suggests, and answer the questions in `docs/steps/14-4-*`, section 7.
4. A developer then adds tests for that format before the first full import.

**Applied in the system:** `format.json` in the export folder; `backend/app/connectors/police_records/`.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D3. Protected identities

**Question:** How are identities protected by law handled: victims of sexual offences (Section 72 BNS), children (Section 74 Juvenile Justice Act 2015, Section 23 POCSO Act)?
**Recommendation:** Keep the system's rule: such records are **confidential**, and party names are **not imported**. In addition, the data owner removes names from those FIR texts **before** export: the system does not redact free text.
**Applied in the system:** the `protected_identity` column; `mapping.py`.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D4. Retention periods

**Question:** How long are uploads, the audit log and police records kept, and what happens when a case is closed, sealed or expunged?
**Recommendation:**
- **Uploads:** 30 days (the current setting).
- **Audit log:** as long as your policy requires for access records. Often several years: name the period.
- **Records:** follow the source system. When the source deletes or expunges a record, delete it here too, at the next import.
- **Backups:** kept 14 days (D8).

**Applied in the system:** `UPLOAD_RETENTION_DAYS`, `AUDIT_RETENTION_DAYS` in `.env`; the nightly retention job.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D5. Who may see what

**Question:** Which staff get which role and clearance, and how are access, extra grants, joiners and leavers managed?
**Recommendation:**
- `viewer`/`public` for general staff; `analyst`/`restricted` for named case analysts; `confidential` clearance for very few named people.
- `admin` for two named administrators.
- Per-case grants for at most 90 days, with a reason.
- An access review every quarter; leavers deactivated on their last day.

**Applied in the system:** `scripts.create_user` (`--role`, `--clearance`, `--deactivate`), `scripts.grant_access`.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D6. Hosting

**Question:** Which computer runs it, where, and who administers it?
**Recommendation:**
- A dedicated server on the department's own premises, with its disks encrypted (BitLocker or LUKS).
- Two named administrators.
- Operating system and Docker updates monthly.
- Not a personal laptop.

**Applied in the system:** `docs/DEPLOYMENT.md`, section 1.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D7. Network and certificate

**Question:** Who can reach the system over the network, and with which certificate?
**Recommendation:**
- The office network only, never the internet.
- A certificate from your organisation's certificate authority.
- Firewall: only port 443 (and 80, which redirects).
- Once the address is final, switch on `Strict-Transport-Security`.

**Applied in the system:** `SITE_ADDRESS`, `TLS`, `WEB_BIND`, `HTTPS_PORT` in `.env`; `deploy/Caddyfile`; `deploy/certs/`.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D8. Backups

**Question:** Where are backups kept, who checks they can be restored, and how long are they kept?
**Recommendation:**
- A nightly backup to an encrypted disk that is **not** cloud-synced.
- A weekly copy to a second, encrypted place.
- A named person runs `restore.sh check` monthly.
- Backups kept 14 days.

**Applied in the system:** `BACKUP_DIR`, `BACKUP_KEEP_DAYS`; Task Scheduler or cron (`docs/steps/14-3-*`, section 5).
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D9. Expert review of the search-quality labels

**Question:** Who checks the AI-drafted relevance grades that the search quality is measured against?
**Recommendation:**
1. A lawyer reviews the 319-row sheet (about 2–3 hours), following `backend/evaluation/review/README.md`.
2. Import it, then run `scripts.evaluate` again.
3. Once police data is in use, add police-specific test searches.

**Applied in the system:** `scripts.labels_review export` / `import --reviewer`. The reviewer's name is recorded in `labels.json`.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D10. Use of the AI

**Question:** What may staff rely on the AI features for?
**Recommendation:**
- Search results and assistant answers are **aids for finding material**. Every answer is checked against its cited pages.
- They are never the basis for a decision about guilt, liability or action.
- Staff get a short briefing; the on-screen disclaimers stay.

**Applied in the system:** the disclaimers in the interface; the assistant's rules (`backend/app/chat/service.py`).
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D11. Independent security review

**Question:** Who reviews the system's security before real data, and when?
**Recommendation:**
- An independent reviewer (your security team or an empanelled auditor) before go-live.
- Scope: login and access control, uploads, the web server and HTTPS, the server set-up.
- Start from the internal review in `docs/SECURITY_REVIEW.md`.

**Applied in the system:** findings are fixed and re-tested before go-live.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open

## D12. Location of the project and its data

**Question:** Where do the project, its data and its backups live?
**Recommendation:**
- On the server from D6, e.g. `C:\case-search` or `/opt/case-search`.
- **Not** in OneDrive or any other cloud-synced folder.
- The development copy is currently inside OneDrive.

**Applied in the system:** `docs/DEPLOYMENT.md`, section 1; `BACKUP_DIR`.
**Decided by:** ____________________ **Date:** __________ **Decision / reference:** ______________________________
**Status:** open
