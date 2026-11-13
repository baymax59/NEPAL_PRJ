"""Identifiers named by imported findings: IP address, domain, URL, e-mail, phone, IMEI, IMSI, account, file hash.

Each is checked and stored in one normal form, so the same identifier written differently ("+91 98450 12345",
"098450-12345") is recognised as the same, in a case and across cases. "Defanged" values as threat reports write
them (hxxp://example[.]com) are accepted. A value that isn't a valid identifier of its type is refused with a
message saying why: nothing is guessed or silently dropped.
"""

import ipaddress
import re
from urllib.parse import urlsplit

from app.casemgmt.enums import IndicatorType
from app.casemgmt.errors import Invalid
from app.core.config import get_settings

LABELS = {
    IndicatorType.IP: "IP address",
    IndicatorType.DOMAIN: "Domain",
    IndicatorType.URL: "Web address (URL)",
    IndicatorType.EMAIL: "E-mail address",
    IndicatorType.PHONE: "Phone number",
    IndicatorType.IMEI: "IMEI (handset)",
    IndicatorType.IMSI: "IMSI (SIM card)",
    IndicatorType.ACCOUNT: "Bank account or UPI ID",
    IndicatorType.FILE_HASH: "File hash",
}
HINTS = {
    IndicatorType.IP: "IPv4 or IPv6, e.g. 203.0.113.45 (a port after ':' is dropped)",
    IndicatorType.DOMAIN: "e.g. kyc-update.example",
    IndicatorType.URL: "http:// or https://, e.g. https://kyc-update.example/login",
    IndicatorType.EMAIL: "e.g. helpdesk@kyc-update.example",
    IndicatorType.PHONE: "with its country code (+91 98450 12345); a 10-digit number is taken as a national number",
    IndicatorType.IMEI: "14 to 16 digits; stored as the first 14, which identify the handset",
    IndicatorType.IMSI: "14 or 15 digits",
    IndicatorType.ACCOUNT: "an account number (6 to 34 letters or digits) or a UPI ID (name@bank)",
    IndicatorType.FILE_HASH: "MD5, SHA-1 or SHA-256, in hexadecimal",
}
MAX_IDENTIFIERS = 100
MAX_VALUE = 300

_DOMAIN = re.compile(r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")
_UPI = re.compile(r"^[a-z0-9][a-z0-9._-]{1,255}@[a-z][a-z0-9.]{1,63}$")
_ACCOUNT = re.compile(r"^[A-Z0-9]{6,34}$")
_HEX = re.compile(r"^[0-9a-f]+$")
_SEPARATORS = re.compile(r"[\s\-./()]")
_PORT = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3}):\d{1,5}$")


def _refang(value: str) -> str:
    return (value.replace("[.]", ".").replace("(.)", ".").replace("[dot]", ".").replace("[:]", ":")
            .replace("[@]", "@").replace("[at]", "@"))


