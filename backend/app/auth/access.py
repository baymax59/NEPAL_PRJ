"""Which cases a user may see.

Every query that reads cases, documents or chunks must include `access.case_condition()`.
Access is checked inside the query itself (never "fetch, then filter"), so restricted
records are never loaded for a user who may not see them.

A user sees a case if its sensitivity is at or below their clearance, or if they hold an
unexpired grant for that specific case (need-to-know access).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, or_

from app.core.enums import Sensitivity
from app.db.models import Case

# Lowest to highest.
SENSITIVITY_ORDER = [level.value for level in Sensitivity]


def sensitivities_up_to(clearance: str) -> frozenset[str]:
    return frozenset(SENSITIVITY_ORDER[: SENSITIVITY_ORDER.index(clearance) + 1])


@dataclass(frozen=True)
class AccessContext:
    user_id: uuid.UUID | None
    allowed_sensitivities: frozenset[str]
    granted_case_ids: frozenset[uuid.UUID] = frozenset()

    def case_condition(self) -> ColumnElement[bool]:
        visible = Case.sensitivity.in_(self.allowed_sensitivities)
        if self.granted_case_ids:
            return or_(visible, Case.id.in_(self.granted_case_ids))
        return visible


# For offline tools (e.g. scripts/evaluate.py) that run without a logged-in user: public only.
ANONYMOUS = AccessContext(user_id=None, allowed_sensitivities=sensitivities_up_to(Sensitivity.PUBLIC.value))
