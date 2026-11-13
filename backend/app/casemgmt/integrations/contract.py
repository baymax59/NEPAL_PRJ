"""The integration contract: what an outside system sends to add a finding to a case (docs/case-management/09).

Kept in one place, so the API, the checks, the screens and the contract document agree. Version 1.0.
"""

import datetime as dt
import hashlib
import re

from app.casemgmt.enums import ImportItemType, IndicatorType
from app.casemgmt.errors import Invalid
from app.casemgmt.evidence import moment
from app.casemgmt.integrations import indicators

CONTRACT_VERSION = "2.0"
IMPORTS_FOLDER = "imports"  # the case folder findings are filed in

ITEM_TYPES: dict[ImportItemType, dict] = {
    ImportItemType.LOG_EVENT: {
        "label": "Log event", "folder": "log-events", "observed_at": True,
        "description": "An event found by the Log Analyzer: a login, an access, a change, an error…"},
    ImportItemType.ALERT: {
        "label": "Alert", "folder": "alerts", "observed_at": True,
        "description": "An alert raised by a monitoring or alerting system, with its rule and severity."},
    ImportItemType.CDR_RESULT: {
        "label": "CDR analysis result", "folder": "cdr", "observed_at": True,
        "description": "A result derived from call detail records obtained under a legal requisition (contacts, "
                       "locations, common numbers…). The records themselves stay in the CDR system."},
    ImportItemType.IPDR_RESULT: {
        "label": "IPDR analysis result", "folder": "ipdr", "observed_at": True,
        "description": "A result derived from IP detail records obtained under a legal requisition (who used an IP "
                       "address at a time, sessions…). The records themselves stay in the IPDR system."},
    ImportItemType.OSINT: {
        "label": "Open-source information", "folder": "osint", "observed_at": False,
        "description": "Publicly available information captured lawfully (a public post, a website, a listing), "
                       "with where and when it was captured."},
    ImportItemType.INDICATOR: {
        "label": "Indicator", "folder": "indicators", "observed_at": False,
        "description": "Identifiers on their own: IP addresses, domains, phone numbers, IMEI, IMSI, accounts…"},
    ImportItemType.REPORT: {
        "label": "External report (by reference)", "folder": "reports", "observed_at": False,
        "description": "A report kept in another system (a forensic laboratory, for example), recorded by its "
                       "reference and hash."},
}
# Item types a newly registered source requires a legal authorisation for, unless the administrator decides otherwise.
AUTHORITY_BY_DEFAULT = [ImportItemType.CDR_RESULT.value, ImportItemType.IPDR_RESULT.value]

MAX_SUMMARY = 2000
MAX_DETAILS_BYTES = 64_000
RECORD_ID = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")
_HASH = re.compile(r"^(?:(sha256|sha512):)?([0-9a-f]+)$")
_HASH_LENGTH = {"sha256": 64, "sha512": 128}
_SLUG = re.compile(r"[^a-z0-9._-]+")


def label(item_type: str) -> str:
    try:
        return ITEM_TYPES[ImportItemType(item_type)]["label"]
    except ValueError:
        return item_type.replace("_", " ")


def item_type(value: str) -> ImportItemType:
    try:
        return ImportItemType(value)
    except ValueError:
        raise Invalid(f"Unknown item_type '{str(value)[:30]}': use one of {', '.join(t.value for t in ImportItemType)}") from None


def source_hash(value: str) -> str:
    """'sha256:<hex>' or 'sha512:<hex>'; 64 hexadecimal characters alone are taken as SHA-256."""
    match = _HASH.fullmatch((value or "").strip().lower())
    if match is None:
        raise Invalid("source_hash must be the record's SHA-256 (or 'sha512:<hex>') as the source system computed it")
    algorithm = match.group(1) or "sha256"
    if len(match.group(2)) != _HASH_LENGTH[algorithm]:
        raise Invalid(f"source_hash: a {algorithm.upper()} has {_HASH_LENGTH[algorithm]} hexadecimal characters")
    return f"{algorithm}:{match.group(2)}"


def record_id(value: str) -> str:
    value = (value or "").strip()
    if not RECORD_ID.fullmatch(value):
        raise Invalid("source_record_id: the record's ID in the source system, 1 to 200 characters, no control characters")
    return value


def text(value: str | None, what: str, limit: int, *, minimum: int = 0) -> str | None:
    value = (value or "").strip()
    if len(value) < minimum or len(value) > limit:
        raise Invalid(f"{what}: {minimum} to {limit:,} characters" if minimum else f"{what}: at most {limit:,} characters")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        raise Invalid(f"{what} contains control characters")
    return value or None


def period(kind: ImportItemType, observed_at: dt.datetime | None, observed_until: dt.datetime | None) -> tuple:
    """(observed_at UTC, its timezone, observed_until UTC). Times need a timezone and can't be in the future."""
    start, tz = moment(observed_at, "observed_at")
    end, _ = moment(observed_until, "observed_until")
    if ITEM_TYPES[kind]["observed_at"] and start is None:
        raise Invalid(f"A {label(kind).lower()} needs observed_at: when it happened, with its timezone")
    if end is not None and (start is None or end < start):
        raise Invalid("observed_until must come after observed_at")
    return start, tz, end


def describe() -> dict:
    """The contract as data, for the screens and for integrators (GET /api/v1/integrations/contract)."""
    return {
        "version": CONTRACT_VERSION,
        "item_types": [{"code": t.value, "label": spec["label"], "description": spec["description"],
                        "observed_at_required": spec["observed_at"], "authority_by_default": t.value in AUTHORITY_BY_DEFAULT}
                       for t, spec in ITEM_TYPES.items()],
        "identifier_types": [{"code": t.value, "label": indicators.LABELS[t], "format": indicators.HINTS[t]} for t in IndicatorType],
        "limits": {"summary_characters": MAX_SUMMARY, "details_bytes": MAX_DETAILS_BYTES,
                   "identifiers": indicators.MAX_IDENTIFIERS, "identifier_characters": indicators.MAX_VALUE},
        "headers": {"Authorization": "Bearer <the token of the person the finding is added for>",
                    "X-Integration-Key": "<the source's key, issued once by an administrator>",
                    "Idempotency-Key": "<optional: repeat a request safely>"},
    }
