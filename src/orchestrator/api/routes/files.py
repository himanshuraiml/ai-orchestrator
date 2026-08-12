import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.api.deps import get_context_manager, get_db
from orchestrator.api.routes.tasks import DEFAULT_USER_ID
from orchestrator.config.settings import get_settings
from orchestrator.context.manager import ContextManager
from orchestrator.db.repositories import artifacts as artifacts_repo
from orchestrator.db.repositories import documents as documents_repo

router = APIRouter(tags=["files"])


class FileUploadResponse(BaseModel):
    file_id: uuid.UUID
    document_id: uuid.UUID
    chunk_count: int


@router.post("/v1/files", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    context_manager: ContextManager = Depends(get_context_manager),
) -> FileUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename")

    upload_root = Path(get_settings().artifact_root) / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    storage_path = upload_root / f"{uuid.uuid4()}_{safe_name}"

    contents = await file.read()
    storage_path.write_bytes(contents)

    artifact = await artifacts_repo.create_artifact(
        db,
        user_id=DEFAULT_USER_ID,
        name=safe_name,
        mime_type=file.content_type or "application/octet-stream",
        storage_uri=str(storage_path),
        size_bytes=len(contents),
        checksum=hashlib.sha256(contents).hexdigest(),
    )

    try:
        document = await context_manager.ingest_file(db, artifact.id)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Failed to ingest file: {exc}") from exc

    await db.commit()

    chunks = await documents_repo.list_chunks_for_document(db, document.id)

    return FileUploadResponse(file_id=artifact.id, document_id=document.id, chunk_count=len(chunks))
