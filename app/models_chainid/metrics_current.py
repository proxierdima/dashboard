from sqlalchemy import Integer, String, Float, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models_chainid.base import Base


class ValidatorMetricsCurrent(Base):
    __tablename__ = "validator_metrics_current"

    validator_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    chain_id: Mapped[str | None] = mapped_column(String(100), index=True)
    operator_address: Mapped[str | None] = mapped_column(String(200), index=True)
    metrics_url: Mapped[str | None] = mapped_column(String(255))

    fetch_ok: Mapped[int] = mapped_column(Integer, default=0)
    fetch_error: Mapped[str | None] = mapped_column(Text)

    current_height: Mapped[int | None] = mapped_column(Integer)
    network_height: Mapped[int | None] = mapped_column(Integer)
    height_lag: Mapped[int | None] = mapped_column(Integer)

    last_signed_height: Mapped[int | None] = mapped_column(Integer)
    signed_lag: Mapped[int | None] = mapped_column(Integer)
    missed_blocks: Mapped[int | None] = mapped_column(Integer)

    peers: Mapped[int | None] = mapped_column(Integer)
    is_block_syncing: Mapped[int | None] = mapped_column(Integer)

    validator_power: Mapped[int | None] = mapped_column(Integer)
    validators_power: Mapped[int | None] = mapped_column(Integer)
    validators_count: Mapped[int | None] = mapped_column(Integer)
    voting_power_percent: Mapped[float | None] = mapped_column(Float)

    block_interval_avg_sec: Mapped[float | None] = mapped_column(Float)
    round_duration_avg_sec: Mapped[float | None] = mapped_column(Float)
    step_new_height_avg_sec: Mapped[float | None] = mapped_column(Float)
    step_propose_avg_sec: Mapped[float | None] = mapped_column(Float)
    step_prevote_avg_sec: Mapped[float | None] = mapped_column(Float)
    step_precommit_avg_sec: Mapped[float | None] = mapped_column(Float)
    step_commit_avg_sec: Mapped[float | None] = mapped_column(Float)

    commit_avg_sec: Mapped[float | None] = mapped_column(Float)
    finalize_block_avg_sec: Mapped[float | None] = mapped_column(Float)
    process_proposal_avg_sec: Mapped[float | None] = mapped_column(Float)
    query_avg_sec: Mapped[float | None] = mapped_column(Float)
    flush_avg_sec: Mapped[float | None] = mapped_column(Float)
    block_processing_avg_ms: Mapped[float | None] = mapped_column(Float)

    mempool_size: Mapped[int | None] = mapped_column(Integer)
    mempool_size_bytes: Mapped[int | None] = mapped_column(Integer)
    block_size_bytes: Mapped[int | None] = mapped_column(Integer)
    num_txs: Mapped[int | None] = mapped_column(Integer)
    total_txs: Mapped[int | None] = mapped_column(Integer)

    resident_memory_bytes: Mapped[int | None] = mapped_column(Integer)
    virtual_memory_bytes: Mapped[int | None] = mapped_column(Integer)
    open_fds: Mapped[int | None] = mapped_column(Integer)
    max_fds: Mapped[int | None] = mapped_column(Integer)
    goroutines: Mapped[int | None] = mapped_column(Integer)
    threads: Mapped[int | None] = mapped_column(Integer)
    cpu_seconds_total: Mapped[float | None] = mapped_column(Float)

    heap_alloc_bytes: Mapped[int | None] = mapped_column(Integer)
    heap_inuse_bytes: Mapped[int | None] = mapped_column(Integer)
    heap_sys_bytes: Mapped[int | None] = mapped_column(Integer)
    heap_objects: Mapped[int | None] = mapped_column(Integer)
    gc_pause_p50_sec: Mapped[float | None] = mapped_column(Float)
    gc_pause_max_sec: Mapped[float | None] = mapped_column(Float)

    raw_json: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(String(50), index=True)
