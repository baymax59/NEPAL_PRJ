"""Integration sources: the outside systems allowed to add findings to cases, and their access policies.

- Only a platform administrator registers a source. It gets a **key**, shown once: the system sends it with every
  request (header X-Integration-Key). Only the key's SHA-256 is stored, so a stolen database can't be used to
  send findings. A lost or leaked key is replaced (rotated): the old one stops working at once.
- The **policy** is fixed when the source is registered: which kinds of findings it may add, for which kinds a
  legal authorisation reference is required, and the lowest case classification it may add to. A source with a
  different policy is registered as a new source, so every import names the exact policy it was accepted under.
- Disabling a source stops its key at once; what it added stays in the cases' history.
- Every change is a permanent integration_source_events row. Callers write the audit events.
"""

import hashlib
import hmac
import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.auth.mfa import require_strong_auth
from app.casemgmt import queries
from app.casemgmt.access import is_super_admin
from app.casemgmt.enums import ImportItemType, SourceEventType, SourceKind, SourceStatus
from app.casemgmt.errors import Forbidden, Invalid, NotVisible
from app.casemgmt.integrations import contract
from app.casemgmt.models import CaseFamily, IntegrationImport, IntegrationSource, IntegrationSourceEvent
from app.core.enums import Sensitivity
from app.db.models import User

KEY_START = "khi_"  # Knight Hawk integration key
KEY = re.compile(r"^khi_[A-Za-z0-9_-]{40,60}$")
CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
KINDS = {
    SourceKind.LOG_ANALYZER: "Log Analyzer", SourceKind.ALERTING: "Alerting", SourceKind.TELECOM: "CDR / IPDR analysis",
    SourceKind.OSINT: "OSINT", SourceKind.THREAT_INTEL: "Threat intelligence", SourceKind.FORENSIC_LAB: "Forensic laboratory",
    SourceKind.OTHER: "Other",
}

# The built-in fictional test source (test_source.py): its registration, offered to administrators in one click.
TEST_SOURCE = {
    "code": "fict-test-source",
    "name": "Fictional test source (Log Analyzer, CDR/IPDR, OSINT, alerts)",
    "kind": SourceKind.OTHER.value,
    "description": "FICTIONAL. Stands in for the Knight Hawk Log Analyzer, CDR/IPDR analysis, OSINT and alert systems "
                   "until they exist. Every finding it sends is invented test data.",
    "legal_basis": "FICTIONAL test data: no real person's data is obtained. A real source states here the authority its "
                   "data is obtained under (for example, requisitions to service providers).",
    "allowed_item_types": [t.value for t in ImportItemType],
    "authority_required_for": contract.AUTHORITY_BY_DEFAULT,
    "min_case_classification": Sensitivity.INTERNAL.value,
}


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> tuple[str, str, str]:
    """(the key, its SHA-256, its first characters to recognise it by)."""
    key = KEY_START + secrets.token_urlsafe(36)
    return key, _hash(key), key[:12]


def _require_admin(user: User, change: str | None = None) -> None:
    if not is_super_admin(user):
        raise Forbidden("Only platform administrators manage integration sources")
    if change:
        require_strong_auth(user, change)


def _reason(reason: str | None) -> str:
    reason = (reason or "").strip()
    if not 5 <= len(reason) <= 1000:
        raise Invalid("Say why (5 to 1,000 characters): the reason stays in the source's history")
    return reason


