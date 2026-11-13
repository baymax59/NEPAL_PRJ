"""CDR analytics: search, top contacts, frequency, call graph, and advanced analysis."""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.cdr.models import CdrRecord


def search_records(
    db: Session,
    case_family_id,
    *,
    q: str | None = None,
    party: str | None = None,
    service_type: str | None = None,
    direction: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    min_duration: int | None = None,
    limit: int = 100,
    offset: int = 0,
    include_duplicates: bool = False,
) -> tuple[int, list[CdrRecord]]:
    stmt = select(CdrRecord).where(CdrRecord.case_family_id == case_family_id)
    if not include_duplicates:
        stmt = stmt.where(CdrRecord.is_duplicate.is_(False))
    if q:
        stmt = stmt.where(
            (CdrRecord.a_party_canonical.ilike(f"%{q}%"))
            | (CdrRecord.b_party_canonical.ilike(f"%{q}%"))
            | (CdrRecord.a_party.ilike(f"%{q}%"))
            | (CdrRecord.b_party.ilike(f"%{q}%"))
            | (CdrRecord.imei.ilike(f"%{q}%"))
            | (CdrRecord.cell_id.ilike(f"%{q}%"))
        )
    if party:
        stmt = stmt.where(
            (CdrRecord.a_party_canonical == party)
            | (CdrRecord.b_party_canonical == party)
            | (CdrRecord.a_party == party)
            | (CdrRecord.b_party == party)
        )
    if service_type:
        stmt = stmt.where(CdrRecord.service_type == service_type)
    if direction:
        stmt = stmt.where(CdrRecord.call_direction == direction)
    if date_from:
        stmt = stmt.where(CdrRecord.timestamp_utc >= dt.datetime.combine(date_from, dt.time.min, tzinfo=dt.UTC))
    if date_to:
        stmt = stmt.where(CdrRecord.timestamp_utc <= dt.datetime.combine(date_to, dt.time.max, tzinfo=dt.UTC))
    if min_duration is not None:
        stmt = stmt.where(CdrRecord.duration_seconds >= min_duration)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(CdrRecord.timestamp_utc.asc().nulls_last()).limit(limit).offset(offset)).all()
    return total, list(rows)


def top_contacts(db: Session, case_family_id, *, limit: int = 20) -> list[dict]:
    stmt = (
        select(CdrRecord.a_party_canonical, CdrRecord.b_party_canonical)
        .where(CdrRecord.case_family_id == case_family_id)
        .where(CdrRecord.is_duplicate.is_(False))
        .where(CdrRecord.a_party_canonical.is_not(None))
    )
    rows = db.execute(stmt).all()
    counts: dict[str, int] = defaultdict(int)
    for a, b in rows:
        if a:
            counts[a] += 1
        if b:
            counts[b] += 1
    top = sorted(counts.items(), key=lambda x: -x[1])[:limit]
    return [{"number": n, "count": c} for n, c in top]


def call_graph(db: Session, case_family_id, *, min_calls: int = 1) -> dict:
    stmt = (
        select(CdrRecord.a_party_canonical, CdrRecord.b_party_canonical, CdrRecord.service_type)
        .where(CdrRecord.case_family_id == case_family_id)
        .where(CdrRecord.is_duplicate.is_(False))
        .where(CdrRecord.a_party_canonical.is_not(None))
        .where(CdrRecord.b_party_canonical.is_not(None))
    )
    rows = db.execute(stmt).all()

    edge_counts: dict[tuple, int] = defaultdict(int)
    edge_types: dict[tuple, set] = defaultdict(set)
    for a, b, svc in rows:
        if a and b and a != b:
            key = (min(a, b), max(a, b))
            edge_counts[key] += 1
            if svc:
                edge_types[key].add(svc)

    node_set: set[str] = set()
    edges = []
    for (a, b), count in edge_counts.items():
        if count >= min_calls:
            node_set.add(a)
            node_set.add(b)
            edges.append({"source": a, "target": b, "count": count, "types": sorted(edge_types[(a, b)])})

    nodes = [{"id": n, "label": n} for n in sorted(node_set)]
    return {"nodes": nodes, "edges": edges}


