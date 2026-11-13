"""The organisation: its name and the prefix of its case numbers (decision D13 in docs/DECISIONS.md).

New users join the first organisation (created by migration 0007 as the placeholder "KH"). Setting it up
changes that organisation's prefix and name, so everyone already in it stays in it. The prefix can change only
until the organisation's first case: case numbers such as KH-2026-0001 are permanent (the database enforces it).
"""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.casemgmt.models import CaseFamily, Organization
from app.db.models import User

CODE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")


def default_organisation(session: Session) -> Organization:
    return session.scalars(select(Organization).order_by(Organization.created_at)).first()


def overview(session: Session) -> list[dict]:
    cases = dict(session.execute(select(CaseFamily.organization_id, func.count()).group_by(CaseFamily.organization_id)).all())
    users = dict(session.execute(select(User.organization_id, func.count()).group_by(User.organization_id)).all())
    return [{"code": o.code, "name": o.name, "cases": cases.get(o.id, 0), "users": users.get(o.id, 0)}
            for o in session.scalars(select(Organization).order_by(Organization.created_at))]


def _name(name: str) -> str:
    name = (name or "").strip()
    if not 3 <= len(name) <= 200:
        raise ValueError("The organisation's name is 3 to 200 characters")
    return name


def set_up(session: Session, *, code: str, name: str) -> tuple[str, str]:
    """Set the default organisation's case-number prefix and name. Returns (old code, new code)."""
    code = (code or "").strip().upper()
    if not CODE.fullmatch(code):
        raise ValueError("The prefix is 2 to 8 capital letters or digits, starting with a letter (e.g. KH, TSP, MH01)")
    organisation = default_organisation(session)
    old = organisation.code
    if code != old:
        if session.scalar(select(func.count()).select_from(CaseFamily).where(CaseFamily.organization_id == organisation.id)):
            raise ValueError(f"{old} already has cases, so its prefix stays (case numbers are permanent); "
                             "only the name can still change")
        if session.scalar(select(Organization.id).where(Organization.code == code)):
            raise ValueError(f"Another organisation already uses the prefix {code}")
    organisation.code, organisation.name = code, _name(name)
    session.flush()
    return old, code


def rename(session: Session, *, code: str, name: str) -> None:
    organisation = session.scalar(select(Organization).where(Organization.code == (code or "").strip().upper()))
    if organisation is None:
        raise ValueError(f"No organisation with the prefix {code}")
    organisation.name = _name(name)
    session.flush()