def register(session: Session, actor: User, *, code: str, name: str, kind: str, legal_basis: str,
             allowed_item_types: list[str], authority_required_for: list[str] | None = None,
             min_case_classification: str = Sensitivity.INTERNAL.value, description: str | None = None,
             fictional: bool = False) -> tuple[IntegrationSource, str]:
    """Register a source of the administrator's organisation. Returns it and its key (shown once, never stored)."""
    _require_admin(actor, "registering an integration source")
    code = (code or "").strip().lower()
    if not CODE.fullmatch(code):
        raise Invalid("The source's code is 2 to 63 lower-case letters, digits or '-', e.g. log-analyzer")
    if session.scalar(select(IntegrationSource.id).where(IntegrationSource.organization_id == actor.organization_id,
                                                         IntegrationSource.code == code)):
        raise Invalid(f"A source with the code {code} is already registered. A source's policy can't change: "
                      "register the new policy under a new code")
    name = contract.text(name, "The source's name", 200, minimum=3)
    try:
        kind = SourceKind(kind).value
    except ValueError:
        raise Invalid(f"Unknown kind of source: use one of {', '.join(k.value for k in SourceKind)}") from None
    legal_basis = contract.text(legal_basis, "The legal basis (under what authority the source's data is obtained)", 2000,
                                minimum=10)
    allowed = sorted({contract.item_type(t).value for t in allowed_item_types})
    if not allowed:
        raise Invalid("Choose at least one kind of finding the source may add")
    authority = sorted({contract.item_type(t).value for t in (authority_required_for if authority_required_for is not None
                                                             else [t for t in contract.AUTHORITY_BY_DEFAULT if t in allowed])})
    if not set(authority) <= set(allowed):
        raise Invalid("A legal authorisation can only be required for kinds of finding the source may add")
    try:
        minimum = Sensitivity(min_case_classification).value
    except ValueError:
        raise Invalid(f"Unknown classification: use one of {', '.join(s.value for s in Sensitivity)}") from None
    key, digest, prefix = new_key()
    source = IntegrationSource(organization_id=actor.organization_id, code=code, name=name, kind=kind,
                               description=contract.text(description, "The description", 2000), legal_basis=legal_basis,
                               allowed_item_types=allowed, authority_required_for=authority, min_case_classification=minimum,
                               fictional=fictional, status=SourceStatus.ENABLED.value, key_hash=digest, key_prefix=prefix,
                               created_by=actor.id)
    session.add(source)
    session.flush()
    session.add(IntegrationSourceEvent(source_id=source.id, event_type=SourceEventType.REGISTERED.value, actor_id=actor.id,
                                       reason="Registered", key_prefix=prefix))
    session.flush()
    return source, key


def register_test_source(session: Session, actor: User) -> tuple[IntegrationSource, str]:
    return register(session, actor, **TEST_SOURCE, fictional=True)


def get_source(session: Session, actor: User, source_id) -> IntegrationSource:
    """A source of the administrator's organisation (404 for anything else)."""
    _require_admin(actor)
    source = session.get(IntegrationSource, source_id)
    if source is None or source.organization_id != actor.organization_id:
        raise NotVisible(exists=source is not None)
    return source


def set_enabled(session: Session, actor: User, source: IntegrationSource, *, enabled: bool, reason: str) -> None:
    _require_admin(actor, "enabling or disabling an integration source")
    reason = _reason(reason)
    target = SourceStatus.ENABLED if enabled else SourceStatus.DISABLED
    if source.status == target:
        raise Invalid(f"{source.name} is already {target.value}")
    source.status = target.value
    session.add(IntegrationSourceEvent(source_id=source.id, actor_id=actor.id, reason=reason,
                                       event_type=(SourceEventType.ENABLED if enabled else SourceEventType.DISABLED).value))
    session.flush()


def rotate_key(session: Session, actor: User, source: IntegrationSource, *, reason: str) -> str:
    """Issue a new key; the old one stops working at once. Returns the new key (shown once)."""
    _require_admin(actor, "issuing a new integration key")
    reason = _reason(reason)
    key, digest, prefix = new_key()
    source.key_hash, source.key_prefix = digest, prefix
    source.key_issued_at = func.now()
    session.add(IntegrationSourceEvent(source_id=source.id, event_type=SourceEventType.KEY_ROTATED.value, actor_id=actor.id,
                                       reason=reason, key_prefix=prefix))
    session.flush()
    session.refresh(source)
    return key


