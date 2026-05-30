import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    HANDOFF = "handoff"
    CLOSED = "closed"


class ConversationHandler(str, enum.Enum):
    BOT = "bot"
    HUMAN = "human"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Conversation(Base):
    __tablename__ = "conversations"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        String(10),
        nullable=False,
        default=ConversationStatus.ACTIVE,
    )
    # Sprint 3: replaces handled_by (DB enum) with plain VARCHAR for flexibility.
    # ConversationHandler Python enum is preserved for application-layer type safety.
    current_handler: Mapped[ConversationHandler] = mapped_column(
        String(10),
        nullable=False,
        default=ConversationHandler.BOT,
        server_default="bot",
    )
    # Non-null when current_handler == 'human'; the user who took control.
    handler_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Message(Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wa_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        String(16),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Sprint 3: NULL = sent by the bot; UUID = sent by a human user from the dashboard.
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
