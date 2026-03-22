from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class NetworkEndpoint(Base):
    __tablename__ = "network_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "endpoint_type",
            "url",
            name="uq_network_endpoint_chain_type_url",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("networks.chain_id"),
        index=True,
    )
    endpoint_type: Mapped[str] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(20))
    url: Mapped[str] = mapped_column(String(500))
    priority: Mapped[int] = mapped_column(Integer, default=1)
    is_public: Mapped[int] = mapped_column(Integer, default=1)
    is_enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    network = relationship(
        "Network",
        back_populates="endpoints",
        primaryjoin="foreign(NetworkEndpoint.chain_id) == Network.chain_id",
    )
    checks = relationship(
        "EndpointCheck", back_populates="endpoint", cascade="all, delete-orphan"
    )


class EndpointCheck(Base):
    __tablename__ = "endpoint_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("network_endpoints.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    remote_height: Mapped[int | None] = mapped_column(Integer)
    chain_id_reported: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    checked_at: Mapped[DateTime] = mapped_column(DateTime, index=True)

    endpoint = relationship("NetworkEndpoint", back_populates="checks")
