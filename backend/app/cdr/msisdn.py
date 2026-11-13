"""MSISDN canonical normalization for Nepal (np-msisdn.v1) and India (in-msisdn.v1)."""
import hashlib
import json
import re


def normalize_msisdn(raw: str | None, rule: str) -> str | None:
    """Return the canonical MSISDN under `rule`, or None if the value cannot be normalized.

    np-msisdn.v1: canonical form 9779XXXXXXXXX (13 digits).
    in-msisdn.v1: canonical form 91[6-9]XXXXXXXXX (12 digits).
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if rule == "np-msisdn.v1":
        if re.fullmatch(r"9779[0-9]{9}", digits):
            return digits
        if re.fullmatch(r"977[0-9]{10}", digits):
            return digits
        if digits.startswith("0") and len(digits) == 11:
            return "977" + digits[1:]
        if re.fullmatch(r"9[0-9]{9}", digits):
            return "977" + digits
        return None
    if rule == "in-msisdn.v1":
        if re.fullmatch(r"91[6-9][0-9]{9}", digits):
            return digits
        if digits.startswith("0") and len(digits) == 11:
            candidate = "91" + digits[1:]
            if re.fullmatch(r"91[6-9][0-9]{9}", candidate):
                return candidate
        if re.fullmatch(r"[6-9][0-9]{9}", digits):
            return "91" + digits
        return None
    return None


def fingerprint_fields(row: dict) -> str:
    """SHA-256 fingerprint of the CDR row's identity fields (for duplicate detection)."""
    fields = {
        "a": row.get("a_party") or "",
        "b": row.get("b_party") or "",
        "ts": str(row.get("timestamp_local") or ""),
        "dur": str(row.get("duration_seconds") or ""),
        "type": row.get("call_type") or "",
        "imei": row.get("imei") or "",
        "cell": row.get("cell_id") or "",
        "lac": row.get("area_code") or "",
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
