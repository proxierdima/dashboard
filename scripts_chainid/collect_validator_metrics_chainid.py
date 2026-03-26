#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DB_FILE = ROOT / "validator_dashboard_chainid.db"

LINE_RE = re.compile(
    r'^([a-zA-Z_:][a-zA-Z0-9_:]*)'
    r'(?:\{([^}]*)\})?'
    r'\s+'
    r'([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)$'
)
LABEL_RE = re.compile(r'(\w+)="([^"]*)"')

CURRENT_SNAPSHOT_COLUMNS = [
    "chain_id",
    "operator_address",
    "current_height",
    "network_height",
    "height_lag",
    "last_signed_height",
    "signed_lag",
    "missed_blocks",
    "peers",
    "is_block_syncing",
    "validator_power",
    "validators_power",
    "validators_count",
    "voting_power_percent",
    "block_interval_avg_sec",
    "round_duration_avg_sec",
    "step_new_height_avg_sec",
    "step_propose_avg_sec",
    "step_prevote_avg_sec",
    "step_precommit_avg_sec",
    "step_commit_avg_sec",
    "commit_avg_sec",
    "finalize_block_avg_sec",
    "process_proposal_avg_sec",
    "query_avg_sec",
    "flush_avg_sec",
    "block_processing_avg_ms",
    "mempool_size",
    "mempool_size_bytes",
    "block_size_bytes",
    "num_txs",
    "total_txs",
    "resident_memory_bytes",
    "virtual_memory_bytes",
    "open_fds",
    "max_fds",
    "goroutines",
    "threads",
    "cpu_seconds_total",
    "heap_alloc_bytes",
    "heap_inuse_bytes",
    "heap_sys_bytes",
    "heap_objects",
    "gc_pause_p50_sec",
    "gc_pause_max_sec",
]

