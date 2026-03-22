from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_chainid.base import Base


class SnapshotTarget(Base):
    __tablename__ = "snapshot_targets"
    __table_args__ = (
        UniqueConstraint("chain_id", "name", name="uq_snapshot_target_chain_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("networks.chain_id"),
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), index=True)
    path: Mapped[str] = mapped_column(String(500))
    file_pattern: Mapped[str | None] = mapped_column(String(255))
    is_enabled: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    network = relationship(
        "Network",
        back_populates="snapshot_targets",
        primaryjoin="foreign(SnapshotTarget.chain_id) == Network.chain_id",
    )
    checks = relationship(
        "SnapshotCheck",
        back_populates="target",
        cascade="all, delete-orphan",
    )


class SnapshotCheck(Base):
    __tablename__ = "snapshot_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("snapshot_targets.id"), index=True)

    status: Mapped[str] = mapped_column(String(20), index=True)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    file_mtime: Mapped[DateTime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    checked_at: Mapped[DateTime] = mapped_column(DateTime, index=True)

    target = relationship("SnapshotTarget", back_populates="checks")
