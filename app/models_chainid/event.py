from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[str | None] = mapped_column(
        String(120),
        ForeignKey("networks.chain_id"),
        index=True,
    )

    source: Mapped[str] = mapped_column(String(50), index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(String(50), index=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), index=True)

    network = relationship("Network")
