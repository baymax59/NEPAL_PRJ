"""Idempotency keys for create requests (docs/case-management/06, "Conventions").

A client that isn't sure whether a create request arrived (a lost connection, a double click) sends it again
with the same `Idempotency-Key` header. The first answer is stored with the change, in the same transaction;
a repeat with the same key and the same request gets that answer back (header `Idempotent-Replay: true`)
instead of creating a duplicate. The same key with a different request is refused. Keys are per user and are
honoured for 24 hours.
"""

import datetime as dt
import re
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casemgmt import hashing
from app.casemgmt.errors import Invalid
from app.casemgmt.models import IdempotencyKey
from app.db.models import User

KEY = re.compile(r"^[A-Za-z0-9_.:-]{8,100}$")
REPLAY_WINDOW = dt.timedelta(hours=24)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Once:
    """with Audited(...) as event:
           once = Once(db, user, idempotency_key, "POST /api/v1/cases", body.model_dump(mode="json"))
           if (previous := once.previous()) is not None:
               event.read(replayed=True)
               return previous
           ... create ...
           once.save(201, s.CaseCreated, result)   # before event.write(), which commits both
    """

    def __init__(self, db: Session, user: User, key: str | None, endpoint: str, request: Any):
        self.db, self.user, self.endpoint = db, user, endpoint
        self.key = key.strip() if key else None
        if self.key is not None and not KEY.fullmatch(self.key):
            raise Invalid("An Idempotency-Key is 8 to 100 letters, digits or the characters _ . : -")
        self.request_hash = hashing.content_hash(jsonable_encoder(request))

    def previous(self) -> JSONResponse | None:
        """The stored answer to an earlier, identical request with this key; None if there wasn't one."""
        if self.key is None:
            return None
        row = self.db.scalar(select(IdempotencyKey).where(IdempotencyKey.user_id == self.user.id, IdempotencyKey.key == self.key))
        if row is None:
            return None
        if row.endpoint != self.endpoint or row.request_hash != self.request_hash:
            raise Invalid("This Idempotency-Key was already used for a different request: use a new key")
        if row.created_at < _now() - REPLAY_WINDOW:
            raise Invalid("This Idempotency-Key was used more than 24 hours ago: use a new key")
        return JSONResponse(status_code=row.status_code, content=row.response, headers={"Idempotent-Replay": "true"})

    def save(self, status_code: int, model: type[BaseModel], result: Any) -> None:
        """Keep the answer, shaped exactly as the endpoint returns it, in the same transaction as the change."""
        if self.key is None:
            return
        body = jsonable_encoder(model.model_validate(result))
        self.db.add(IdempotencyKey(user_id=self.user.id, key=self.key, endpoint=self.endpoint, request_hash=self.request_hash,
                                   status_code=status_code, response=body))
        self.db.flush()
