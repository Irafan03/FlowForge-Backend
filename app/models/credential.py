import uuid

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Credential(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Type: api_key, oauth2_google, telegram_bot, http_header
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Fernet-encrypted JSON blob — never store plaintext secrets
    encrypted_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="credentials")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Credential id={self.id} name={self.name!r} type={self.type!r}>"
