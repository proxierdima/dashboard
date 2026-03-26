from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class ValidatorStatusCurrent(Base):
    __tablename__ = "validator_status_current"
    __table_args__ = (
        Index("ix_validator_status_current_chain_status", "chain_id", "status_level"),
        Index("ix_validator_status_current_chain_updated", "chain_id", "updated_at"),
    )

    validator_id: Mapped[int] = mapped_column(
        ForeignKey("validators.id"),
        primary_key=True,
    )

    chain_id: Mapped[str | None] = mapped_column(String(120), index=True)
    operator_address: Mapped[str | None] = mapped_column(String(200), index=True)
    delegator_address: Mapped[str | None] = mapped_column(String(200))
    consensus_address: Mapped[str | None] = mapped_column(String(200))
    moniker_snapshot: Mapped[str | None] = mapped_column(String(200))

    fetch_ok: Mapped[int] = mapped_column(Integer, default=0, index=True)
    fetch_error: Mapped[str | None] = mapped_column(Text)
    fetch_duration_ms: Mapped[int | None] = mapped_column(Integer)
    http_status: Mapped[int | None] = mapped_column(Integer)
    rest_url_used: Mapped[str | None] = mapped_column(String(500))
    rpc_url_used: Mapped[str | None] = mapped_column(String(500))

    validator_exists: Mapped[int] = mapped_column(Integer, default=0)
    validator_status: Mapped[str | None] = mapped_column(String(30), index=True)
    jailed: Mapped[int | None] = mapped_column(Integer, index=True)
    status_level: Mapped[str] = mapped_column(String(20), default="critical", index=True)

    validator_tokens_raw: Mapped[str | None] = mapped_column(Text)
    validator_tokens_display: Mapped[float | None] = mapped_column(Float)
    network_bonded_tokens_raw: Mapped[str | None] = mapped_column(Text)
    network_bonded_tokens_display: Mapped[float | None] = mapped_column(Float)
    voting_power_percent: Mapped[float | None] = mapped_column(Float)
    annual_provisions_raw: Mapped[str | None] = mapped_column(Text)
    apr_percent: Mapped[float | None] = mapped_column(Float, index=True)
    annual_provisions_raw: Mapped[str | None] = mapped_column(Text)
    apr_percent: Mapped[float | None] = mapped_column(Float, index=True)

    commission_rate_percent: Mapped[float | None] = mapped_column(Float)
    commission_max_rate_percent: Mapped[float | None] = mapped_column(Float)
    commission_max_change_rate_percent: Mapped[float | None] = mapped_column(Float)

    self_bonded_raw: Mapped[str | None] = mapped_column(Text)
    self_bonded_display: Mapped[float | None] = mapped_column(Float)
    self_bonded_percent: Mapped[float | None] = mapped_column(Float)

    reward_commission_primary_denom: Mapped[str | None] = mapped_column(String(100))
    reward_commission_primary_raw: Mapped[str | None] = mapped_column(Text)
    reward_commission_primary_display: Mapped[float | None] = mapped_column(Float)
    reward_commission_display: Mapped[str | None] = mapped_column(String(255))
    reward_commission_raw_json: Mapped[str | None] = mapped_column(Text)

    raw_json: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[DateTime | None] = mapped_column(DateTime, index=True)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    validator = relationship("Validator")


class ValidatorStatusHistory(Base):
    __tablename__ = "validator_status_history"
    __table_args__ = (
        Index("ix_validator_status_history_validator_sampled", "validator_id", "sampled_at"),
        Index("ix_validator_status_history_chain_sampled", "chain_id", "sampled_at"),
        Index("ix_validator_status_history_status_sampled", "status_level", "sampled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validator_id: Mapped[int] = mapped_column(ForeignKey("validators.id"), index=True)

    chain_id: Mapped[str | None] = mapped_column(String(120), index=True)
    operator_address: Mapped[str | None] = mapped_column(String(200), index=True)
    delegator_address: Mapped[str | None] = mapped_column(String(200))
    consensus_address: Mapped[str | None] = mapped_column(String(200))
    moniker_snapshot: Mapped[str | None] = mapped_column(String(200))

    fetch_ok: Mapped[int] = mapped_column(Integer, default=0, index=True)
    fetch_error: Mapped[str | None] = mapped_column(Text)
    fetch_duration_ms: Mapped[int | None] = mapped_column(Integer)
    http_status: Mapped[int | None] = mapped_column(Integer)
    rest_url_used: Mapped[str | None] = mapped_column(String(500))
    rpc_url_used: Mapped[str | None] = mapped_column(String(500))

    validator_exists: Mapped[int] = mapped_column(Integer, default=0)
    validator_status: Mapped[str | None] = mapped_column(String(30), index=True)
    jailed: Mapped[int | None] = mapped_column(Integer, index=True)
    status_level: Mapped[str] = mapped_column(String(20), default="critical", index=True)

    validator_tokens_raw: Mapped[str | None] = mapped_column(Text)
    validator_tokens_display: Mapped[float | None] = mapped_column(Float)
    network_bonded_tokens_raw: Mapped[str | None] = mapped_column(Text)
    network_bonded_tokens_display: Mapped[float | None] = mapped_column(Float)
    voting_power_percent: Mapped[float | None] = mapped_column(Float)
    annual_provisions_raw: Mapped[str | None] = mapped_column(Text)
    apr_percent: Mapped[float | None] = mapped_column(Float, index=True)
    annual_provisions_raw: Mapped[str | None] = mapped_column(Text)
    apr_percent: Mapped[float | None] = mapped_column(Float, index=True)

    commission_rate_percent: Mapped[float | None] = mapped_column(Float)
    commission_max_rate_percent: Mapped[float | None] = mapped_column(Float)
    commission_max_change_rate_percent: Mapped[float | None] = mapped_column(Float)

    self_bonded_raw: Mapped[str | None] = mapped_column(Text)
    self_bonded_display: Mapped[float | None] = mapped_column(Float)
    self_bonded_percent: Mapped[float | None] = mapped_column(Float)

    reward_commission_primary_denom: Mapped[str | None] = mapped_column(String(100))
    reward_commission_primary_raw: Mapped[str | None] = mapped_column(Text)
    reward_commission_primary_display: Mapped[float | None] = mapped_column(Float)
    reward_commission_display: Mapped[str | None] = mapped_column(String(255))
    reward_commission_raw_json: Mapped[str | None] = mapped_column(Text)

    raw_json: Mapped[str | None] = mapped_column(Text)
    sampled_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )

    validator = relationship("Validator")