def frequency_by_hour(db: Session, case_family_id) -> list[dict]:
    stmt = (
        select(
            func.extract("hour", CdrRecord.timestamp_utc).label("hour"),
            func.count().label("count"),
        )
        .where(CdrRecord.case_family_id == case_family_id)
        .where(CdrRecord.is_duplicate.is_(False))
        .where(CdrRecord.timestamp_utc.is_not(None))
        .group_by(text("hour"))
        .order_by(text("hour"))
    )
    return [{"hour": int(r.hour), "count": r.count} for r in db.execute(stmt).all()]


def summary_stats(db: Session, case_family_id) -> dict:
    stmt = select(
        func.count().label("total"),
        func.count(CdrRecord.a_party_canonical.distinct()).label("unique_subscribers"),
        func.min(CdrRecord.timestamp_utc).label("earliest"),
        func.max(CdrRecord.timestamp_utc).label("latest"),
    ).where(CdrRecord.case_family_id == case_family_id).where(CdrRecord.is_duplicate.is_(False))
    row = db.execute(stmt).one()
    return {
        "total_records": row.total or 0,
        "unique_subscribers": row.unique_subscribers or 0,
        "earliest": row.earliest.isoformat() if row.earliest else None,
        "latest": row.latest.isoformat() if row.latest else None,
    }


# ─────────────────────────── Feature 7: Communication Timeline ──────────────

def timeline_for_number(
    db: Session,
    case_family_id,
    number: str,
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: int = 500,
) -> list[CdrRecord]:
    stmt = select(CdrRecord).where(
        CdrRecord.case_family_id == case_family_id,
        or_(
            CdrRecord.a_party_canonical == number,
            CdrRecord.b_party_canonical == number,
            CdrRecord.a_party == number,
            CdrRecord.b_party == number,
        ),
    )
    if date_from:
        stmt = stmt.where(CdrRecord.timestamp_utc >= dt.datetime.combine(date_from, dt.time.min, tzinfo=dt.UTC))
    if date_to:
        stmt = stmt.where(CdrRecord.timestamp_utc <= dt.datetime.combine(date_to, dt.time.max, tzinfo=dt.UTC))
    return list(db.scalars(stmt.order_by(CdrRecord.timestamp_utc.asc().nulls_last()).limit(limit)).all())


# ─────────────────────────── Feature 6: Common Contacts & Co-location ───────

def common_contacts(db: Session, case_family_id, number_a: str, number_b: str) -> dict:
    def _contacts_and_towers(number: str):
        rows = db.execute(
            select(
                CdrRecord.a_party_canonical,
                CdrRecord.b_party_canonical,
                CdrRecord.cell_id,
                CdrRecord.timestamp_utc,
            )
            .where(CdrRecord.case_family_id == case_family_id)
            .where(CdrRecord.is_duplicate.is_(False))
            .where(
                or_(
                    CdrRecord.a_party_canonical == number,
                    CdrRecord.b_party_canonical == number,
                )
            )
        ).all()
        contacts: set[str] = set()
        tower_times: dict[str, list[dt.datetime]] = defaultdict(list)
        for a, b, cell, ts in rows:
            other = b if a == number else a
            if other and other != number:
                contacts.add(other)
            if cell and ts:
                tower_times[cell].append(ts)
        return contacts, tower_times

    contacts_a, towers_a = _contacts_and_towers(number_a)
    contacts_b, towers_b = _contacts_and_towers(number_b)

    shared = sorted(contacts_a & contacts_b - {number_a, number_b})

    colocation: list[dict] = []
    for cell in set(towers_a) & set(towers_b):
        for ts_a in towers_a[cell]:
            for ts_b in towers_b[cell]:
                if abs((ts_a - ts_b).total_seconds()) <= 3600:
                    colocation.append({
                        "cell_id": cell,
                        "time_a": ts_a.isoformat(),
                        "time_b": ts_b.isoformat(),
                        "gap_minutes": round(abs((ts_a - ts_b).total_seconds()) / 60, 1),
                    })
                    break
            else:
                continue
            break

    return {
        "number_a": number_a,
        "number_b": number_b,
        "shared_contacts": shared,
        "shared_contact_count": len(shared),
        "colocation_events": sorted(colocation, key=lambda x: x["time_a"]),
        "contacts_a_count": len(contacts_a),
        "contacts_b_count": len(contacts_b),
    }