def authenticate(session: Session, key: str | None) -> IntegrationSource:
    """The enabled source this key belongs to; Forbidden otherwise (the key is never logged)."""
    if not key or not KEY.fullmatch(key.strip()):
        raise Forbidden("A valid integration key (header X-Integration-Key) is required to add findings to a case")
    digest = _hash(key.strip())
    source = session.scalar(select(IntegrationSource).where(IntegrationSource.key_hash == digest))
    if source is None or not hmac.compare_digest(source.key_hash, digest):
        raise Forbidden("This integration key isn't valid: it may have been replaced")
    if source.status != SourceStatus.ENABLED:
        raise Forbidden(f"The source {source.name} is disabled: it can't add findings")
    return source


def test_source(session: Session, organization_id) -> IntegrationSource | None:
    return session.scalar(select(IntegrationSource).where(IntegrationSource.organization_id == organization_id,
                                                          IntegrationSource.code == TEST_SOURCE["code"],
                                                          IntegrationSource.fictional.is_(True)))


def check_policy(source: IntegrationSource, family: CaseFamily, kind: str, authority_ref: str | None) -> None:
    """The source's access policy for one finding (the person's own rights are checked by the caller)."""
    if source.organization_id != family.organization_id:
        raise Forbidden(f"{source.name} belongs to another organisation: it can't add findings to this case")
    if source.status != SourceStatus.ENABLED:
        raise Forbidden(f"The source {source.name} is disabled: it can't add findings")
    if kind not in source.allowed_item_types:
        raise Forbidden(f"{source.name} may add only: {', '.join(contract.label(t).lower() for t in source.allowed_item_types)}")
    if kind in source.authority_required_for and not authority_ref:
        raise Invalid(f"A {contract.label(kind).lower()} from {source.name} needs authority_ref: the legal authorisation "
                      "it was obtained under (a requisition or order number)")
    if source.min_case_classification not in sensitivities_up_to(family.classification):
        raise Forbidden(f"{source.name} may add findings only to cases classified {source.min_case_classification} or "
                        f"higher; this case is {family.classification}")


def policy(source: IntegrationSource) -> dict:
    return {"allowed_item_types": source.allowed_item_types, "authority_required_for": source.authority_required_for,
            "min_case_classification": source.min_case_classification, "legal_basis": source.legal_basis}


def source_ref(source: IntegrationSource) -> dict:
    return {"id": source.id, "code": source.code, "name": source.name, "kind": source.kind, "kind_label": KINDS.get(SourceKind(source.kind)),
            "fictional": source.fictional, "status": source.status}


def list_sources(session: Session, actor: User) -> list[dict]:
    """Every source of the administrator's organisation, with its policy, key prefix, use and history."""
    _require_admin(actor)
    sources = list(session.scalars(select(IntegrationSource).where(IntegrationSource.organization_id == actor.organization_id)
                                   .order_by(IntegrationSource.created_at)))
    ids = [s.id for s in sources]
    usage = {row.source_id: row for row in session.execute(
        select(IntegrationImport.source_id, func.count().label("imports"), func.count(func.distinct(IntegrationImport.case_family_id))
               .label("cases"), func.max(IntegrationImport.imported_at).label("last"))
        .where(IntegrationImport.source_id.in_(ids)).group_by(IntegrationImport.source_id))} if ids else {}
    events: dict = {}
    for event in session.scalars(select(IntegrationSourceEvent).where(IntegrationSourceEvent.source_id.in_(ids))
                                 .order_by(IntegrationSourceEvent.id)) if ids else []:
        events.setdefault(event.source_id, []).append(event)
    who = queries.people(session, [s.created_by for s in sources] + [e.actor_id for es in events.values() for e in es])
    return [{
        **source_ref(s), "description": s.description, "policy": policy(s), "key_prefix": s.key_prefix,
        "key_issued_at": s.key_issued_at, "created_by": who.get(s.created_by), "created_at": s.created_at,
        "imports": usage[s.id].imports if s.id in usage else 0, "cases": usage[s.id].cases if s.id in usage else 0,
        "last_import_at": usage[s.id].last if s.id in usage else None,
        "history": [{"event_type": e.event_type, "by": who.get(e.actor_id), "reason": e.reason, "key_prefix": e.key_prefix,
                     "at": e.occurred_at} for e in events.get(s.id, [])],
    } for s in sources]
