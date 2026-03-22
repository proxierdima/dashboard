from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class Validator(Base):
    __tablename__ = "validators"
    __table_args__ = (
        UniqueConstraint("chain_id", "operator_address", name="uq_validator_chain_operator"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    chain_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("networks.chain_id"),
        index=True,
    )

    moniker: Mapped[str | None] = mapped_column(String(200))
    operator_address: Mapped[str] = mapped_column(String(200), index=True)
    delegator_address: Mapped[str | None] = mapped_column(String(200))
    consensus_address: Mapped[str | None] = mapped_column(String(200))

    rpc_url: Mapped[str | None] = mapped_column(String(255))
    metrics_url: Mapped[str | None] = mapped_column(String(255))

    is_main: Mapped[int] = mapped_column(Integer, default=1)
    is_enabled: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    network = relationship(
        "Network",
        back_populates="validators",
        primaryjoin="foreign(Validator.chain_id) == Network.chain_id",
    )

    current_status = relationship(
        "ValidatorStatusCurrent",
        back_populates="validator",
        uselist=False,
        cascade="all, delete-orphan",
    )
    history = relationship(
        "ValidatorStatusHistory",
        back_populates="validator",
        cascade="all, delete-orphan",
    )


class ValidatorStatusCurrent(Base):
    __tablename__ = "validator_status_current"

    validator_id: Mapped[int] = mapped_column(ForeignKey("validators.id"), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(50), index=True)
    in_active_set: Mapped[int | None] = mapped_column(Integer)
    jailed: Mapped[int | None] = mapped_column(Integer)
    tombstoned: Mapped[int | None] = mapped_column(Integer)
    tokens: Mapped[str | None] = mapped_column(String(100))
    delegator_shares: Mapped[str | None] = mapped_column(String(100))
    commission_rate: Mapped[str | None] = mapped_column(String(50))
    commission_max_rate: Mapped[str | None] = mapped_column(String(50))
    commission_max_change_rate: Mapped[str | None] = mapped_column(String(50))
    min_self_delegation: Mapped[str | None] = mapped_column(String(100))
    self_delegation_amount: Mapped[str | None] = mapped_column(String(100))
    rank: Mapped[int | None] = mapped_column(Integer)
    voting_power: Mapped[str | None] = mapped_column(String(100))
    last_seen_height: Mapped[int | None] = mapped_column(Integer)
    last_checked_at: Mapped[DateTime | None] = mapped_column(DateTime, index=True)
    raw_json: Mapped[str | None] = mapped_column(String)

    validator = relationship("Validator", back_populates="current_status")


class ValidatorStatusHistory(Base):
    __tablename__ = "validator_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    validator_id: Mapped[int] = mapped_column(ForeignKey("validators.id"), index=True)
    status: Mapped[str | None] = mapped_column(String(50))
    in_active_set: Mapped[int | None] = mapped_column(Integer)
    jailed: Mapped[int | None] = mapped_column(Integer)
    tombstoned: Mapped[int | None] = mapped_column(Integer)
    tokens: Mapped[str | None] = mapped_column(String(100))
    commission_rate: Mapped[str | None] = mapped_column(String(50))
    rank: Mapped[int | None] = mapped_column(Integer)
    voting_power: Mapped[str | None] = mapped_column(String(100))
    last_seen_height: Mapped[int | None] = mapped_column(Integer)
    collected_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    raw_json: Mapped[str | None] = mapped_column(String)

    validator = relationship("Validator", back_populates="history")
