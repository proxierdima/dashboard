from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class NetworkStatusCurrent(Base):
    __tablename__ = "network_status_current"

    chain_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("networks.chain_id"),
        primary_key=True,
    )

    status: Mapped[str | None] = mapped_column(String(50), index=True)
    latest_height: Mapped[int | None] = mapped_column(Integer)
    active_validators: Mapped[int | None] = mapped_column(Integer)
    bonded_tokens: Mapped[str | None] = mapped_column(String(100))
    inflation: Mapped[str | None] = mapped_column(String(50))
    community_pool: Mapped[str | None] = mapped_column(String(200))
    staking_apr: Mapped[str | None] = mapped_column(String(50))
    last_checked_at: Mapped[DateTime | None] = mapped_column(DateTime, index=True)
    raw_json: Mapped[str | None] = mapped_column(String)
    overall_status: Mapped[str | None] = mapped_column(String(50))
    validator_status: Mapped[str | None] = mapped_column(String(50))
    sync_status: Mapped[str | None] = mapped_column(String(50))
    snapshot_status: Mapped[str | None] = mapped_column(String(50))
    local_height: Mapped[str | None] = mapped_column(String(50))
    reference_height: Mapped[str | None] = mapped_column(String(50))
    sync_diff: Mapped[str | None] = mapped_column(String(50))
    active_alerts_count: Mapped[str | None] = mapped_column(String(50))
    last_updated_at: Mapped[DateTime] = mapped_column(DateTime)

    network = relationship("Network")