# ─────────────────────────── Feature 10: Multi-IMEI / Multi-Number ──────────

def imei_associations(db: Session, case_family_id) -> dict:
    rows = db.execute(
        select(
            CdrRecord.imei,
            CdrRecord.a_party_canonical,
            CdrRecord.timestamp_utc,
        )
        .where(CdrRecord.case_family_id == case_family_id)
        .where(CdrRecord.is_duplicate.is_(False))
        .where(CdrRecord.imei.is_not(None))
        .where(CdrRecord.a_party_canonical.is_not(None))
    ).all()

    imei_numbers: dict[str, set[str]] = defaultdict(set)
    imei_dates: dict[str, list[dt.datetime]] = defaultdict(list)
    number_imeis: dict[str, set[str]] = defaultdict(set)

    for imei, a, ts in rows:
        imei_numbers[imei].add(a)
        number_imeis[a].add(imei)
        if ts:
            imei_dates[imei].append(ts)

    imei_table = []
    for imei, numbers in sorted(imei_numbers.items()):
        dates = imei_dates[imei]
        imei_table.append({
            "imei": imei,
            "numbers": sorted(numbers),
            "number_count": len(numbers),
            "first_seen": min(dates).isoformat() if dates else None,
            "last_seen": max(dates).isoformat() if dates else None,
            "flagged": len(numbers) > 1,
        })

    multi_imei = [
        {"number": n, "imeis": sorted(imeis), "imei_count": len(imeis)}
        for n, imeis in sorted(number_imeis.items())
        if len(imeis) > 1
    ]

    return {
        "imei_table": sorted(imei_table, key=lambda x: -x["number_count"]),
        "multi_imei_numbers": sorted(multi_imei, key=lambda x: -x["imei_count"]),
        "total_imeis": len(imei_table),
        "flagged_imeis": sum(1 for r in imei_table if r["flagged"]),
    }


# ─────────────────────────── Feature 8: Anomaly Detection ───────────────────

def anomaly_detect(db: Session, case_family_id) -> list[dict]:
    rows = db.execute(
        select(
            CdrRecord.a_party_canonical,
            CdrRecord.b_party_canonical,
            CdrRecord.imei,
            CdrRecord.cell_id,
            CdrRecord.timestamp_utc,
            CdrRecord.service_type,
        )
        .where(CdrRecord.case_family_id == case_family_id)
        .where(CdrRecord.is_duplicate.is_(False))
    ).all()

    # Build per-number index
    number_events: dict[str, list[tuple]] = defaultdict(list)
    number_imeis: dict[str, set[str]] = defaultdict(set)

    for a, b, imei, cell, ts, svc in rows:
        if a:
            number_events[a].append((ts, cell, imei, svc))
            if imei:
                number_imeis[a].add(imei)

    anomalies: list[dict] = []

    # 1. Bulk SMS: >50 SMS events in a 1-hour window
    for number, events in number_events.items():
        sms = sorted([(ts, cell) for ts, cell, _, svc in events if svc == "sms" and ts])
        for i, (ts, _) in enumerate(sms):
            window = [e for e in sms if ts <= e[0] <= ts + dt.timedelta(hours=1)]
            if len(window) >= 50:
                anomalies.append({
                    "type": "bulk_sms",
                    "severity": "high",
                    "number": number,
                    "description": f"Bulk SMS: {len(window)} messages in 1 hour starting {ts.strftime('%Y-%m-%d %H:%M')} UTC",
                    "event_count": len(window),
                    "first_seen": ts.isoformat(),
                })
                break

    # 2. SIM swap: same number on 2+ different IMEIs
    for number, imeis in number_imeis.items():
        if len(imeis) > 1:
            anomalies.append({
                "type": "sim_swap",
                "severity": "medium",
                "number": number,
                "description": f"Number used on {len(imeis)} different devices (possible SIM swap or sharing)",
                "imei_count": len(imeis),
                "imeis": sorted(imeis)[:5],
            })

    # 3. Rapid location change: different cell towers within 30 minutes
    for number, events in number_events.items():
        cell_events = sorted(
            [(ts, cell) for ts, cell, _, _ in events if cell and ts],
            key=lambda x: x[0],
        )
        for i in range(len(cell_events) - 1):
            ts1, c1 = cell_events[i]
            ts2, c2 = cell_events[i + 1]
            gap = (ts2 - ts1).total_seconds()
            if c1 != c2 and 0 < gap < 1800:
                anomalies.append({
                    "type": "rapid_location_change",
                    "severity": "low",
                    "number": number,
                    "description": (
                        f"Location change: {c1} → {c2} in {int(gap / 60)} minutes"
                    ),
                    "cell_from": c1,
                    "cell_to": c2,
                    "time_from": ts1.isoformat(),
                    "time_to": ts2.isoformat(),
                    "gap_minutes": round(gap / 60, 1),
                })
                break

    # 4. IMEI shared across multiple numbers (device sharing/cloning indicator)
    imei_to_numbers: dict[str, set[str]] = defaultdict(set)
    for a, b, imei, cell, ts, svc in rows:
        if a and imei:
            imei_to_numbers[imei].add(a)
    for imei, numbers in imei_to_numbers.items():
        if len(numbers) > 1:
            anomalies.append({
                "type": "shared_imei",
                "severity": "high",
                "description": f"IMEI {imei} used by {len(numbers)} different numbers (cloning indicator)",
                "imei": imei,
                "numbers": sorted(numbers)[:5],
                "number_count": len(numbers),
            })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(anomalies, key=lambda x: severity_order.get(x.get("severity", "low"), 2))


