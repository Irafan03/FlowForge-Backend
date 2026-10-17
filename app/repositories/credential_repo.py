import uuid

from sqlalchemy.orm import Session

from app.models.credential import Credential


def create(
    db: Session,
    user_id: uuid.UUID,
    name: str,
    type: str,
    encrypted_data: bytes,
) -> Credential:
    cred = Credential(user_id=user_id, name=name, type=type, encrypted_data=encrypted_data)
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def get_by_id(db: Session, credential_id: uuid.UUID, user_id: uuid.UUID) -> Credential | None:
    return (
        db.query(Credential)
        .filter(Credential.id == credential_id, Credential.user_id == user_id)
        .first()
    )


def list_by_user(db: Session, user_id: uuid.UUID) -> list[Credential]:
    return db.query(Credential).filter(Credential.user_id == user_id).all()


def delete(db: Session, credential: Credential) -> None:
    db.delete(credential)
    db.commit()
