"""The fictional test source (phase CM-6).

It stands in for the Knight Hawk Log Analyzer, CDR/IPDR analysis, OSINT and alert systems until they exist, so the
"Add to case" flow can be tried in the screens and tested end to end. Every finding is invented (FICTIONAL) and fits
the fictional online-banking-fraud story used in the demo case. Only reserved example values are used: documentation
IP ranges (RFC 5737), .example domains (RFC 2606), the test mobile network 001-01, a test IMEI (reporting body 00),
and invented account numbers.

Each finding carries the hash a real source would compute over its record (SHA-256 of the record's canonical JSON).
The source serves only this fixed catalogue: it can't be used to send anything else. It is turned off with
CM_TEST_SOURCE=false, and an administrator must register it first (one click in Integration sources).
"""

import datetime as dt
from copy import deepcopy

from app.casemgmt import hashing
from app.casemgmt.errors import NotVisible
from app.casemgmt.integrations.imports import Finding

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SUSPECT_PHONE = "+91 70000 00042"
COMPLAINANT_PHONE = "+91 98450 12345"  # the number in the demo case's FIR
SUSPECT_IMSI = "001010000004242"  # test network: MCC 001, MNC 01
SUSPECT_IMEI = "004400112233448"  # reporting body 00: a test IMEI (valid check digit)
LOGIN_IP = "203.0.113.45"
HOSTING_IP = "198.51.100.23"
APP_SHA256 = "d3c188c4499dccb75521c7f4d0a368e0b87dd16ba38487417b3a0b61bbf0f517"
REQUISITION = "Requisition FICT/CYB/2026/017 to the service provider's nodal officer (FICTIONAL)"


def _at(day: int, hour: int, minute: int, month: int = 3) -> str:
    return dt.datetime(2026, month, day, hour, minute, tzinfo=IST).isoformat()


