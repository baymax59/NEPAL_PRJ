"""Base CDR parser types and column alias map."""
from dataclasses import dataclass, field


@dataclass
class ParsedRow:
    row_number: int
    raw: dict[str, str]
    mapped: dict
    errors: list[tuple[str, str]] = field(default_factory=list)


COLUMN_ALIASES: dict[str, list[str]] = {
    "a_party": ["a_party", "a party", "calling_number", "calling number", "msisdn", "subscriber", "originating", "from", "caller"],
    "b_party": ["b_party", "b party", "called_number", "called number", "dialed", "dialled", "destination", "to", "callee"],
    "timestamp": ["timestamp", "date_time", "datetime", "call_date", "call_time", "event_time", "start_time", "start time", "date/time"],
    "duration_seconds": ["duration_seconds", "duration", "call_duration", "call duration", "dur", "duration(s)", "duration(sec)"],
    "call_type": ["call_type", "call type", "type", "event_type", "record_type", "usage_type"],
    "imei": ["imei", "equipment_id"],
    "imsi": ["imsi", "subscriber_id", "subscriber identity"],
    "cell_id": ["cell_id", "cell id", "tower_id", "cgid", "cgi", "bts", "site_id", "serving_cell", "first_cell"],
    "area_code": ["area_code", "lac", "tac", "location_area_code", "tracking_area_code"],
    "operator": ["operator", "network", "provider", "carrier", "telco"],
    "network_type": ["network_type", "network type", "technology", "rat", "access_technology"],
}


def map_header(columns: list[str]) -> dict[str, str]:
    """Return {canonical_field: original_column} for each recognized column."""
    lower_map = {c.lower().strip(): c for c in columns}
    result: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_map:
                result[canonical] = lower_map[alias]
                break
    return result
