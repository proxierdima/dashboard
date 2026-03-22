from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class NetworkAsset(Base):
    __tablename__ = "network_assets"
    __table_args__ = (
        UniqueConstraint("chain_id", "base_denom", name="uq_network_asset_chain_base_denom"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("networks.chain_id"),
        index=True,
    )

    base_denom: Mapped[str] = mapped_column(String(200), index=True)
    symbol: Mapped[str | None] = mapped_column(String(100), index=True)
    display: Mapped[str | None] = mapped_column(String(100))
    display_denom: Mapped[str | None] = mapped_column(String(100), index=True)
    exponent: Mapped[int | None] = mapped_column(Integer)
    coingecko_id: Mapped[str | None] = mapped_column(String(120), index=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    network = relationship("Network")
