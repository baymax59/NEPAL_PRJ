# 09. Integration contract: "Add to case"

For developers of the Knight Hawk systems that send findings to cases: the Log Analyzer, CDR and IPDR analysis, OSINT, alerting, forensic laboratories. Contract **version 2.0** (version 1.0 was built in phase CM-6 for the earlier git-style design, [`../steps/15-6-integrations.md`](../steps/15-6-integrations.md); version 2.0 sends a `case_id` instead of a repository, a branch and a head, see [`../steps/17-2-plain-case-backend.md`](../steps/17-2-plain-case-backend.md)). The live description is `GET /api/v1/integrations/contract`, and every field is in [`openapi.json`](openapi.json).

## 1. What the contract does

An investigator looking at a result in another system (a suspicious login, a CDR analysis, a public post) presses **Add to case**. That system calls one endpoint, and the finding becomes part of the case:

- a **permanent file** in the case (`IMP-0001`, `IMP-0002`…), kept exactly as received, in the case's folder **imports** (the case makes that folder the first time a finding arrives; it is marked as made by the system);
- written into the case's **numbered history** (an entry of kind "imported finding"), so it is searched, reported and listed like everything else in the case;
- with its **provenance**: which system, which record in it, the record's hash, where the full record stays, the legal authority it was obtained under, when it happened, which key sent it, and for whom;
- with an **audit event**, and a notice to the case's lead investigator.

There is no review step and no approval: the finding goes straight into the case, like a note written by a Sub Investigator.

The **identifiers** it names (IP addresses, domains, phone numbers, IMEI, IMSI, accounts, file hashes) are matched across cases, so the same suspect number in two cases is found, but only in cases the reader may open.

**What is not stored:** raw data. Log files and CDR or IPDR datasets stay in their source systems. The case keeps the reference (`payload_ref`), the hash (`source_hash`) and the derived result (`details`, at most 64,000 bytes).

## 2. Before the first call: registration

A platform administrator registers each system under **Administration → Integration sources** (or `POST /api/v1/integrations/sources`) with:

| Field | Meaning |
|---|---|
| `code` | Short name of the source: `log-analyzer`, `cdr-analysis` |
| `kind` | `log_analyzer`, `alerting`, `telecom`, `osint`, `threat_intel`, `forensic_lab` or `other` |
| `legal_basis` | Under what authority the system's data is obtained. Required |
| `allowed_item_types` | The kinds of finding it may send (section 5) |
| `authority_required_for` | Kinds that must come with `authority_ref`, a requisition or order number. Default: CDR and IPDR results |
| `min_case_classification` | Findings go only to cases classified at least this (`public` < `internal` < `restricted` < `confidential`) |

The answer contains the source's **key** (`khi_…`), **shown once**. Only its SHA-256 is stored. Give it to the system's administrators through a secure channel, and keep it in the system's secret store, never in code.

The policy can't be edited. A new policy means a new source, so every import names exactly the policy it was accepted under. A source can be **disabled** (its key stops at once; what it added stays), enabled again, and given a **new key** (the old one stops at once). Every change is kept in the source's history, with the administrator and the reason.

## 3. Authentication: two credentials

```
POST /api/v1/integrations/add-to-case
Authorization: Bearer <the token of the person the finding is added for>
X-Integration-Key: khi_<the source's key>
Idempotency-Key: <optional, 8-100 characters>
Content-Type: application/json
```

- **The person** decides to add the finding, and **their rights apply**: they must be allowed to add files to the case, that is the Investigator who leads it, a Sub Investigator or an Analyst on its team, or the Supervisor or an Administrator who oversees it. A Viewer, or someone not on the case, is refused. With single sign-on (when the platform provides it), the system forwards the person's token.
- **The key** says which system vouches for the record. Without a valid key of an enabled source, nothing is accepted.

A system that adds findings without a person (an automatic alert feed) uses an ordinary user account of its own, added to the case's team like a colleague (as a Sub Investigator or Analyst). There is no back door: the same rules apply.

## 4. The request body