HISTORY_ONLY_COLUMNS = [
    "block_interval_sum_sec",
    "block_interval_count",
    "round_duration_sum_sec",
    "round_duration_count",
    "step_new_height_sum_sec",
    "step_new_height_count",
    "step_propose_sum_sec",
    "step_propose_count",
    "step_prevote_sum_sec",
    "step_prevote_count",
    "step_precommit_sum_sec",
    "step_precommit_count",
    "step_commit_sum_sec",
    "step_commit_count",
    "commit_sum_sec",
    "commit_count",
    "finalize_block_sum_sec",
    "finalize_block_count",
    "process_proposal_sum_sec",
    "process_proposal_count",
    "query_sum_sec",
    "query_count",
    "flush_sum_sec",
    "flush_count",
    "block_processing_sum_sec",
    "block_processing_count",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS validator_metrics_current (
            validator_id INTEGER PRIMARY KEY,
            chain_id TEXT,
            operator_address TEXT,
            metrics_url TEXT,

            fetch_ok INTEGER DEFAULT 0,
            fetch_error TEXT,

            current_height INTEGER,
            network_height INTEGER,
            height_lag INTEGER,

            last_signed_height INTEGER,
            signed_lag INTEGER,
            missed_blocks INTEGER,

            peers INTEGER,
            is_block_syncing INTEGER,

            validator_power INTEGER,
            validators_power INTEGER,
            validators_count INTEGER,
            voting_power_percent REAL,

            block_interval_avg_sec REAL,
            round_duration_avg_sec REAL,
            step_new_height_avg_sec REAL,
            step_propose_avg_sec REAL,
            step_prevote_avg_sec REAL,
            step_precommit_avg_sec REAL,
            step_commit_avg_sec REAL,

            commit_avg_sec REAL,
            finalize_block_avg_sec REAL,
            process_proposal_avg_sec REAL,
            query_avg_sec REAL,
            flush_avg_sec REAL,
            block_processing_avg_ms REAL,

            mempool_size INTEGER,
            mempool_size_bytes INTEGER,
            block_size_bytes INTEGER,
            num_txs INTEGER,
            total_txs INTEGER,

            resident_memory_bytes INTEGER,
            virtual_memory_bytes INTEGER,
            open_fds INTEGER,
            max_fds INTEGER,
            goroutines INTEGER,
            threads INTEGER,
            cpu_seconds_total REAL,

            heap_alloc_bytes INTEGER,
            heap_inuse_bytes INTEGER,
            heap_sys_bytes INTEGER,
            heap_objects INTEGER,
            gc_pause_p50_sec REAL,
            gc_pause_max_sec REAL,

            raw_json TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS validator_metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            validator_id INTEGER NOT NULL,
            chain_id TEXT,
            operator_address TEXT,
            metrics_url TEXT,

            fetch_ok INTEGER DEFAULT 0,
            fetch_error TEXT,

            current_height INTEGER,
            network_height INTEGER,
            height_lag INTEGER,

            last_signed_height INTEGER,
            signed_lag INTEGER,
            missed_blocks INTEGER,

            peers INTEGER,
            is_block_syncing INTEGER,

            validator_power INTEGER,
            validators_power INTEGER,
            validators_count INTEGER,
            voting_power_percent REAL,

            block_interval_avg_sec REAL,
            round_duration_avg_sec REAL,
            step_new_height_avg_sec REAL,
            step_propose_avg_sec REAL,
            step_prevote_avg_sec REAL,
            step_precommit_avg_sec REAL,
            step_commit_avg_sec REAL,

            commit_avg_sec REAL,
            finalize_block_avg_sec REAL,
            process_proposal_avg_sec REAL,
            query_avg_sec REAL,
            flush_avg_sec REAL,
            block_processing_avg_ms REAL,

            block_interval_sum_sec REAL,
            block_interval_count REAL,
            round_duration_sum_sec REAL,
            round_duration_count REAL,
            step_new_height_sum_sec REAL,
            step_new_height_count REAL,
            step_propose_sum_sec REAL,
            step_propose_count REAL,
            step_prevote_sum_sec REAL,
            step_prevote_count REAL,
            step_precommit_sum_sec REAL,
            step_precommit_count REAL,
            step_commit_sum_sec REAL,
            step_commit_count REAL,
            commit_sum_sec REAL,
            commit_count REAL,
            finalize_block_sum_sec REAL,
            finalize_block_count REAL,
            process_proposal_sum_sec REAL,
            process_proposal_count REAL,
            query_sum_sec REAL,
            query_count REAL,
            flush_sum_sec REAL,
            flush_count REAL,
            block_processing_sum_sec REAL,
            block_processing_count REAL,

            mempool_size INTEGER,
            mempool_size_bytes INTEGER,
            block_size_bytes INTEGER,
            num_txs INTEGER,
            total_txs INTEGER,

            resident_memory_bytes INTEGER,
            virtual_memory_bytes INTEGER,
            open_fds INTEGER,
            max_fds INTEGER,
            goroutines INTEGER,
            threads INTEGER,
            cpu_seconds_total REAL,

            heap_alloc_bytes INTEGER,
            heap_inuse_bytes INTEGER,
            heap_sys_bytes INTEGER,
            heap_objects INTEGER,
            gc_pause_p50_sec REAL,
            gc_pause_max_sec REAL,

            raw_json TEXT,
            sampled_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_validator_metrics_history_validator_sampled ON validator_metrics_history (validator_id, sampled_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_validator_metrics_history_chain_sampled ON validator_metrics_history (chain_id, sampled_at)"
    )
    conn.commit()


def normalize_metrics_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if url.endswith("/metrics"):
        return url
    return url.rstrip("/") + "/metrics"


def parse_labels(labels_raw: str | None) -> dict[str, str]:
    if not labels_raw:
        return {}
    return dict(LABEL_RE.findall(labels_raw))


def to_number(value: str) -> int | float:
    num = float(value)
    if num.is_integer():
        return int(num)
    return num


def parse_prometheus_text(text: str) -> list[dict]:
    rows = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        name, labels_raw, value_raw = m.groups()
        rows.append(
            {
                "name": name,
                "labels": parse_labels(labels_raw),
                "value": to_number(value_raw),
            }
        )
    return rows


def rows_to_index(rows: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for row in rows:
        result.setdefault(row["name"], []).append(row)
    return result


def find_metric_value(index: dict[str, list[dict]], metric_name: str, required_labels: dict[str, str] | None = None):
    rows = index.get(metric_name, [])
    if not rows:
        return None

    if not required_labels:
        return rows[0]["value"]

    for row in rows:
        labels = row["labels"]
        if all(labels.get(k) == v for k, v in required_labels.items()):
            return row["value"]
    return None


def avg(sum_value, count_value):
    if sum_value is None or count_value in (None, 0):
        return None
    return float(sum_value) / float(count_value)


def detect_chain_id(index: dict[str, list[dict]], fallback_chain_id: str | None) -> str | None:
    for metric_name in (
        "cometbft_consensus_height",
        "cometbft_p2p_peers",
        "cometbft_blocksync_syncing",
    ):
        for row in index.get(metric_name, []):
            cid = row["labels"].get("chain_id")
            if cid:
                return cid
    return fallback_chain_id


def detect_validator_address(index: dict[str, list[dict]], fallback_operator: str | None) -> str | None:
    rows = index.get("cometbft_consensus_validator_last_signed_height", [])
    if rows:
        for row in rows:
            addr = row["labels"].get("validator_address")
            if addr:
                return addr
    return fallback_operator


def get_sum_count(index: dict[str, list[dict]], sum_metric: str, count_metric: str, labels: dict[str, str] | None = None):
    sum_value = find_metric_value(index, sum_metric, labels)
    count_value = find_metric_value(index, count_metric, labels)
    return sum_value, count_value, avg(sum_value, count_value)


def get_step_triplet(index: dict[str, list[dict]], chain_id: str, step: str):
    return get_sum_count(
        index,
        "cometbft_consensus_step_duration_seconds_sum",
        "cometbft_consensus_step_duration_seconds_count",
        {"chain_id": chain_id, "step": step},
    )


def get_abci_triplet(index: dict[str, list[dict]], chain_id: str, method: str):
    return get_sum_count(
        index,
        "cometbft_abci_connection_method_timing_seconds_sum",
        "cometbft_abci_connection_method_timing_seconds_count",
        {"chain_id": chain_id, "method": method, "type": "sync"},
    )


def extract_gc_quantiles(index: dict[str, list[dict]]):
    rows = index.get("go_gc_duration_seconds", [])
    p50 = None
    pmax = None
    for row in rows:
        q = row["labels"].get("quantile")
        if q == "0.5":
            p50 = row["value"]
        elif q == "1":
            pmax = row["value"]
    return p50, pmax


def build_snapshot(index: dict[str, list[dict]], fallback_chain_id: str | None, fallback_operator: str | None):
    chain_id = detect_chain_id(index, fallback_chain_id)
    operator_address = detect_validator_address(index, fallback_operator)

    if not chain_id:
        chain_id = fallback_chain_id

    current_height = find_metric_value(index, "cometbft_consensus_height", {"chain_id": chain_id}) if chain_id else None
    network_height = find_metric_value(index, "cometbft_consensus_latest_block_height", {"chain_id": chain_id}) if chain_id else None
    peers = find_metric_value(index, "cometbft_p2p_peers", {"chain_id": chain_id}) if chain_id else None
    block_syncing = find_metric_value(index, "cometbft_blocksync_syncing", {"chain_id": chain_id}) if chain_id else None

    last_signed_height = None
    missed_blocks = None
    validator_power = None

    if chain_id and operator_address:
        metric_labels = {"chain_id": chain_id, "validator_address": operator_address}
        last_signed_height = find_metric_value(index, "cometbft_consensus_validator_last_signed_height", metric_labels)
        missed_blocks = find_metric_value(index, "cometbft_consensus_validator_missed_blocks", metric_labels)
        validator_power = find_metric_value(index, "cometbft_consensus_validator_power", metric_labels)

    validators_power = find_metric_value(index, "cometbft_consensus_validators_power", {"chain_id": chain_id}) if chain_id else None
    validators_count = find_metric_value(index, "cometbft_consensus_validators", {"chain_id": chain_id}) if chain_id else None

    height_lag = None
    if current_height is not None and network_height is not None:
        height_lag = max(int(network_height) - int(current_height), 0)

    signed_lag = None
    if last_signed_height is not None and network_height is not None:
        signed_lag = max(int(network_height) - int(last_signed_height), 0)

    voting_power_percent = None
    if validator_power is not None and validators_power not in (None, 0):
        voting_power_percent = (float(validator_power) / float(validators_power)) * 100.0

    block_interval_sum_sec, block_interval_count, block_interval_avg_sec = (
        get_sum_count(
            index,
            "cometbft_consensus_block_interval_seconds_sum",
            "cometbft_consensus_block_interval_seconds_count",
            {"chain_id": chain_id},
        )
        if chain_id else (None, None, None)
    )
    round_duration_sum_sec, round_duration_count, round_duration_avg_sec = (
        get_sum_count(
            index,
            "cometbft_consensus_round_duration_seconds_sum",
            "cometbft_consensus_round_duration_seconds_count",
            {"chain_id": chain_id},
        )
        if chain_id else (None, None, None)
    )

    step_new_height_sum_sec, step_new_height_count, step_new_height_avg_sec = (
        get_step_triplet(index, chain_id, "NewHeight") if chain_id else (None, None, None)
    )
    step_propose_sum_sec, step_propose_count, step_propose_avg_sec = (
        get_step_triplet(index, chain_id, "Propose") if chain_id else (None, None, None)
    )
    step_prevote_sum_sec, step_prevote_count, step_prevote_avg_sec = (
        get_step_triplet(index, chain_id, "Prevote") if chain_id else (None, None, None)
    )
    step_precommit_sum_sec, step_precommit_count, step_precommit_avg_sec = (
        get_step_triplet(index, chain_id, "Precommit") if chain_id else (None, None, None)
    )
    step_commit_sum_sec, step_commit_count, step_commit_avg_sec = (
        get_step_triplet(index, chain_id, "Commit") if chain_id else (None, None, None)
    )

    commit_sum_sec, commit_count, commit_avg_sec = (
        get_abci_triplet(index, chain_id, "commit") if chain_id else (None, None, None)
    )
    finalize_block_sum_sec, finalize_block_count, finalize_block_avg_sec = (
        get_abci_triplet(index, chain_id, "finalize_block") if chain_id else (None, None, None)
    )
    process_proposal_sum_sec, process_proposal_count, process_proposal_avg_sec = (
        get_abci_triplet(index, chain_id, "process_proposal") if chain_id else (None, None, None)
    )
    query_sum_sec, query_count, query_avg_sec = (
        get_abci_triplet(index, chain_id, "query") if chain_id else (None, None, None)
    )
    flush_sum_sec, flush_count, flush_avg_sec = (
        get_abci_triplet(index, chain_id, "flush") if chain_id else (None, None, None)
    )

    block_processing_sum_sec, block_processing_count, block_processing_avg_sec = (
        get_sum_count(
            index,
            "cometbft_state_block_processing_time_sum",
            "cometbft_state_block_processing_time_count",
            {"chain_id": chain_id},
        )
        if chain_id else (None, None, None)
    )

    gc_p50, gc_pmax = extract_gc_quantiles(index)

    return {
        "chain_id": chain_id,
        "operator_address": operator_address,
        "current_height": int(current_height) if current_height is not None else None,
        "network_height": int(network_height) if network_height is not None else None,
        "height_lag": height_lag,
        "last_signed_height": int(last_signed_height) if last_signed_height is not None else None,
        "signed_lag": signed_lag,
        "missed_blocks": int(missed_blocks) if missed_blocks is not None else None,
        "peers": int(peers) if peers is not None else None,
        "is_block_syncing": int(block_syncing) if block_syncing is not None else None,
        "validator_power": int(validator_power) if validator_power is not None else None,
        "validators_power": int(validators_power) if validators_power is not None else None,
        "validators_count": int(validators_count) if validators_count is not None else None,
        "voting_power_percent": voting_power_percent,
        "block_interval_avg_sec": block_interval_avg_sec,
        "round_duration_avg_sec": round_duration_avg_sec,
        "step_new_height_avg_sec": step_new_height_avg_sec,
        "step_propose_avg_sec": step_propose_avg_sec,
        "step_prevote_avg_sec": step_prevote_avg_sec,
        "step_precommit_avg_sec": step_precommit_avg_sec,
        "step_commit_avg_sec": step_commit_avg_sec,
        "commit_avg_sec": commit_avg_sec,
        "finalize_block_avg_sec": finalize_block_avg_sec,
        "process_proposal_avg_sec": process_proposal_avg_sec,
        "query_avg_sec": query_avg_sec,
        "flush_avg_sec": flush_avg_sec,
        "block_processing_avg_ms": block_processing_avg_sec * 1000.0 if block_processing_avg_sec is not None else None,
        "block_interval_sum_sec": block_interval_sum_sec,
        "block_interval_count": block_interval_count,
        "round_duration_sum_sec": round_duration_sum_sec,
        "round_duration_count": round_duration_count,
        "step_new_height_sum_sec": step_new_height_sum_sec,
        "step_new_height_count": step_new_height_count,
        "step_propose_sum_sec": step_propose_sum_sec,
        "step_propose_count": step_propose_count,
        "step_prevote_sum_sec": step_prevote_sum_sec,
        "step_prevote_count": step_prevote_count,
        "step_precommit_sum_sec": step_precommit_sum_sec,
        "step_precommit_count": step_precommit_count,
        "step_commit_sum_sec": step_commit_sum_sec,
        "step_commit_count": step_commit_count,
        "commit_sum_sec": commit_sum_sec,
        "commit_count": commit_count,
        "finalize_block_sum_sec": finalize_block_sum_sec,
        "finalize_block_count": finalize_block_count,
        "process_proposal_sum_sec": process_proposal_sum_sec,
        "process_proposal_count": process_proposal_count,
        "query_sum_sec": query_sum_sec,
        "query_count": query_count,
        "flush_sum_sec": flush_sum_sec,
        "flush_count": flush_count,
        "block_processing_sum_sec": block_processing_sum_sec,
        "block_processing_count": block_processing_count,
        "mempool_size": find_metric_value(index, "cometbft_mempool_size", {"chain_id": chain_id}) if chain_id else None,
        "mempool_size_bytes": find_metric_value(index, "cometbft_mempool_size_bytes", {"chain_id": chain_id}) if chain_id else None,
        "block_size_bytes": find_metric_value(index, "cometbft_consensus_block_size_bytes", {"chain_id": chain_id}) if chain_id else None,
        "num_txs": find_metric_value(index, "cometbft_consensus_num_txs", {"chain_id": chain_id}) if chain_id else None,
        "total_txs": find_metric_value(index, "cometbft_consensus_total_txs", {"chain_id": chain_id}) if chain_id else None,
        "resident_memory_bytes": find_metric_value(index, "process_resident_memory_bytes"),
        "virtual_memory_bytes": find_metric_value(index, "process_virtual_memory_bytes"),
        "open_fds": find_metric_value(index, "process_open_fds"),
        "max_fds": find_metric_value(index, "process_max_fds"),
        "goroutines": find_metric_value(index, "go_goroutines"),
        "threads": find_metric_value(index, "go_threads"),
        "cpu_seconds_total": find_metric_value(index, "process_cpu_seconds_total"),
        "heap_alloc_bytes": find_metric_value(index, "go_memstats_heap_alloc_bytes"),
        "heap_inuse_bytes": find_metric_value(index, "go_memstats_heap_inuse_bytes"),
        "heap_sys_bytes": find_metric_value(index, "go_memstats_heap_sys_bytes"),
        "heap_objects": find_metric_value(index, "go_memstats_heap_objects"),
        "gc_pause_p50_sec": gc_p50,
        "gc_pause_max_sec": gc_pmax,
    }


def fetch_metrics(url: str, timeout: int = 6) -> str:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def upsert_current_metrics(
    conn: sqlite3.Connection,
    validator_id: int,
    metrics_url: str,
    snapshot: dict,
    fetch_ok: int,
    fetch_error: str | None,
    raw_json: str,
):
    insert_columns = [
        "validator_id",
        "chain_id",
        "operator_address",
        "metrics_url",
        "fetch_ok",
        "fetch_error",
        *CURRENT_SNAPSHOT_COLUMNS,
        "raw_json",
        "updated_at",
    ]
    update_columns = [col for col in insert_columns if col != "validator_id"]
    placeholders = ", ".join(["?"] * len(insert_columns))

    conn.execute(
        f"""
        INSERT INTO validator_metrics_current ({", ".join(insert_columns)})
        VALUES ({placeholders})
        ON CONFLICT(validator_id) DO UPDATE SET
            {", ".join(f"{col}=excluded.{col}" for col in update_columns)}
        """,
        (
            validator_id,
            snapshot.get("chain_id"),
            snapshot.get("operator_address"),
            metrics_url,
            fetch_ok,
            fetch_error,
            *(snapshot.get(col) for col in CURRENT_SNAPSHOT_COLUMNS),
            raw_json,
            utc_now_iso(),
        ),
    )


def insert_history_metrics(
    conn: sqlite3.Connection,
    validator_id: int,
    metrics_url: str,
    snapshot: dict,
    fetch_ok: int,
    fetch_error: str | None,
    raw_json: str,
):
    insert_columns = [
        "validator_id",
        "chain_id",
        "operator_address",
        "metrics_url",
        "fetch_ok",
        "fetch_error",
        *CURRENT_SNAPSHOT_COLUMNS,
        *HISTORY_ONLY_COLUMNS,
        "raw_json",
        "sampled_at",
    ]
    placeholders = ", ".join(["?"] * len(insert_columns))

    conn.execute(
        f"""
        INSERT INTO validator_metrics_history ({", ".join(insert_columns)})
        VALUES ({placeholders})
        """,
        (
            validator_id,
            snapshot.get("chain_id"),
            snapshot.get("operator_address"),
            metrics_url,
            fetch_ok,
            fetch_error,
            *(snapshot.get(col) for col in CURRENT_SNAPSHOT_COLUMNS),
            *(snapshot.get(col) for col in HISTORY_ONLY_COLUMNS),
            raw_json,
            utc_now_iso(),
        ),
    )


def persist_metrics_sample(
    conn: sqlite3.Connection,
    validator_id: int,
    metrics_url: str,
    snapshot: dict,
    fetch_ok: int,
    fetch_error: str | None,
):
    raw_json = json.dumps(snapshot, ensure_ascii=False)
    upsert_current_metrics(conn, validator_id, metrics_url, snapshot, fetch_ok, fetch_error, raw_json)
    insert_history_metrics(conn, validator_id, metrics_url, snapshot, fetch_ok, fetch_error, raw_json)


def main():
    conn = db_connect()
    ensure_tables(conn)

    validators = conn.execute(
        """
        SELECT id, chain_id, operator_address, metrics_url
        FROM validators
        WHERE COALESCE(is_enabled, 1) = 1
          AND metrics_url IS NOT NULL
          AND TRIM(metrics_url) <> ''
        ORDER BY chain_id ASC, operator_address ASC
        """
    ).fetchall()

    total = len(validators)
    ok = 0
    fail = 0

    for row in validators:
        validator_id = row["id"]
        chain_id = row["chain_id"]
        operator_address = row["operator_address"]
        metrics_url = normalize_metrics_url(row["metrics_url"])

        print(f"[FETCH] {chain_id} | {operator_address} | {metrics_url}")

        if not metrics_url:
            fail += 1
            persist_metrics_sample(
                conn,
                validator_id,
                row["metrics_url"] or "",
                {"chain_id": chain_id, "operator_address": operator_address},
                0,
                "empty metrics_url",
            )
            conn.commit()
            continue

        try:
            text = fetch_metrics(metrics_url)
            rows = parse_prometheus_text(text)
            index = rows_to_index(rows)
            snapshot = build_snapshot(index, chain_id, operator_address)
            persist_metrics_sample(conn, validator_id, metrics_url, snapshot, 1, None)
            conn.commit()
            ok += 1
            print(f"[OK] {chain_id}")
        except Exception as e:
            snapshot = {"chain_id": chain_id, "operator_address": operator_address}
            persist_metrics_sample(conn, validator_id, metrics_url, snapshot, 0, str(e))
            conn.commit()
            fail += 1
            print(f"[ERR] {chain_id} | {e}")

    conn.close()
    print(f"\nDone. total={total} ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
