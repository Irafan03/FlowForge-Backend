"""
Credential management endpoints:

  POST   /credentials             → create (encrypt + store)
  GET    /credentials             → list (never returns secret data)
  GET    /credentials/{id}        → get one (no secret data)
  DELETE /credentials/{id}        → delete
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.repositories import credential_repo
from app.schemas.credential import CredentialCreate, CredentialRead
from app.services.credential_service import encrypt_data

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.post(
    "",
    response_model=CredentialRead,
    status_code=status.HTTP_201_CREATED,
    summary="Store a new credential (secret data is encrypted at rest)",
)
def create_credential(
    body: CredentialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CredentialRead:
    encrypted = encrypt_data(body.data)
    credential = credential_repo.create(
        db,
        user_id=current_user.id,
        name=body.name,
        type=body.type,
        encrypted_data=encrypted,
    )
    return credential  # type: ignore[return-value]


@router.get(
    "",
    response_model=list[CredentialRead],
    summary="List all credentials for the current user (no secret data)",
)
def list_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CredentialRead]:
    return credential_repo.list_by_user(db, current_user.id)  # type: ignore[return-value]


@router.get(
    "/{credential_id}",
    response_model=CredentialRead,
    summary="Get a single credential by ID (no secret data)",
)
def get_credential(
    credential_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CredentialRead:
    credential = credential_repo.get_by_id(db, credential_id, current_user.id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )
    return credential  # type: ignore[return-value]


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a credential",
)
def delete_credential(
    credential_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    credential = credential_repo.get_by_id(db, credential_id, current_user.id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )
    credential_repo.delete(db, credential)