| Field | Required | Rules |
|---|---|---|
| `case_id` | yes | The case to add to (its `id`, a UUID) |
| `item_type` | yes | Section 5; must be in the source's `allowed_item_types` |
| `source_record_id` | yes | The record's ID in the source system, 1-200 characters |
| `source_hash` | yes | SHA-256 of the record, as the source computed it: `sha256:<64 hex>` (64 hex alone is taken as SHA-256; `sha512:<128 hex>` also accepted) |
| `summary` | yes | What was found, in a few sentences (10-2,000 characters). People read this first, and Case Intelligence searches it |
| `title` | no | Up to 300 characters; default "<kind>: <record ID>" |
| `payload_ref` | no | Where the full record stays, in the source system (a URI or reference), up to 500 characters |
| `authority_ref` | when the policy requires it | The legal authorisation the data was obtained under, up to 300 characters |
| `observed_at` | for log events, alerts, CDR and IPDR results | When it happened, **with its timezone** (`2026-03-04T10:41:00+05:30`). Not in the future |
| `observed_until` | no | The end of a period (a CDR window), after `observed_at` |
| `identifiers` | for indicators | Up to 100 `{"type": …, "value": …}` (section 6) |
| `details` | no | The derived result, as a JSON object, at most 64,000 bytes |
| `message` | no | A short note kept with the history entry; a default one is written |

