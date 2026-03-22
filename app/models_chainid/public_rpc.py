from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class PublicRpcEndpoint(Base):
    __tablename__ = "public_rpc_endpoints"
    __table_args__ = (
        UniqueConstraint("chain_id", "url", name="uq_public_rpc_chain_url"),
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
    is_enabled: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    network = relationship("Network")
    checks = relationship(
        "PublicRpcCheck",
        back_populates="endpoint",
        cascade="all, delete-orphan",
    )


class PublicRpcCheck(Base):
    __tablename__ = "public_rpc_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("public_rpc_endpoints.id"), index=True)

    status: Mapped[str] = mapped_column(String(20), index=True)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    remote_height: Mapped[int | None] = mapped_column(Integer)
    chain_id_reported: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    checked_at: Mapped[DateTime] = mapped_column(DateTime, index=True)

    endpoint = relationship("PublicRpcEndpoint", back_populates="checks")
