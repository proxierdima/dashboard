from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class Network(Base):
    __tablename__ = "networks"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    directory: Mapped[str | None] = mapped_column(String(120), index=True)

    chain_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    chain_type: Mapped[str | None] = mapped_column(String(50))
    network_type: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(30))

    website: Mapped[str | None] = mapped_column(String(255))
    bech32_prefix: Mapped[str | None] = mapped_column(String(50))
    daemon_name: Mapped[str | None] = mapped_column(String(100))
    node_home: Mapped[str | None] = mapped_column(String(255))
    key_algos: Mapped[str | None] = mapped_column(Text)
    slip44: Mapped[int | None] = mapped_column(Integer)

    base_denom: Mapped[str | None] = mapped_column(String(100))
    display_denom: Mapped[str | None] = mapped_column(String(100))
    exponent: Mapped[int | None] = mapped_column(Integer)
    coingecko_id: Mapped[str | None] = mapped_column(String(120))

    fee_tokens: Mapped[str | None] = mapped_column(Text)
    fixed_min_gas_price: Mapped[str | None] = mapped_column(Text)
    low_gas_price: Mapped[str | None] = mapped_column(Text)
    average_gas_price: Mapped[str | None] = mapped_column(Text)
    high_gas_price: Mapped[str | None] = mapped_column(Text)
    staking_tokens: Mapped[str | None] = mapped_column(Text)

    git_repo: Mapped[str | None] = mapped_column(String(255))
    recommended_version: Mapped[str | None] = mapped_column(String(100))
    compatible_versions: Mapped[str | None] = mapped_column(Text)
    genesis_url: Mapped[str | None] = mapped_column(String(500))

    is_enabled: Mapped[int] = mapped_column(Integer, default=1)

    rpc: Mapped[str | None] = mapped_column(String, nullable=True)
    rest: Mapped[str | None] = mapped_column(String, nullable=True)
    grpc: Mapped[str | None] = mapped_column(String, nullable=True)

    rpc1: Mapped[str | None] = mapped_column(String, nullable=True)
    rest1: Mapped[str | None] = mapped_column(String, nullable=True)
    grpc1: Mapped[str | None] = mapped_column(String, nullable=True)

    rpc2: Mapped[str | None] = mapped_column(String, nullable=True)
    rest2: Mapped[str | None] = mapped_column(String, nullable=True)
    grpc2: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    endpoints = relationship(
        "NetworkEndpoint",
        back_populates="network",
        primaryjoin="Network.chain_id == foreign(NetworkEndpoint.chain_id)",
        cascade="all, delete-orphan",
    )
    validators = relationship(
        "Validator",
        back_populates="network",
        primaryjoin="Network.chain_id == foreign(Validator.chain_id)",
        cascade="all, delete-orphan",
    )