Unknown fields are refused (`422`), so a typing mistake is never silently ignored. (Version 1.0's `repository_id`, `branch_id` and `expected_head` are gone: there is nothing to match against, because a case has one history and the finding is simply added to it.)

## 5. Kinds of finding (`item_type`)

| Code | Label | `observed_at` | Legal authority by default | Typical `details` |
|---|---|---|---|---|
| `log_event` | Log event | required | no | system, event, device, session, result |
| `alert` | Alert | required | no | rule, severity, counts, status |
| `cdr_result` | CDR analysis result | required | **yes** | calls, durations, cells, the analysis' conclusion |
| `ipdr_result` | IPDR analysis result | required | **yes** | public IP, ports, operator, access type |
| `osint` | Open-source information | optional | no | platform, address of the post, when and how it was captured, the capture's hash |
| `indicator` | Indicator | optional | no | campaign, confidence, first seen. **At least one identifier** |
| `report` | External report (by reference) | optional | no | laboratory, report number, pages, conclusion |

## 6. Identifiers

Each identifier is checked and stored in one normal form, so the same one written differently matches. "Defanged" values (`hxxp://example[.]com`, `198.51.100[.]23`) are accepted. An invalid value is refused with a message naming it: nothing is guessed.

| Type | Accepted | Stored as |
|---|---|---|
| `ip` | IPv4 or IPv6; a port after `:` is dropped | `203.0.113.45`, `2001:db8::1` |
| `domain` | any case, a trailing dot, international names | lower case, `xn--` form |
| `url` | `http://` or `https://` only | lower-case scheme and host, default ports removed |
| `email` | `name@domain` | lower case |
| `phone` | with the country code (`+91 98450 12345`, `0091…`), or a 10-digit national number (country code from the server setting `CM_PHONE_COUNTRY_CODE`, 91 by default) | `+919845012345` |
| `imei` | 14, 15 (the check digit must be right, or 0) or 16 digits | the first 14 digits, which identify the handset |
| `imsi` | 14 or 15 digits | digits |
| `account` | an account number (6-34 letters or digits) or a UPI ID (`name@bank`) | upper-case number, or lower-case UPI ID |
| `file_hash` | MD5, SHA-1 or SHA-256 in hex, optionally prefixed `sha256:` | lower-case hex |

## 7. Answers

**201 Created** (`ImportAdded`): `entry` (the number of the history entry that recorded it), `updated` (true when it is a new version of a finding already in the case), and `finding`: the finding as the case shows it (`artifact_id`, `display_id`, `version_number`, the provenance fields, the identifiers in their normal form, `received_with` (the first 12 characters of the key that sent it) and `content_sha256` (the hash of what the case keeps)).

| Status | When | What to do |
|---|---|---|
| `401` | no or expired login | log the person in again |
| `403` | no key, a wrong or replaced key, a disabled source; a kind the source may not send; a case below the source's minimum classification; a source of another organisation; the person may read the case but not add to it, or the case is archived (read-only) | fix the key or the policy, or ask who may add |
| `404` | the case doesn't exist **or the person may not see it** (the same answer, on purpose) | check the person's access |
| `409` | the same record, with the same hash, is already active in this case (`existing` names it) | nothing to do |
| `422` | a field is missing or invalid; `authority_ref` missing where required; `details` too large | fix the request |

## 8. A record that changes at its source

- **Same record, same hash**, already active: refused with `409`. Nothing is duplicated.
- **Same record, a new hash** (the source corrected or updated it): accepted as a **new version** of the same `IMP-…` file. The change note says the hash changed from what to what, and the earlier version stays, readable.
- **A finding withdrawn** from the case (by the Investigator or an overseer, with a reason) and sent again: a **new file** with a new number (`IMP-0002`), never a new version of the withdrawn one. The withdrawn file and its reason stay in the history.

The finding itself is never edited in Knight Hawk: people add a note that refers to it, or withdraw it. Both stay in the history.

## 9. Repeating a request safely

Send an `Idempotency-Key` (per person, kept 24 hours). Repeating the same request with the same key returns the first answer with `Idempotent-Replay: true`, without a second history entry. The same key with a different request is refused.

## 10. Example (fictional)

```http
POST /api/v1/integrations/add-to-case
Authorization: Bearer eyJ…
X-Integration-Key: khi_…
Idempotency-Key: cdr-res-2026-017-01-attempt-1

{
  "case_id": "6c1e…",
  "item_type": "cdr_result",
  "source_record_id": "CDR-RES-2026-017-01",
  "source_hash": "sha256:5b0e…(64 hex)",
  "title": "Calls from the suspect number to the complainant on 3 March 2026",
  "summary": "FICTIONAL. The suspect number called the complainant four times on 3 March 2026, 21 minutes in total.",
  "payload_ref": "fict-cdr://datasets/FICT-CYB-2026-017/analyses/01",
  "authority_ref": "Requisition FICT/CYB/2026/017 to the service provider's nodal officer (FICTIONAL)",
  "observed_at": "2026-03-03T09:58:00+05:30", "observed_until": "2026-03-03T11:20:00+05:30",
  "identifiers": [{"type": "phone", "value": "+91 70000 00042"}, {"type": "imsi", "value": "001010000004242"}],
  "details": {"calls": 4, "total_duration_seconds": 1260}
}
```

All values are invented: documentation IP ranges (RFC 5737), `.example` domains (RFC 2606), the test mobile network 001-01, a test IMEI.

## 11. What must never be sent

- **Data obtained without authorisation**, or by interception the law doesn't allow. The source's legal basis and the `authority_ref` are recorded with every finding, and shown to everyone who reads it.
- **Raw datasets** (full logs, CDR or IPDR dumps): send a reference, the hash and the derived result.
- **Real personal data in tests.** Use the fictional test source (section 12) and fictional values.
- **Secrets**: passwords, keys, tokens in any field.

Imported findings are not automatically admissible in court; they are leads and records of what another system reported.

## 12. Trying it without a real system

The **fictional test source** stands in for the real systems until they exist. An administrator registers it in one click (**Add the fictional test source**); then the case's **Imports** tab → **Add from a source** offers eight invented findings (a login, an alert and its later update, a CDR and an IPDR result, a public post, campaign indicators, a laboratory report). They go through exactly the same rules. A test program can also call the contract itself with the test source's key. In production, turn it off with `CM_TEST_SOURCE=false`.

## 13. Checklist for a new integration

1. The administrator registers the source, with its legal basis and the smallest policy it needs.
2. The key goes into the system's secret store; it is replaced if ever exposed.
3. The system computes `source_hash` over the record it holds, the same way every time.
4. Times carry their timezone; identifiers use the types of section 6.
5. Every call sends an `Idempotency-Key`; a `409` means the finding is already in the case, not a reason to retry.
6. Tests use the fictional test source, never real data.
7. A system written for contract 1.0 sends `case_id` now, and drops `repository_id`, `branch_id` and `expected_head`.
