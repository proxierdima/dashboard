from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class PublicRpcEndpointCheck(Base):
    __tablename__ = "public_rpc_endpoints_checks"
    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "endpoint_type",
            "url",
            name="uq_public_rpc_endpoints_checks_chain_type_url",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("networks.chain_id"),
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), index=True)
    endpoint_type: Mapped[str] = mapped_column(String(20), index=True)
    label: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str | None] = mapped_column(String(50), index=True)

    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    selected_for_dashboard: Mapped[int] = mapped_column(Integer, default=0, index=True)

    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    remote_height: Mapped[int | None] = mapped_column(Integer)
    chain_id_reported: Mapped[str | None] = mapped_column(String(120))
    check_error: Mapped[str | None] = mapped_column(Text)

    consecutive_fail_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_ok_count: Mapped[int] = mapped_column(Integer, default=0)

    first_seen_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    last_checked_at: Mapped[DateTime | None] = mapped_column(DateTime, index=True)
    last_ok_at: Mapped[DateTime | None] = mapped_column(DateTime, index=True)
    last_fail_at: Mapped[DateTime | None] = mapped_column(DateTime, index=True)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    network = relationship("Network")