# ─────────────────────────── Feature 4: Link Analysis (2-hop) ───────────────

def link_graph_for_number(
    db: Session,
    case_family_id,
    seed_number: str,
    *,
    hops: int = 2,
    min_calls: int = 1,
) -> dict:
    """Extended call graph seeded from one number, showing up to `hops` degrees of separation."""

    def _contacts_of(numbers: set[str]) -> set[str]:
        if not numbers:
            return set()
        rows = db.execute(
            select(CdrRecord.a_party_canonical, CdrRecord.b_party_canonical)
            .where(CdrRecord.case_family_id == case_family_id)
            .where(CdrRecord.is_duplicate.is_(False))
            .where(
                or_(
                    CdrRecord.a_party_canonical.in_(numbers),
                    CdrRecord.b_party_canonical.in_(numbers),
                )
            )
        ).all()
        found: set[str] = set()
        for a, b in rows:
            if a:
                found.add(a)
            if b:
                found.add(b)
        return found - numbers

    hop_sets: list[set[str]] = [{seed_number}]
    all_numbers: set[str] = {seed_number}
    for _ in range(min(hops, 3)):
        new_contacts = _contacts_of(hop_sets[-1]) - all_numbers
        if not new_contacts:
            break
        hop_sets.append(new_contacts)
        all_numbers |= new_contacts
        if len(all_numbers) > 300:
            break

    # Build edges for all numbers in the graph
    edge_counts: dict[tuple, int] = defaultdict(int)
    if all_numbers:
        all_rows = db.execute(
            select(CdrRecord.a_party_canonical, CdrRecord.b_party_canonical)
            .where(CdrRecord.case_family_id == case_family_id)
            .where(CdrRecord.is_duplicate.is_(False))
            .where(CdrRecord.a_party_canonical.in_(all_numbers))
            .where(CdrRecord.b_party_canonical.in_(all_numbers))
        ).all()
        for a, b in all_rows:
            if a and b and a != b:
                edge_counts[(min(a, b), max(a, b))] += 1

    hop_map: dict[str, int] = {}
    for i, s in enumerate(hop_sets):
        for n in s:
            hop_map[n] = i

    nodes = [{"id": n, "label": n, "hop": hop_map.get(n, 0)} for n in sorted(all_numbers)]
    edges = [
        {"source": a, "target": b, "count": c}
        for (a, b), c in edge_counts.items()
        if c >= min_calls
    ]

    return {"nodes": nodes, "edges": edges, "seed": seed_number, "total_nodes": len(nodes)}


