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


