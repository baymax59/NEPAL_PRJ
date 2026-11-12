"""Reading cases for the API. Every query applies the caller's access condition."""

import datetime as dt

from sqlalchemy import ColumnElement, extract, func, select
from sqlalchemy.orm import Session, selectinload

from app.auth.access import AccessContext
from app.connectors.registry import attribution_for
from app.db.models import Case, CaseEntity
from app.explain.citations import case_citations
from app.schemas.cases import (
    CaseDetail,
    CaseFilters,
    CaseList,
    CaseListParams,
    CaseSummary,
    CountedValue,
    CourtMentionOut,
    DocumentOut,
    FilterOptions,
    TimelineEventOut,
    YearRange,
)

SORT_ORDERS = {
    "date_desc": (Case.primary_date.desc().nulls_last(), Case.display_id),
    "date_asc": (Case.primary_date.asc().nulls_last(), Case.display_id),
    "title": (Case.title.asc().nulls_last(), Case.display_id),
}


def filter_conditions(filters: CaseFilters) -> list[ColumnElement[bool]]:
    conditions = []
    if filters.year_from is not None:
        conditions.append(Case.primary_date >= dt.date(filters.year_from, 1, 1))
    if filters.year_to is not None:
        conditions.append(Case.primary_date < dt.date(filters.year_to + 1, 1, 1))
    if filters.outcome:
        conditions.append(Case.outcome.in_(filters.outcome))
    if filters.source_system:
        conditions.append(Case.source_system.in_(filters.source_system))
    return conditions


def list_cases(session: Session, access: AccessContext, params: CaseListParams) -> CaseList:
    where = [access.case_condition(), *filter_conditions(params)]
    total = session.scalar(select(func.count()).select_from(Case).where(*where))
    cases = session.scalars(
        select(Case).where(*where).order_by(*SORT_ORDERS[params.sort]).limit(params.limit).offset(params.offset)
    ).all()
    return CaseList(total=total, items=[CaseSummary.model_validate(case) for case in cases])


def case_exists(session: Session, display_id: str) -> bool:
    """For the audit log only: tells "denied" from "not found". Never shown to the user."""
    return session.scalar(select(func.count()).select_from(Case).where(Case.display_id == display_id)) > 0


def get_visible_case(session: Session, access: AccessContext, display_id: str) -> Case | None:
    """None if the case doesn't exist *or* the caller may not see it. Callers can't tell which."""
    return session.scalars(
        select(Case)
        .where(Case.display_id == display_id, access.case_condition())
        .options(selectinload(Case.documents), selectinload(Case.events))
    ).one_or_none()


def get_case_detail(session: Session, access: AccessContext, display_id: str) -> CaseDetail | None:
    case = get_visible_case(session, access, display_id)
    if case is None:
        return None

    return CaseDetail(
        **CaseSummary.model_validate(case).model_dump(),
        source_record_id=case.source_record_id,
        dates=case.dates,
        summary=case.summary,
        parties=case.parties,
        officials=case.officials,
        provisions=case_citations(session, [case.id]).get(case.id, []),
        courts=_courts_named(session, case.id),
        outcome_source_field=case.outcome_source_field,
        outcome_date=case.outcome_date,
        timeline=[TimelineEventOut.model_validate(event) for event in case.events],
        documents=[DocumentOut.model_validate(doc) for doc in case.documents],
        warnings=case.warnings,
        provenance=case.provenance,
        source_extra=case.source_extra,
        attribution=attribution_for(case.source_system),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _courts_named(session: Session, case_id) -> list[CourtMentionOut]:
    rows = session.scalars(select(CaseEntity).where(CaseEntity.case_id == case_id, CaseEntity.kind == "court")).all()
    merged: dict[str, CourtMentionOut] = {}
    for row in rows:  # merged across the case's documents
        court = merged.setdefault(row.value, CourtMentionOut(name=row.value, mentions=0, pages=[]))
        court.mentions += row.mentions
        court.pages = sorted(set(court.pages) | set(row.pages))
    return sorted(merged.values(), key=lambda c: (-c.mentions, c.name))


def filter_options(session: Session, access: AccessContext) -> FilterOptions:
    visible = access.case_condition()
    first, last = session.execute(
        select(func.min(extract("year", Case.primary_date)), func.max(extract("year", Case.primary_date))).where(
            visible
        )
    ).one()
    outcomes = session.execute(
        select(Case.outcome, func.count())
        .where(visible, Case.outcome.is_not(None))
        .group_by(Case.outcome)
        .order_by(func.count().desc(), Case.outcome)
    ).all()
    sources = session.execute(
        select(Case.source_system, func.count()).where(visible).group_by(Case.source_system).order_by(Case.source_system)
    ).all()
    return FilterOptions(
        years=YearRange(min=int(first), max=int(last)) if first is not None else None,
        outcomes=[CountedValue(value=value, count=count) for value, count in outcomes],
        source_systems=[CountedValue(value=value, count=count) for value, count in sources],
    )
