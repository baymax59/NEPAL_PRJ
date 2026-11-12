"""Provisions cited by cases, as stored by app/explain/indexing.py."""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentProvision
from app.schemas.cases import ProvisionCitation


def case_citations(session: Session, case_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ProvisionCitation]]:
    """Provisions each case cites, most-mentioned first (merged across its documents)."""
    rows = session.scalars(select(DocumentProvision).where(DocumentProvision.case_id.in_(case_ids))).all()
    merged: dict[uuid.UUID, dict[str, ProvisionCitation]] = defaultdict(dict)
    for row in rows:
        existing = merged[row.case_id].get(row.provision_key)
        if existing is None:
            merged[row.case_id][row.provision_key] = ProvisionCitation(
                key=row.provision_key, label=row.label, mentions=row.mention_count, pages=list(row.pages)
            )
        else:
            existing.mentions += row.mention_count
            existing.pages = sorted(set(existing.pages) | set(row.pages))
    return {
        case_id: sorted(by_key.values(), key=lambda c: (-c.mentions, c.label)) for case_id, by_key in merged.items()
    }
