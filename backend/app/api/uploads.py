"""Upload a new case document and find similar historical cases.

Analysts and admins only. Each upload belongs to the user who created it: other users get
"Upload not found" (the audit log records the attempt as denied).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session, selectinload

from app.audit.log import AuditLog, get_audit_log
from app.auth.access import AccessContext
from app.auth.dependencies import get_access_context, require_role
from app.core.config import get_settings
from app.core.enums import AuditOutcome, Role
from app.db.models import Upload, User
from app.db.session import get_db
from app.embeddings.model import Embedder, get_embedder
from app.schemas.cases import ProvisionCitation
from app.schemas.similar import SimilarCasesResponse, SimilarRequest, UploadOut
from app.similar.service import document_from_upload, find_similar_cases
from app.uploads.service import UploadRejected, delete_upload, save_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])

DbSession = Annotated[Session, Depends(get_db)]
Analyst = Annotated[User, Depends(require_role(Role.ANALYST, Role.ADMIN))]
Audit = Annotated[AuditLog, Depends(get_audit_log)]
OptionalEmbedder = Annotated[Embedder | None, Depends(get_embedder)]


def _to_out(upload: Upload) -> UploadOut:
    return UploadOut(
        id=upload.id,
        filename=upload.original_filename,
        size_bytes=upload.size_bytes,
        mime_type=upload.mime_type,
        page_count=upload.page_count,
        passages=len(upload.chunks),
        provisions=[ProvisionCitation(**p) for p in upload.provisions],
        warnings=upload.warnings,
        created_at=upload.created_at,
    )


def _own_upload(db: Session, upload_id: uuid.UUID, user: User, audit: AuditLog, action: str) -> Upload:
    upload = db.get(Upload, upload_id, options=[selectinload(Upload.chunks)])
    if upload is None or upload.owner_id != str(user.id):
        outcome = AuditOutcome.NOT_FOUND if upload is None else AuditOutcome.DENIED
        audit.record(action, outcome, user=user, target_type="upload", target_id=str(upload_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return upload


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
def create_upload(file: UploadFile, db: DbSession, user: Analyst, audit: Audit, embedder: OptionalEmbedder) -> UploadOut:
    settings = get_settings()
    try:
        upload = save_upload(
            db,
            settings.data_dir,
            file.filename,
            file.file,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
            embedder=embedder,
            owner_id=str(user.id),
        )
    except UploadRejected as exc:
        # The file name isn't recorded: it may contain names of people involved.
        audit.record("upload.create", AuditOutcome.REJECTED, user=user, details={"status": exc.status_code, "reason": exc.message})
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    audit.record(
        "upload.create",
        AuditOutcome.SUCCESS,
        user=user,
        target_type="upload",
        target_id=str(upload.id),
        details={"sha256": upload.sha256, "size_bytes": upload.size_bytes, "pages": upload.page_count},
    )
    return _to_out(upload)


@router.get("/{upload_id}", response_model=UploadOut)
def get_upload(upload_id: uuid.UUID, db: DbSession, user: Analyst, audit: Audit) -> UploadOut:
    upload = _own_upload(db, upload_id, user, audit, "upload.view")
    audit.record("upload.view", AuditOutcome.SUCCESS, user=user, target_type="upload", target_id=str(upload_id))
    return _to_out(upload)


@router.post("/{upload_id}/similar", response_model=SimilarCasesResponse)
def similar_to_upload(
    upload_id: uuid.UUID,
    request: SimilarRequest,
    db: DbSession,
    user: Analyst,
    access: Annotated[AccessContext, Depends(get_access_context)],
    audit: Audit,
    embedder: OptionalEmbedder,
) -> SimilarCasesResponse:
    document = document_from_upload(_own_upload(db, upload_id, user, audit, "upload.similar"))
    result = find_similar_cases(db, access, embedder, document, request.filters, request.limit, request.offset)
    audit.record(
        "upload.similar",
        AuditOutcome.SUCCESS,
        user=user,
        target_type="upload",
        target_id=str(upload_id),
        details={"total": result.total_cases},
    )
    return result


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_upload(upload_id: uuid.UUID, db: DbSession, user: Analyst, audit: Audit) -> Response:
    delete_upload(db, get_settings().data_dir, _own_upload(db, upload_id, user, audit, "upload.delete"))
    audit.record("upload.delete", AuditOutcome.SUCCESS, user=user, target_type="upload", target_id=str(upload_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
