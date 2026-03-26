#!/usr/bin/env python3

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_FILE = ROOT_DIR / "validator_dashboard_chainid.db"
TEMPLATES = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))


def db_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_scalar(conn, query: str, params=()):
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0
    value = row[0]
    return 0 if value is None else value


def format_utc(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        normalized = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%H:%M %d-%m-%Y UTC")
    except Exception:
        return str(ts)


def format_number(value, decimals: int = 2) -> str:
    if value in (None, ""):
        return "—"
    try:
        num = float(value)
    except Exception:
        return str(value)

    if num.is_integer():
        return str(int(num))

    return f"{num:.{decimals}f}".rstrip("0").rstrip(".")


def format_amount_fixed(value, decimals: int = 2) -> str:
    if value in (None, ""):
        return "—"
    try:
        num = float(value)
    except Exception:
        return str(value)
    return f"{num:,.{decimals}f}".replace(",", " ")


def format_bytes_mb(value):
    if value in (None, "", 0, "0"):
        return "—"
    try:
        return f"{float(value) / 1024 / 1024:.1f} MB"
    except Exception:
        return str(value)


def format_yes_no(value) -> str:
    if value in (True, 1, "1", "true", "True", "yes", "Yes"):
        return "yes"
    if value in (False, 0, "0", "false", "False", "no", "No"):
        return "no"
    return "—"


def status_emoji(value):
    if value == "ok":
        return "🟢"
    if value == "warning":
        return "🟡"
    if value == "critical":
        return "🔴"
    return "⚪"


def classify_row(fetch_ok, height_lag):
    if int(fetch_ok or 0) == 0:
        return "critical"
    try:
        if height_lag is not None and int(height_lag) > 5:
            return "warning"
    except Exception:
        pass
    return "ok"


def get_dashboard_totals(conn):
    return {
        "networks": get_scalar(
            conn,
            """
            SELECT COUNT(DISTINCT v.chain_id)
            FROM validators v
            WHERE COALESCE(v.is_enabled, 1) = 1
            """,
        ),
        "ok": get_scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM validators v
            LEFT JOIN validator_status_current vs ON vs.validator_id = v.id
            WHERE COALESCE(v.is_enabled, 1) = 1
              AND COALESCE(vs.status_level, 'critical') = 'ok'
            """,
        ),
        "warning": get_scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM validators v
            LEFT JOIN validator_status_current vs ON vs.validator_id = v.id
            WHERE COALESCE(v.is_enabled, 1) = 1
              AND COALESCE(vs.status_level, 'critical') = 'warning'
            """,
        ),
        "critical": get_scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM validators v
            LEFT JOIN validator_status_current vs ON vs.validator_id = v.id
            WHERE COALESCE(v.is_enabled, 1) = 1
              AND COALESCE(vs.status_level, 'critical') = 'critical'
            """,
        ),
        "alerts": get_scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM validators v
            LEFT JOIN validator_status_current vs ON vs.validator_id = v.id
            WHERE COALESCE(v.is_enabled, 1) = 1
              AND COALESCE(vs.status_level, 'critical') != 'ok'
            """,
        ),
    }