def _luhn_check_digit(digits: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:  # every second digit from the right, starting with the one before the check digit
            n *= 2
            n = n - 9 if n > 9 else n
        total += n
    return (10 - total % 10) % 10


def _domain(value: str) -> str:
    host = value.strip().rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")  # internationalised names in their xn-- form
    except UnicodeError:
        raise Invalid(f"'{value[:60]}' isn't a valid domain") from None
    if not _DOMAIN.fullmatch(host):
        raise Invalid(f"'{value[:60]}' isn't a valid domain")
    return host


def _phone(value: str) -> str:
    raw = _SEPARATORS.sub("", value.strip())
    country = get_settings().cm_phone_country_code
    if raw.startswith("+"):
        digits = raw[1:]
    elif raw.startswith("00"):
        digits = raw[2:]
    elif len(raw) == 10:
        digits = country + raw
    elif len(raw) == 11 and raw.startswith("0"):
        digits = country + raw[1:]
    elif len(raw) == len(country) + 10 and raw.startswith(country):
        digits = raw
    else:
        raise Invalid(f"Phone number '{value[:40]}': write it with its country code, e.g. +{country} 98450 12345")
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise Invalid(f"'{value[:40]}' isn't a valid phone number (8 to 15 digits with the country code)")
    return "+" + digits


def _imei(value: str) -> str:
    digits = _SEPARATORS.sub("", value.strip())
    if not digits.isdigit() or len(digits) not in (14, 15, 16):
        raise Invalid(f"'{value[:40]}' isn't a valid IMEI (14 to 16 digits)")
    if len(digits) == 15 and digits[14] != "0" and int(digits[14]) != _luhn_check_digit(digits[:14]):
        raise Invalid(f"'{value[:40]}' isn't a valid IMEI: its check digit is wrong")
    return digits[:14]


def _url(value: str) -> str:
    raw = value.strip()
    raw = re.sub(r"^hxxp", "http", raw, flags=re.IGNORECASE)
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise Invalid(f"'{value[:60]}' isn't a web address: it must start with http:// or https://")
    try:
        port_number = parts.port
    except ValueError:
        raise Invalid(f"'{value[:60]}' isn't a valid web address (its port)") from None
    if _is_ip(parts.hostname):
        address = ipaddress.ip_address(parts.hostname)
        host = f"[{address}]" if address.version == 6 else str(address)
    else:
        host = _domain(parts.hostname)
    port = f":{port_number}" if port_number and port_number not in (80, 443) else ""
    normal = f"{scheme}://{host}{port}{parts.path or '/'}" + (f"?{parts.query}" if parts.query else "")
    if len(normal) > MAX_VALUE:
        raise Invalid(f"The web address starting '{value[:40]}' is longer than {MAX_VALUE} characters: put it in the details")
    return normal


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _ip(value: str) -> str:
    raw = value.strip()
    if match := _PORT.fullmatch(raw):
        raw = match.group(1)
    elif raw.startswith("[") and "]" in raw:  # [2001:db8::1]:443
        raw = raw[1:raw.index("]")]
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        raise Invalid(f"'{value[:60]}' isn't a valid IP address") from None


def _email(value: str) -> str:
    raw = value.strip().lower()
    local, at, host = raw.rpartition("@")
    if not at or not local or len(local) > 64 or re.search(r"\s", local):
        raise Invalid(f"'{value[:60]}' isn't a valid e-mail address")
    return f"{local}@{_domain(host)}"


def _account(value: str) -> str:
    raw = value.strip()
    if "@" in raw:
        upi = raw.lower()
        if not _UPI.fullmatch(upi):
            raise Invalid(f"'{value[:60]}' isn't a valid UPI ID (name@bank)")
        return upi
    number = _SEPARATORS.sub("", raw).upper()
    if not _ACCOUNT.fullmatch(number):
        raise Invalid(f"'{value[:60]}' isn't a valid account number (6 to 34 letters or digits)")
    return number


def _file_hash(value: str) -> str:
    raw = value.strip().lower()
    for prefix in ("md5:", "sha1:", "sha-1:", "sha256:", "sha-256:"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    if not _HEX.fullmatch(raw) or len(raw) not in (32, 40, 64):
        raise Invalid(f"'{value[:70]}' isn't an MD5, SHA-1 or SHA-256 hash in hexadecimal")
    return raw


def _digits(value: str, lengths: tuple[int, ...], what: str) -> str:
    digits = _SEPARATORS.sub("", value.strip())
    if not digits.isdigit() or len(digits) not in lengths:
        raise Invalid(f"'{value[:40]}' isn't a valid {what} ({' or '.join(map(str, lengths))} digits)")
    return digits


NORMALISE = {
    IndicatorType.IP: _ip,
    IndicatorType.DOMAIN: _domain,
    IndicatorType.URL: _url,
    IndicatorType.EMAIL: _email,
    IndicatorType.PHONE: _phone,
    IndicatorType.IMEI: _imei,
    IndicatorType.IMSI: lambda v: _digits(v, (14, 15), "IMSI"),
    IndicatorType.ACCOUNT: _account,
    IndicatorType.FILE_HASH: _file_hash,
}


def normalise(kind: str, value: str) -> str:
    """The normal form of an identifier, or Invalid saying what is wrong with it."""
    try:
        indicator = IndicatorType(kind)
    except ValueError:
        raise Invalid(f"Unknown kind of identifier '{str(kind)[:30]}': use one of {', '.join(t.value for t in IndicatorType)}") from None
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"An identifier of type {indicator.value} has no value")
    if len(value) > 2 * MAX_VALUE:
        raise Invalid(f"An identifier of type {indicator.value} is longer than {MAX_VALUE} characters")
    refanged = value if indicator in (IndicatorType.FILE_HASH, IndicatorType.ACCOUNT) else _refang(value)
    normal = NORMALISE[indicator](refanged)
    if len(normal) > MAX_VALUE:
        raise Invalid(f"An identifier of type {indicator.value} is longer than {MAX_VALUE} characters")
    return normal


def parse_all(items: list[dict]) -> list[dict]:
    """[{type, value}] as received -> [{type, value (normal form), as_received}], without repeats, in the order given."""
    if len(items) > MAX_IDENTIFIERS:
        raise Invalid(f"At most {MAX_IDENTIFIERS} identifiers per finding")
    seen: set[tuple[str, str]] = set()
    result = []
    for item in items:
        kind, value = str(item.get("type", "")), item.get("value")
        normal = normalise(kind, value)
        if (kind, normal) in seen:
            continue
        seen.add((kind, normal))
        result.append({"type": kind, "value": normal, "as_received": value.strip()[:MAX_VALUE]})
    return result


def label(kind: str) -> str:
    try:
        return LABELS[IndicatorType(kind)]
    except ValueError:
        return kind
