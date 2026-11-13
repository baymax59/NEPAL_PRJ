"""LLM-powered CDR search and analysis.

The AI is given a full snapshot of the uploaded CDR file (date range, columns present,
top numbers, service types) so it can intelligently answer questions about the actual data.

Two modes:
  - FILTER mode: query converts to structured filters → rows returned from DB
  - DIRECT mode: AI answers the question from the data profile + pre-fetched stats
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.cdr import analytics
from app.chat.llm import ChatModelUnavailable
from app.core.config import get_settings

# ── regex to strip <think>…</think> from reasoning models ───────────────────
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


# ── raw Ollama call (non-streaming, compact) ─────────────────────────────────

def _ollama(messages: list[dict], *, temperature: float = 0.0, num_predict: int = 500) -> str:
    settings = get_settings()
    base_url = settings.ollama_url.rstrip("/")
    model_name = settings.chat_model

    # qwen3 chain-of-thought suppression via /no_think system instruction
    if "qwen3" in model_name.lower():
        msgs = list(messages)
        if msgs and msgs[0]["role"] == "system":
            msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n\n/no_think"}
        else:
            msgs.insert(0, {"role": "system", "content": "/no_think"})
    else:
        msgs = messages

    body = {
        "model": model_name,
        "messages": msgs,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    with httpx.Client(timeout=httpx.Timeout(120, connect=10)) as client:
        try:
            resp = client.post(f"{base_url}/api/chat", json=body)
        except httpx.ConnectError as exc:
            raise ChatModelUnavailable(
                "Ollama is not running. Start Ollama and try again."
            ) from exc
        if resp.status_code == 404:
            raise ChatModelUnavailable(
                f"Model '{model_name}' is not installed in Ollama. "
                f"Run: ollama pull {model_name}"
            )
        if resp.status_code != 200:
            raise ChatModelUnavailable(f"Ollama returned HTTP {resp.status_code}")
        raw = resp.json().get("message", {}).get("content", "")

    # Strip reasoning chain output
    return _THINK_RE.sub("", raw).strip()


# ── build data context string to inject into every prompt ───────────────────

def _build_context(profile: dict) -> str:
    if not profile.get("has_data"):
        return "The CDR dataset is empty — no records have been imported yet."

    lines: list[str] = [
        f"=== CDR Dataset Context ===",
        f"Total records: {profile['total_records']:,}",
        f"Unique numbers: {profile.get('unique_number_count', 0):,}",
    ]

    if profile.get("date_range"):
        dr = profile["date_range"]
        lines.append(f"Date range: {dr['earliest']} to {dr['latest']}")

    if profile.get("service_type_counts"):
        sc = profile["service_type_counts"]
        parts = ", ".join(f"{k}: {v:,}" for k, v in sorted(sc.items(), key=lambda x: -x[1]))
        lines.append(f"Service types: {parts}")

    if profile.get("direction_counts"):
        dc = profile["direction_counts"]
        parts = ", ".join(f"{k}: {v:,}" for k, v in sorted(dc.items(), key=lambda x: -x[1]))
        lines.append(f"Directions: {parts}")

    if profile.get("duration_stats"):
        ds = profile["duration_stats"]
        lines.append(
            f"Duration (seconds): min={ds['min_seconds']}, "
            f"max={ds['max_seconds']}, avg={ds['avg_seconds']}"
        )

    if profile.get("top_numbers"):
        top = profile["top_numbers"][:20]
        lines.append(f"Top {len(top)} most active numbers:")
        for entry in top:
            lines.append(f"  {entry['number']}  ({entry['event_count']} events)")

    cols = profile.get("columns_present", [])
    if cols:
        lines.append(f"Columns with data: {', '.join(sorted(cols))}")

    if profile.get("unique_imeis"):
        lines.append(f"IMEIs in dataset: {', '.join(profile['unique_imeis'][:10])}")

    if profile.get("unique_cell_ids"):
        lines.append(f"Cell IDs in dataset: {', '.join(profile['unique_cell_ids'][:10])}")

    return "\n".join(lines)


# ── step 1: classify the question and extract filters ───────────────────────

_FILTER_SYSTEM = """\
You are a CDR (Call Detail Records) analyst AI for a law enforcement investigation tool.
You have been given the actual contents of the uploaded CDR file as context below.

Your job:
1. Read the investigator's question carefully.
2. Decide: can this question be answered by FILTERING the records, or does it need a DIRECT answer from the data context?
3. Return a JSON object with these fields:
   "mode"       : "filter" | "direct"
   "filters"    : object (only if mode=filter) — valid keys: "q", "party", "service_type",
                  "direction", "date_from" (YYYY-MM-DD), "date_to" (YYYY-MM-DD), "min_duration" (int seconds)
   "direct_answer" : string (only if mode=direct) — your complete answer to the question using
                     the data context above. Be specific: cite numbers, counts, dates from the context.

Use mode=direct for questions like:
  - "Who called the most?" / "Top numbers?" → answer from top_numbers in context
  - "What date range does the data cover?" → answer from date_range
  - "How many records are there?" → answer from total_records
  - "What service types are in the data?" → answer from service_type_counts
  - "Are there any IMEIs?" → answer from columns_present / unique_imeis
  - Any question that asks for a summary, count, or overview of the data