# ─────────────────────────── Data Profile (for AI context) ──────────────────

def data_profile(db: Session, case_family_id) -> dict:
    """
    Build a rich snapshot of the CDR dataset so the AI knows what it's working with.
    Returns columns actually populated, date range, top numbers, service breakdown, etc.
    """
    rows = db.execute(
        select(
            CdrRecord.a_party_canonical,
            CdrRecord.b_party_canonical,
            CdrRecord.a_party,
            CdrRecord.b_party,
            CdrRecord.timestamp_utc,
            CdrRecord.duration_seconds,
            CdrRecord.service_type,
            CdrRecord.call_direction,
            CdrRecord.imei,
            CdrRecord.cell_id,
            CdrRecord.operator,
            CdrRecord.network_type,
            CdrRecord.area_code,
        )
        .where(CdrRecord.case_family_id == case_family_id)
        .where(CdrRecord.is_duplicate.is_(False))
        .limit(100_000)
    ).all()

    if not rows:
        return {
            "total_records": 0,
            "has_data": False,
            "columns_present": [],
            "date_range": None,
            "unique_numbers": [],
            "service_type_counts": {},
            "direction_counts": {},
        }

    # Identify which columns actually have data
    cols_present: list[str] = ["a_party", "b_party"]  # always present
    sample = rows[:200]
    if any(r.a_party_canonical for r in sample):
        cols_present.append("a_party_canonical")
    if any(r.b_party_canonical for r in sample):
        cols_present.append("b_party_canonical")
    if any(r.timestamp_utc for r in sample):
        cols_present.append("timestamp_utc")
    if any(r.duration_seconds is not None for r in sample):
        cols_present.append("duration_seconds")
    if any(r.service_type for r in sample):
        cols_present.append("service_type")
    if any(r.call_direction for r in sample):
        cols_present.append("call_direction")
    if any(r.imei for r in sample):
        cols_present.append("imei")
    if any(r.cell_id for r in sample):
        cols_present.append("cell_id")
    if any(r.operator for r in sample):
        cols_present.append("operator")
    if any(r.network_type for r in sample):
        cols_present.append("network_type")
    if any(r.area_code for r in sample):
        cols_present.append("area_code")

    # Date range
    timestamps = [r.timestamp_utc for r in rows if r.timestamp_utc]
    date_range = None
    if timestamps:
        date_range = {
            "earliest": min(timestamps).strftime("%Y-%m-%d"),
            "latest": max(timestamps).strftime("%Y-%m-%d"),
        }

    # Service type breakdown
    svc_counts = Counter(r.service_type for r in rows if r.service_type)
    dir_counts = Counter(r.call_direction for r in rows if r.call_direction)

    # Unique numbers (top 50 most active)
    number_freq: Counter = Counter()
    for r in rows:
        if r.a_party_canonical:
            number_freq[r.a_party_canonical] += 1
        elif r.a_party:
            number_freq[r.a_party] += 1
        if r.b_party_canonical:
            number_freq[r.b_party_canonical] += 1
        elif r.b_party:
            number_freq[r.b_party] += 1

    top_numbers = [
        {"number": n, "event_count": c}
        for n, c in number_freq.most_common(50)
    ]

    # Duration stats (voice calls)
    durations = [r.duration_seconds for r in rows if r.duration_seconds is not None]
    duration_stats = None
    if durations:
        duration_stats = {
            "min_seconds": min(durations),
            "max_seconds": max(durations),
            "avg_seconds": round(sum(durations) / len(durations), 1),
        }

    # Unique IMEIs
    unique_imeis = list({r.imei for r in rows if r.imei})[:20]

    # Unique cell IDs
    unique_cells = list({r.cell_id for r in rows if r.cell_id})[:30]

    return {
        "total_records": len(rows),
        "has_data": True,
        "columns_present": sorted(set(cols_present)),
        "date_range": date_range,
        "unique_number_count": len(number_freq),
        "top_numbers": top_numbers,
        "service_type_counts": dict(svc_counts),
        "direction_counts": dict(dir_counts),
        "duration_stats": duration_stats,
        "unique_imeis": unique_imeis,
        "unique_cell_ids": unique_cells,
    }