FINDINGS: list[dict] = [
    {
        "id": "log-new-device-login", "system": "Log Analyzer (fictional)", "item_type": "log_event",
        "source_record_id": "LA-EVT-2026-000731", "title": "New-device login to the complainant's net banking",
        "summary": "FICTIONAL. The complainant's net-banking account was logged into from a new Android device at 10:41 on "
                   "4 March 2026, from IP address 203.0.113.45, eleven minutes before the first transfer.",
        "payload_ref": "fict-log-analyzer://events/LA-EVT-2026-000731", "authority_ref": None,
        "observed_at": _at(4, 10, 41), "observed_until": None,
        "identifiers": [{"type": "ip", "value": LOGIN_IP}],
        "details": {"system": "Net-banking portal (fictional)", "event": "Login from a new device", "device": "Android, model not reported",
                    "session": "FICT-SESS-9931", "result": "success"},
    },
    {
        "id": "alert-rapid-transfers", "system": "Alerting (fictional)", "item_type": "alert",
        "source_record_id": "AL-2026-0192", "title": "Three UPI transfers to a new payee within six minutes",
        "summary": "FICTIONAL. Rule FICT-RULE-17 raised a high-severity alert: three UPI transfers of INR 85,000 each from "
                   "the complainant's account to a new payee, fict.mule@okexample, between 10:52 and 10:58 on 4 March 2026.",
        "payload_ref": "fict-alerting://alerts/AL-2026-0192", "authority_ref": None,
        "observed_at": _at(4, 10, 52), "observed_until": _at(4, 10, 58),
        "identifiers": [{"type": "account", "value": "fict.mule@okexample"}, {"type": "account", "value": "5010 0000 0042 42"}],
        "details": {"rule": "FICT-RULE-17 rapid transfers to a new payee", "severity": "high", "transfers": 3,
                    "amount_each_inr": 85000, "status": "open"},
    },
    {
        "id": "alert-rapid-transfers-update", "system": "Alerting (fictional)", "item_type": "alert",
        "updates": "alert-rapid-transfers",
        "source_record_id": "AL-2026-0192", "title": "Three UPI transfers to a new payee within six minutes",
        "summary": "FICTIONAL. Update of alert AL-2026-0192 by the alerting system: severity raised to critical and the "
                   "alert confirmed as fraud after the bank's review on 5 March 2026.",
        "payload_ref": "fict-alerting://alerts/AL-2026-0192", "authority_ref": None,
        "observed_at": _at(4, 10, 52), "observed_until": _at(4, 10, 58),
        "identifiers": [{"type": "account", "value": "fict.mule@okexample"}, {"type": "account", "value": "5010 0000 0042 42"}],
        "details": {"rule": "FICT-RULE-17 rapid transfers to a new payee", "severity": "critical", "transfers": 3,
                    "amount_each_inr": 85000, "status": "confirmed fraud", "reviewed": "5 March 2026 by the bank's fraud team"},
    },
    {
        "id": "cdr-calls-to-complainant", "system": "CDR analysis (fictional)", "item_type": "cdr_result",
        "source_record_id": "CDR-RES-2026-017-01", "title": "Calls from the suspect number to the complainant on 3 March 2026",
        "summary": "FICTIONAL. Analysis of call records obtained under requisition FICT/CYB/2026/017: the suspect number "
                   "+91 70000 00042 called the complainant (+91 98450 12345) four times on 3 March 2026, 21 minutes in "
                   "total. The handset and SIM used for the calls are identified below.",
        "payload_ref": "fict-cdr://datasets/FICT-CYB-2026-017/analyses/01", "authority_ref": REQUISITION,
        "observed_at": _at(3, 9, 58), "observed_until": _at(3, 11, 20),
        "identifiers": [{"type": "phone", "value": SUSPECT_PHONE}, {"type": "phone", "value": COMPLAINANT_PHONE},
                        {"type": "imei", "value": SUSPECT_IMEI}, {"type": "imsi", "value": SUSPECT_IMSI}],
        "details": {"calls": 4, "total_duration_seconds": 1260, "longest_call_seconds": 612, "first_cell": "FICT-CELL-7781",
                    "analysis": "The suspect number was the complainant's most frequent caller on 3 March 2026"},
    },
    {
        "id": "ipdr-login-ip", "system": "IPDR analysis (fictional)", "item_type": "ipdr_result",
        "source_record_id": "IPDR-RES-2026-017-02", "title": "The login IP address was assigned to the suspect's SIM",
        "summary": "FICTIONAL. IP detail records obtained under requisition FICT/CYB/2026/017 show that 203.0.113.45 (the "
                   "IP address of the new-device login) was assigned to the SIM 001010000004242 of the suspect number "
                   "between 10:30 and 11:00 on 4 March 2026.",
        "payload_ref": "fict-ipdr://datasets/FICT-CYB-2026-017/analyses/02", "authority_ref": REQUISITION,
        "observed_at": _at(4, 10, 30), "observed_until": _at(4, 11, 0),
        "identifiers": [{"type": "ip", "value": LOGIN_IP}, {"type": "imsi", "value": SUSPECT_IMSI}, {"type": "phone", "value": SUSPECT_PHONE}],
        "details": {"public_ip": LOGIN_IP, "ports": "40000-40999", "operator": "Example Telecom (fictional)", "access": "mobile data"},
    },
    {
        "id": "osint-kyc-post", "system": "OSINT (fictional)", "item_type": "osint",
        "source_record_id": "OSINT-2026-0088", "title": "Public post offering 'KYC update' help with the suspect number",
        "summary": "FICTIONAL. A public post on an example social network, published on 27 February 2026, offers help with "
                   "a bank 'KYC update', gives the suspect number +91 70000 00042 and links to kyc-update.example.",
        "payload_ref": "fict-osint://captures/OSINT-2026-0088",
        "authority_ref": "Public information, captured under the unit's OSINT procedure (FICTIONAL)",
        "observed_at": _at(27, 19, 5, month=2), "observed_until": None,
        "identifiers": [{"type": "url", "value": "hxxps://kyc-update[.]example/verify"}, {"type": "domain", "value": "kyc-update.example"},
                        {"type": "phone", "value": SUSPECT_PHONE}],
        "details": {"platform": "Example social network (fictional)", "post": "https://social.example/posts/88231",
                    "captured_at": _at(6, 15, 20), "capture": "screenshot and page archive kept in the OSINT system",
                    "capture_sha256": "35b17b5b29c561129e305c892f95be9c0bf7b3f31d031753501af8bd5b25c023"},
    },
    {
        "id": "ioc-kyc-campaign", "system": "Threat intelligence (fictional)", "item_type": "indicator",
        "source_record_id": "IOC-2026-0031", "title": "Indicators of the 'KYC update' fraud campaign",
        "summary": "FICTIONAL. Indicators shared for the 'KYC update' fraud campaign: its website, contact e-mail, hosting "
                   "IP address and the remote-access app it asks victims to install.",
        "payload_ref": "fict-threat-intel://indicators/IOC-2026-0031", "authority_ref": None,
        "observed_at": None, "observed_until": None,
        "identifiers": [{"type": "domain", "value": "kyc-update.example"}, {"type": "email", "value": "helpdesk@kyc-update.example"},
                        {"type": "ip", "value": HOSTING_IP}, {"type": "file_hash", "value": APP_SHA256}],
        "details": {"campaign": "KYC update (fictional)", "confidence": "medium", "first_seen": "2026-02-20"},
    },
    {
        "id": "lab-phone-report", "system": "Forensic laboratory (fictional)", "item_type": "report",
        "source_record_id": "LAB-2026-0091", "title": "Forensic report on the complainant's phone (by reference)",
        "summary": "FICTIONAL. The cyber forensic laboratory's report FICT-LAB-2026-0091 (14 pages) found a remote-access "
                   "app installed on the complainant's phone at 10:05 on 3 March 2026. The report itself stays in the "
                   "laboratory's system.",
        "payload_ref": "fict-lab://reports/FICT-LAB-2026-0091", "authority_ref": "Forwarded under memo FICT/CYB/2026/021 (FICTIONAL)",
        "observed_at": None, "observed_until": None,
        "identifiers": [{"type": "file_hash", "value": APP_SHA256}],
        "details": {"laboratory": "Example Cyber Forensic Laboratory (fictional)", "report_number": "FICT-LAB-2026-0091", "pages": 14,
                    "conclusion": "Remote-access app installed on 3 March 2026 at 10:05"},
    },
]
_BY_ID = {f["id"]: f for f in FINDINGS}
_HASHED = ("item_type", "source_record_id", "title", "summary", "payload_ref", "authority_ref", "observed_at", "observed_until",
           "identifiers", "details")


def record_hash(finding: dict) -> str:
    """The hash the source system computes over its record: SHA-256 of the record's canonical JSON."""
    return "sha256:" + hashing.content_hash({k: finding[k] for k in _HASHED})


def catalogue() -> list[dict]:
    return [{**deepcopy(f), "source_hash": record_hash(f)} for f in FINDINGS]


def finding(finding_id: str) -> Finding:
    found = _BY_ID.get(finding_id)
    if found is None:
        raise NotVisible()
    return Finding(item_type=found["item_type"], source_record_id=found["source_record_id"], source_hash=record_hash(found),
                   summary=found["summary"], title=found["title"], payload_ref=found["payload_ref"], authority_ref=found["authority_ref"],
                   observed_at=dt.datetime.fromisoformat(found["observed_at"]) if found["observed_at"] else None,
                   observed_until=dt.datetime.fromisoformat(found["observed_until"]) if found["observed_until"] else None,
                   identifiers=deepcopy(found["identifiers"]), details=deepcopy(found["details"]))