Use mode=filter for questions like:
  - "Show me all SMS messages" → {"service_type": "sms"}
  - "Calls longer than 5 minutes" → {"min_duration": 300}
  - "Records for number 977XXXXXXXXX" → {"party": "977XXXXXXXXX"}
  - "Calls between January and March" → {"date_from": "YYYY-01-01", "date_to": "YYYY-03-31"}

IMPORTANT: Respond with ONLY a raw JSON object. No markdown. No prose outside the JSON.
"""


def _parse_intent(query_text: str, context: str) -> dict[str, Any]:
    system_with_context = _FILTER_SYSTEM + f"\n\n{context}"
    raw = _ollama(
        [
            {"role": "system", "content": system_with_context},
            {"role": "user", "content": query_text},
        ],
        temperature=0.0,
        num_predict=600,
    )
    # Extract JSON
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = _THINK_RE.sub("", cleaned).strip()
    m = _JSON_RE.search(cleaned)
    if not m:
        return {"mode": "filter", "filters": {}}
    data = json.loads(m.group())
    # If error-only response, default to empty filter
    if set(data.keys()) == {"error"}:
        return {"mode": "filter", "filters": {}}
    return data


# ── step 2: generate investigator narrative for filter results ───────────────

_NARRATIVE_SYSTEM = """\
You are an AI analyst for a law enforcement CDR investigation tool.
Write a concise professional narrative (3–5 sentences) for an investigator summarising
what was found. Be specific: mention actual numbers, counts, service types, dates from
the data provided. Do not repeat the raw filter parameters. Do not speculate beyond the data.
"""


def _build_narrative(query_text: str, total: int, records: list, profile: dict) -> str:
    if total == 0:
        return (
            "No CDR records matched the query. "
            "Try broadening the date range, removing the direction filter, "
            "or using a different number format."
        )

    svc = Counter(r.service_type for r in records if r.service_type)
    dirs = Counter(r.call_direction for r in records if r.call_direction)
    nums: set[str] = set()
    for r in records:
        if r.a_party_canonical:
            nums.add(r.a_party_canonical)
        if r.b_party_canonical:
            nums.add(r.b_party_canonical)
    timestamps = [r.timestamp_utc for r in records if r.timestamp_utc]
    date_info = ""
    if timestamps:
        date_info = (
            f" spanning {min(timestamps).strftime('%Y-%m-%d')} "
            f"to {max(timestamps).strftime('%Y-%m-%d')}"
        )

    stats = (
        f"Query: '{query_text}'\n"
        f"Records matched: {total} (showing {len(records)}){date_info}\n"
        f"Unique numbers: {len(nums)}\n"
        f"Service breakdown: {dict(svc)}\n"
        f"Direction breakdown: {dict(dirs)}\n"
    )

    try:
        return _ollama(
            [
                {"role": "system", "content": _NARRATIVE_SYSTEM},
                {"role": "user", "content": stats},
            ],
            temperature=0.3,
            num_predict=300,
        )
    except ChatModelUnavailable:
        return f"Found {total} CDR records matching your query{date_info}."


# ── public entry point ───────────────────────────────────────────────────────

def llm_search(db: Session, case_family_id, query_text: str) -> dict:
    """
    Parse `query_text`, apply filters (or answer directly), and return results with
    AI narrative. The AI is given full context about the actual uploaded CDR data.
    """
    # Build data context from uploaded file
    profile = analytics.data_profile(db, case_family_id)
    context = _build_context(profile)

    # Ask AI to classify and extract intent
    intent = _parse_intent(query_text, context)
    mode = intent.get("mode", "filter")

    if mode == "direct":
        # AI answered directly from the data context — no DB query needed
        direct_answer = intent.get("direct_answer", "")
        if not direct_answer:
            direct_answer = "I could not generate a direct answer. Try rephrasing your question."
        return {
            "mode": "direct",
            "narrative": direct_answer,
            "filters": {},
            "total": 0,
            "items": [],
            "data_profile": {
                "total_records": profile.get("total_records", 0),
                "date_range": profile.get("date_range"),
            },
        }

    # Filter mode: apply DB query
    filters = intent.get("filters", {})

    def _date(val: str | None):
        if not val:
            return None
        try:
            return dt.date.fromisoformat(str(val))
        except (ValueError, TypeError):
            return None

    min_dur = filters.get("min_duration")
    if min_dur is not None:
        try:
            min_dur = int(min_dur)
        except (ValueError, TypeError):
            min_dur = None

    total, records = analytics.search_records(
        db,
        case_family_id,
        q=filters.get("q"),
        party=filters.get("party"),
        service_type=filters.get("service_type"),
        direction=filters.get("direction"),
        date_from=_date(filters.get("date_from")),
        date_to=_date(filters.get("date_to")),
        min_duration=min_dur,
        include_duplicates=False,
        limit=200,
        offset=0,
    )

    narrative = _build_narrative(query_text, total, records, profile)

    return {
        "mode": "filter",
        "narrative": narrative,
        "filters": filters,
        "total": total,
        "items": records,
        "data_profile": {
            "total_records": profile.get("total_records", 0),
            "date_range": profile.get("date_range"),
        },
    }