def get_dashboard_rows(conn):
    rows = conn.execute(
        """
        SELECT
            v.id AS validator_id,
            v.chain_id,
            COALESCE(vs.moniker_snapshot, v.moniker, v.operator_address, 'unknown') AS moniker,
            v.operator_address AS valoper_address,
            v.delegator_address,

            n.name,
            COALESCE(n.display_name, n.name, v.chain_id) AS display_name,
            n.display_denom,
            n.base_denom,

            vs.fetch_ok,
            vs.fetch_error,
            vs.status_level,
            vs.validator_status,
            vs.jailed,

            vs.validator_tokens_raw,
            vs.validator_tokens_display,
            vs.network_bonded_tokens_raw,
            vs.network_bonded_tokens_display,
            vs.voting_power_percent,
            vs.apr_percent,

            vs.commission_rate_percent,

            vs.self_bonded_raw,
            vs.self_bonded_display,
            vs.self_bonded_percent,

            vs.updated_at

        FROM validators v
        LEFT JOIN networks n
               ON n.chain_id = v.chain_id
        LEFT JOIN validator_status_current vs
               ON vs.validator_id = v.id
        WHERE COALESCE(v.is_enabled, 1) = 1
        ORDER BY
            CASE COALESCE(vs.status_level, 'critical')
                WHEN 'critical' THEN 0
                WHEN 'warning' THEN 1
                WHEN 'ok' THEN 2
                ELSE 3
            END ASC,
            COALESCE(n.display_name, n.name, v.chain_id) ASC,
            COALESCE(vs.moniker_snapshot, v.moniker, v.operator_address, 'unknown') ASC
        """
    ).fetchall()

    result = []
    for row in rows:
        item = dict(row)

        overall_status = item.get("status_level") or "critical"
        if overall_status not in {"ok", "warning", "critical"}:
            overall_status = "critical"

        denom = item.get("display_denom") or item.get("base_denom") or ""

        item["overall_status"] = overall_status
        item["overall_emoji"] = status_emoji(overall_status)
        item["chain_display"] = item.get("display_name") or item.get("chain_id") or "—"
        item["updated_at_fmt"] = format_utc(item.get("updated_at"))

        item["voting_power_display"] = (
            f'{float(item["voting_power_percent"]):.4f}%'
            if item.get("voting_power_percent") is not None else "—"
        )

        item["total_bonded_tokens_display"] = (
            f'{format_amount_fixed(item.get("network_bonded_tokens_display"), 2)} {denom}'.strip()
            if item.get("network_bonded_tokens_display") is not None else "—"
        )

        item["commission_rate_display"] = (
            f'{float(item["commission_rate_percent"]):.2f}%'
            if item.get("commission_rate_percent") is not None else "—"
        )

        self_bonded_value = (
            f'{format_amount_fixed(item.get("self_bonded_display"), 2)} {denom}'.strip()
            if item.get("self_bonded_display") is not None else "—"
        )
        self_bonded_pct = (
            f'{float(item["self_bonded_percent"]):.2f}%'
            if item.get("self_bonded_percent") is not None else None
        )
        item["self_bonded_display_fmt"] = (
            f"{self_bonded_value} · {self_bonded_pct}"
            if self_bonded_value != "—" and self_bonded_pct
            else self_bonded_value
        )

        item["jailed_display"] = format_yes_no(item.get("jailed"))

        item["apr_display"] = (
            f'{float(item["apr_percent"]):.2f}%'
            if item.get("apr_percent") is not None else "—"
        )

        item["active_alerts_count"] = 1 if overall_status != "ok" else 0

        result.append(item)

    return result


@router.get("/dashboard")
def dashboard(request: Request):
    conn = db_connect()
    try:
        totals = get_dashboard_totals(conn)
        rows = get_dashboard_rows(conn)
    finally:
        conn.close()

    return TEMPLATES.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "totals": totals,
            "rows": rows,
        },
    )


@router.get("/dashboard/rewards")
def dashboard_rewards():
    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard/public-rpc")
