"""Integrations: the endpoints (phase CM-6, docs/case-management/09-integration-contract.md).

- POST /integrations/add-to-case is the contract for the Knight Hawk systems (Log Analyzer, CDR/IPDR, OSINT, alerts).
  It needs two credentials: the person's login (Authorization: Bearer ...), for whom the finding is added and whose
  rights apply, and the source's key (X-Integration-Key), which vouches for the record. The key is never logged.
- Imported findings are read like the rest of a case: only what the reader may see.
- Integration sources are managed by platform administrators; the fictional test source stands in for the real systems.
As everywhere in the module: every request is audited, anything not visible answers 404, nothing is deleted
(DELETE, PUT and PATCH answer 405).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, status

from app.auth.dependencies import CurrentUser
from app.casemgmt import history
from app.casemgmt import schemas as s
from app.casemgmt.access import get_family
from app.casemgmt.api import Audit, Audited, DbSession, IdempotencyKeyHeader
from app.casemgmt.errors import Invalid, NotVisible
from app.casemgmt.idempotency import Once
from app.casemgmt.integrations import contract, imports, sources, test_source
from app.core.config import get_settings

router = APIRouter(prefix="/v1", tags=["case management: integrations"])

IntegrationKey = Annotated[str | None, Header(alias="X-Integration-Key", max_length=120)]
KEY_NOTE = ("Copy this key now: it is shown only once and only its SHA-256 is stored. Give it to the source system's "
            "administrators through a secure channel. If it is lost or leaked, issue a new one: the old key stops working.")


def _finding(body: s.AddToCase | None = None, **fields) -> imports.Finding:
    data = body.model_dump(include={"item_type", "source_record_id", "source_hash", "summary", "title", "payload_ref", "authority_ref",
                                    "observed_at", "observed_until", "identifiers", "details", "message"}) if body else fields
    return imports.Finding(**data)


def _added(db, user, added: imports.Imported) -> dict:
    return {"entry": added.entry.seq, "finding": imports.described(db, added), "updated": added.updated}


def _source_out(db, user, source_id: uuid.UUID) -> dict:
    return next(x for x in sources.list_sources(db, user) if x["id"] == source_id)


# ---------------------------------------------------------------- the contract


@router.get("/integrations/contract", response_model=s.IntegrationContract)
def contract_view(_user: CurrentUser) -> dict:
    """What a finding may contain: item types, identifier types, limits and headers (version 1.0)."""
    return contract.describe()


@router.post("/integrations/add-to-case", response_model=s.ImportAdded, status_code=status.HTTP_201_CREATED)
def add_to_case(body: s.AddToCase, user: CurrentUser, db: DbSession, audit: Audit, integration_key: IntegrationKey = None,
                idempotency_key: IdempotencyKeyHeader = None):
    """Add a finding from an outside system to a case the person may add to: an immutable reference, a history entry and an audit event."""
    with Audited(db, audit, user, "cm.integration.import", "cm_case", body.case_id, item_type=body.item_type) as event:
        source = sources.authenticate(db, integration_key)
        event.details.update(source=source.code, key=source.key_prefix)
        once = Once(db, user, idempotency_key, "POST /api/v1/integrations/add-to-case", body.model_dump(mode="json"))
        if (previous := once.previous()) is not None:
            event.read(replayed=True)
            return previous
        family = get_family(db, user, body.case_id)
        event.target_id = family.display_id
        added = imports.add_to_case(db, user, family, source, _finding(body), key_prefix=source.key_prefix)
        result = _added(db, user, added)
        once.save(status.HTTP_201_CREATED, s.ImportAdded, result)
        event.write(entry=added.entry.seq, finding=added.artifact.display_id, version=added.version.version_number,
                    record=added.record.source_record_id, identifiers=len(result["finding"]["identifiers"]), updated=added.updated)
    return result


# ---------------------------------------------------------------- imported findings in a case


@router.get("/cases/{case_id}/imports", response_model=s.ImportsView)
def list_imports(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """The findings imported into the case."""
    with Audited(db, audit, user, "cm.integration.imports_read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = imports.imports_of(db, user, family)
        event.read(imports=len(result["imports"]))
    return result


@router.get("/cases/{case_id}/imports/{artifact_id}", response_model=s.ImportDetail)
def import_detail(case_id: uuid.UUID, artifact_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """One imported finding: provenance, versions, what uses it, and the other cases where its identifiers appear."""
    with Audited(db, audit, user, "cm.integration.import_read", "cm_case", case_id, artifact=artifact_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = imports.import_detail(db, user, family, artifact_id)
        event.read(finding=result["display_id"], matches=sum(len(i["other_cases"]) for i in result["identifiers"]))
    return result


@router.get("/cases/{case_id}/indicators", response_model=s.IndicatorsView)
def indicators_view(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Every identifier the case's imported findings name, with the other cases (that you can open) where it appears."""
    with Audited(db, audit, user, "cm.integration.indicators_read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = imports.indicators_of(db, user, family)
        event.read(identifiers=result["totals"]["identifiers"], with_matches=result["totals"]["with_matches"])
    return result


# ---------------------------------------------------------------- integration sources (platform administrators)


@router.get("/integrations/sources", response_model=list[s.IntegrationSourceOut])
def list_sources(user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    """The organisation's integration sources, with their access policies, key prefixes, use and history."""
    with Audited(db, audit, user, "cm.integration.sources_read", "cm_integration_source") as event:
        result = sources.list_sources(db, user)
        event.read(sources=len(result))
    return result


@router.post("/integrations/sources", response_model=s.SourceKeyIssued, status_code=status.HTTP_201_CREATED)
def register_source(body: s.SourceCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Register a source with its policy. Its key is in the answer, this once."""
    with Audited(db, audit, user, "cm.integration.source_registered", "cm_integration_source", body.code) as event:
        source, key = sources.register(db, user, **body.model_dump())
        result = {"source": _source_out(db, user, source.id), "key": key, "key_note": KEY_NOTE}
        event.write(source=source.code, key=source.key_prefix, allowed=source.allowed_item_types,
                    authority_required_for=source.authority_required_for, min_case_classification=source.min_case_classification)
    return result


@router.post("/integrations/sources/test-source", response_model=s.SourceKeyIssued, status_code=status.HTTP_201_CREATED)
def register_test_source(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Register the built-in fictional test source (it stands in for the real systems until they exist)."""
    with Audited(db, audit, user, "cm.integration.source_registered", "cm_integration_source", sources.TEST_SOURCE["code"]) as event:
        if not get_settings().cm_test_source:
            raise NotVisible()
        source, key = sources.register_test_source(db, user)
        result = {"source": _source_out(db, user, source.id), "key": key,
                  "key_note": KEY_NOTE + " The built-in test source doesn't need it; a test program calling the contract does."}
        event.write(source=source.code, key=source.key_prefix, fictional=True)
    return result


@router.post("/integrations/sources/{source_id}/status", response_model=s.IntegrationSourceOut)
def change_source_status(source_id: uuid.UUID, body: s.SourceStatusChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Enable or disable a source, with a reason. Disabling stops its key at once; what it added stays."""
    with Audited(db, audit, user, "cm.integration.source_status", "cm_integration_source", source_id, enabled=body.enabled) as event:
        source = sources.get_source(db, user, source_id)
        event.target_id = source.code
        sources.set_enabled(db, user, source, enabled=body.enabled, reason=body.reason)
        result = _source_out(db, user, source.id)
        event.write(status=source.status)
    return result


@router.post("/integrations/sources/{source_id}/key", response_model=s.SourceKeyIssued)
def rotate_source_key(source_id: uuid.UUID, body: s.SourceKeyRotation, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Issue a new key for a source; the old key stops working at once. The new key is in the answer, this once."""
    with Audited(db, audit, user, "cm.integration.source_key", "cm_integration_source", source_id) as event:
        source = sources.get_source(db, user, source_id)
        event.target_id = source.code
        old = source.key_prefix
        key = sources.rotate_key(db, user, source, reason=body.reason)
        result = {"source": _source_out(db, user, source.id), "key": key, "key_note": KEY_NOTE}
        event.write(old_key=old, key=source.key_prefix)
    return result


# ---------------------------------------------------------------- the fictional test source


def _test_source_on() -> None:
    if not get_settings().cm_test_source:
        raise NotVisible()


@router.get("/integrations/test-source", response_model=s.TestSourceView)
def test_source_view(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """The fictional findings the test source can add to a case, and whether an administrator has registered it."""
    with Audited(db, audit, user, "cm.integration.test_source_read", "cm_integration_source", sources.TEST_SOURCE["code"]) as event:
        _test_source_on()
        if user.organization_id is None:
            raise NotVisible()
        source = sources.test_source(db, user.organization_id)
        findings = [{**f, "item_type_label": contract.label(f["item_type"])} for f in test_source.catalogue()]
        result = {"registered": source is not None, "source": sources.source_ref(source) if source else None, "findings": findings,
                  "note": "FICTIONAL TEST SOURCE: it stands in for the Knight Hawk Log Analyzer, CDR/IPDR analysis, OSINT and alert "
                          "systems until they exist. Every finding is invented test data."}
        event.read(registered=source is not None)
    return result


@router.post("/integrations/test-source/send", response_model=s.ImportAdded, status_code=status.HTTP_201_CREATED)
def test_source_send(body: s.TestSourceSend, user: CurrentUser, db: DbSession, audit: Audit, idempotency_key: IdempotencyKeyHeader = None):
    """Add one fictional finding of the test source to a case you may add to, exactly as a real source would."""
    with Audited(db, audit, user, "cm.integration.import", "cm_case", body.case_id, finding=body.finding_id,
                 source=sources.TEST_SOURCE["code"]) as event:
        _test_source_on()
        once = Once(db, user, idempotency_key, "POST /api/v1/integrations/test-source/send", body.model_dump(mode="json"))
        if (previous := once.previous()) is not None:
            event.read(replayed=True)
            return previous
        family = get_family(db, user, body.case_id)
        event.target_id = family.display_id
        source = sources.test_source(db, user.organization_id)
        if source is None:
            raise Invalid("The fictional test source isn't registered yet: a platform administrator registers it under "
                          "Administration, Integration sources")
        finding = test_source.finding(body.finding_id)
        finding.message = body.message
        added = imports.add_to_case(db, user, family, source, finding, key_prefix=None)
        result = _added(db, user, added)
        once.save(status.HTTP_201_CREATED, s.ImportAdded, result)
        event.write(entry=added.entry.seq, finding=added.artifact.display_id, version=added.version.version_number,
                    record=added.record.source_record_id, identifiers=len(result["finding"]["identifiers"]), updated=added.updated,
                    item_type=added.record.item_type)
    return result
