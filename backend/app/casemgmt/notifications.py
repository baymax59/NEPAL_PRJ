"""Notices for users (docs/case-management/06, "Reports, notifications, MFA").

A notice says what happened and where, in a few words: the case number, a short title and
who did it. It never carries file names or evidence content. Notices are kept; reading one only records when.
The live stream (Server-Sent Events) comes with the screens (phase CM-4); until then they are listed on request.
"""

from collections.abc import Iterable

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.casemgmt.models import CaseFamily, Notification
from app.db.models import User


def notify(session: Session, user_ids: Iterable, kind: str, *, family: CaseFamily | None = None,
           actor: User | None = None, **payload) -> None:
    """Add a notice for each user (never for the person who caused it)."""
    body = jsonable_encoder({
        **({"case": family.display_id, "case_id": str(family.id)} if family else {}),  # the id lets a screen link to the case
        **({"by": actor.display_name} if actor else {}),
        **payload,
    })
    for user_id in {u for u in user_ids if u is not None and (actor is None or u != actor.id)}:
        session.add(Notification(user_id=user_id, kind=kind, case_family_id=family.id if family else None,
                                 payload=body))
    session.flush()