def dashboard_public_rpc(request: Request):
    conn = db_connect()
    try:
        try:
            rows_raw = conn.execute(
                """
                SELECT
                    ne.id,
                    ne.chain_id,
                    COALESCE(n.display_name, n.name, ne.chain_id) AS network_name,
                    ne.url,
                    ne.label,
                    ne.priority,
                    ne.endpoint_type,
                    ne.is_enabled,
                    ne.status,
                    ne.http_status,
                    ne.latency_ms,
                    ne.remote_height,
                    ne.chain_id_reported,
                    ne.check_error AS error_message,
                    ne.last_checked_at AS checked_at
                FROM network_endpoints ne
                LEFT JOIN networks n
                  ON n.chain_id = ne.chain_id
                WHERE COALESCE(ne.is_public, 1) = 1
                  AND COALESCE(ne.is_enabled, 1) = 1
                ORDER BY
                    network_name ASC,
                    COALESCE(ne.priority, 999999) ASC,
                    ne.url ASC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows_raw = []

        def infer_endpoint_type(item: dict) -> str:
            label = str(item.get("label") or "").strip().lower()
            url = str(item.get("url") or "").strip().lower()

            if "grpc" in label:
                return "grpc"
            if "rest" in label or "/lcd" in label:
                return "rest"
            if "rpc" in label:
                return "rpc"

            # fallback: most public Cosmos REST urls are http(s) without websocket suffix
            if url.endswith("/websocket"):
                return "rpc"

            # if nothing explicit is available, default to rpc
            return "rpc"

        def fmt_checked_at(value):
            if not value:
                return "—"
            try:
                if isinstance(value, str):
                    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                else:
                    dt = value
                return dt.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                return str(value)

        groups_map = {}

        for row in rows_raw:
            item = dict(row)

            status_value = (item.get("status") or "").strip().upper()
            if status_value != "OK":
                continue

            endpoint_type = (item.get("endpoint_type") or "").strip().lower()

            if endpoint_type not in {"rpc", "rest", "grpc"}:
                endpoint_type = infer_endpoint_type(item)  # fallback только для старых записей

            item["endpoint_type"] = endpoint_type
            item["checked_at_fmt"] = fmt_checked_at(item.get("checked_at"))
            item["latency_ms_value"] = int(item.get("latency_ms") or 999999999)
            item["latency_fmt"] = f'{item["latency_ms_value"]} ms' if item.get("latency_ms") is not None else "—"
            item["remote_height_fmt"] = str(item.get("remote_height")) if item.get("remote_height") is not None else "—"

            chain_id = item.get("chain_id") or "unknown"
            if chain_id not in groups_map:
                groups_map[chain_id] = {
                    "chain_id": chain_id,
                    "network_name": item.get("network_name") or chain_id,
                    "rpc_items": [],
                    "rest_items": [],
                    "grpc_items": [],
                    "best_checked_at": item["checked_at_fmt"],
                }

            group = groups_map[chain_id]

            if endpoint_type == "rpc":
                group["rpc_items"].append(item)
            elif endpoint_type == "rest":
                group["rest_items"].append(item)
            elif endpoint_type == "grpc":
                group["grpc_items"].append(item)
            else:
                group["rpc_items"].append(item)

        rows = []
        for _, group in sorted(groups_map.items(), key=lambda x: x[1]["network_name"].lower()):
            group["rpc_items"] = sorted(group["rpc_items"], key=lambda x: (x["latency_ms_value"], x["url"]))[:3]
            group["rest_items"] = sorted(group["rest_items"], key=lambda x: (x["latency_ms_value"], x["url"]))[:3]
            group["grpc_items"] = sorted(group["grpc_items"], key=lambda x: (x["latency_ms_value"], x["url"]))[:3]

            all_items = group["rpc_items"] + group["rest_items"] + group["grpc_items"]
            if not all_items:
                continue

            best_item = min(all_items, key=lambda x: x["latency_ms_value"])
            group["best_latency_fmt"] = best_item["latency_fmt"]
            group["best_remote_height_fmt"] = best_item["remote_height_fmt"]
            group["checked_at_fmt"] = best_item["checked_at_fmt"]
            group["rpc_count"] = len(group["rpc_items"])
            group["rest_count"] = len(group["rest_items"])
            group["grpc_count"] = len(group["grpc_items"])
            group["total_count"] = group["rpc_count"] + group["rest_count"] + group["grpc_count"]

            rows.append(group)

    finally:
        conn.close()

    return TEMPLATES.TemplateResponse(
        "public_rpc.html",
        {
            "request": request,
            "rows": rows,
        },
    )


@router.get("/dashboard/alerts")
def dashboard_alerts(request: Request):
    return TEMPLATES.TemplateResponse("alerts.html", {"request": request, "rows": []})


@router.get("/dashboard/snapshots")
def dashboard_snapshots(request: Request):
    return TEMPLATES.TemplateResponse("snapshots.html", {"request": request, "rows": []})


@router.get("/dashboard/proposals")
def dashboard_proposals(request: Request):
    conn = db_connect()
    try:
        try:
            rows_raw = conn.execute(
                """
                SELECT
                    gp.proposal_id,
                    gp.chain_id,
                    COALESCE(n.display_name, n.name, gp.chain_id) AS network_name,
                    gp.title,
                    gp.status,
                    gp.voting_end_time,
                    gp.yes_votes,
                    gp.no_votes,
                    gp.abstain_votes,
                    gp.no_with_veto_votes,
                    gp.validator_voted,
                    gp.validator_vote_option
                FROM governance_proposals gp
                JOIN networks n
                  ON n.chain_id = gp.chain_id
                JOIN (
                    SELECT DISTINCT chain_id
                    FROM validators
                    WHERE COALESCE(is_enabled, 1) = 1
                ) v
                  ON v.chain_id = gp.chain_id
                WHERE COALESCE(gp.is_latest, 1) = 1
                ORDER BY
                    CASE
                        WHEN lower(COALESCE(gp.status, '')) IN ('voting_period', 'voting period', 'proposal_status_voting_period') THEN 0
                        ELSE 1
                    END,
                    gp.voting_end_time ASC,
                    network_name ASC,
                    gp.proposal_id DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows_raw = []

        rows = []
        now = datetime.now(timezone.utc)

        for row in rows_raw:
            item = dict(row)

            yes_votes = float(item.get("yes_votes") or 0)
            no_votes = float(item.get("no_votes") or 0)
            abstain_votes = float(item.get("abstain_votes") or 0)
            veto_votes = float(item.get("no_with_veto_votes") or 0)

            votes_map = {
                "YES": yes_votes,
                "NO": no_votes,
                "ABSTAIN": abstain_votes,
                "VETO": veto_votes,
            }
            majority = max(votes_map, key=votes_map.get) if any(votes_map.values()) else "—"

            our_vote_raw = (item.get("validator_vote_option") or "").strip()
            if not our_vote_raw:
                if int(item.get("validator_voted") or 0) == 1:
                    our_vote = "VOTED"
                else:
                    our_vote = "—"
            else:
                normalized = our_vote_raw.upper().replace("VOTE_OPTION_", "").replace("_", " ")
                if normalized == "NO WITH VETO":
                    normalized = "VETO"
                our_vote = normalized

            item["our_vote"] = our_vote
            item["majority"] = majority
            item["topic"] = item.get("title") or "—"

            status_value = (item.get("status") or "").strip().lower()
            if status_value in {"voting_period", "voting period", "proposal_status_voting_period"}:
                item["status_badge"] = "active"
            elif status_value in {"passed", "proposal_status_passed"}:
                item["status_badge"] = "ok"
            elif status_value in {"rejected", "failed", "proposal_status_rejected", "proposal_status_failed"}:
                item["status_badge"] = "critical"
            else:
                item["status_badge"] = "muted"

            voting_end_time = item.get("voting_end_time")
            item["voting_end_time_fmt"] = "—"
            item["deadline_status"] = "normal"

            if voting_end_time:
                try:
                    if isinstance(voting_end_time, str):
                        dt = datetime.fromisoformat(voting_end_time.replace("Z", "+00:00"))
                    else:
                        dt = voting_end_time

                    item["voting_end_time_fmt"] = dt.strftime("%Y-%m-%d %H:%M UTC")

                    diff = (dt - now).total_seconds()
                    if diff < 0:
                        item["deadline_status"] = "expired"
                    elif diff <= 6 * 3600:
                        item["deadline_status"] = "urgent"
                    else:
                        item["deadline_status"] = "normal"
                except Exception:
                    item["voting_end_time_fmt"] = str(voting_end_time)

            rows.append(item)

    finally:
        conn.close()

    return TEMPLATES.TemplateResponse(
        "proposals.html",
        {
            "request": request,
            "rows": rows,
        },
    )


@router.get("/validators/{validator_id}/details")
def validator_details(validator_id: int):
    conn = db_connect()
    try:
        row = conn.execute(
            """
            SELECT
                v.id AS validator_id,
                v.chain_id,
                COALESCE(v.moniker, v.operator_address, 'unknown') AS moniker,
                v.operator_address,
                v.delegator_address,
                v.rpc_url,
                v.metrics_url,
                vm.fetch_ok,
                vm.fetch_error,
                vm.current_height,
                vm.network_height,
                vm.height_lag,
                vm.last_signed_height,
                vm.signed_lag,
                vm.missed_blocks,
                vm.peers,
                vm.is_block_syncing,
                vm.validator_power,
                vm.validators_power,
                vm.validators_count,
                vm.voting_power_percent,
                vm.block_interval_avg_sec,
                vm.round_duration_avg_sec,
                vm.step_commit_avg_sec,
                vm.commit_avg_sec,
                vm.finalize_block_avg_sec,
                vm.query_avg_sec,
                vm.mempool_size,
                vm.block_size_bytes,
                vm.resident_memory_bytes,
                vm.open_fds,
                vm.goroutines,
                vm.cpu_seconds_total,
                vm.gc_pause_p50_sec,
                vm.updated_at
            FROM validators v
            LEFT JOIN validator_metrics_current vm ON vm.validator_id = v.id
            WHERE v.id = ?
            """,
            (validator_id,),
        ).fetchone()

        if not row:
            return JSONResponse({"error": "validator not found"}, status_code=404)

        item = dict(row)
        item["overall_status"] = classify_row(item.get("fetch_ok"), item.get("height_lag"))
        item["updated_at_fmt"] = format_utc(item.get("updated_at"))
        item["resident_memory_display"] = format_bytes_mb(item.get("resident_memory_bytes"))
        return JSONResponse(item)
    finally:
        conn.close()
