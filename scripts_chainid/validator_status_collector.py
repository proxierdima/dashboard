#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from decimal import Decimal, InvalidOperation
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.models_chainid import (
    Network,
    NetworkEndpoint,
    Validator,
    ValidatorStatusCurrent,
    ValidatorStatusHistory,
)

HTTP_TIMEOUT = 8
MAX_WORKERS = 16
MAX_ENDPOINTS_PER_TYPE = 3
USER_AGENT = "validator-status-collector/1.0"


@dataclass
class ValidatorTask:
    validator_id: int
    chain_id: str
    moniker: str | None
    operator_address: str
    delegator_address: str | None
    consensus_address: str | None
    network_base_denom: str | None
    network_display_denom: str | None
    exponent: int | None
    rpc_candidates: list[str]
    rest_candidates: list[str]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_float_amount(raw_amount: str | int | float | None, exponent: int | None) -> float | None:
    if raw_amount is None:
        return None
    try:
        raw_int = int(str(raw_amount))
        exp = int(exponent or 0)
        return raw_int / (10 ** exp)
    except Exception:
        return None


def to_decimal(value: str | int | float | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def safe_percent(numerator: Decimal | None, denominator: Decimal | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    try:
        return float((numerator / denominator) * Decimal("100"))
    except Exception:
        return None


def pick_primary_coin(coins: list[dict[str, Any]] | None, preferred_denom: str | None) -> dict[str, Any] | None:
    if not coins:
        return None

    if preferred_denom:
        for coin in coins:
            if str(coin.get("denom")) == preferred_denom:
                return coin

    return coins[0]


def coins_to_display_string(
    coins: list[dict[str, Any]] | None,
    preferred_denom: str | None,
    exponent: int | None,
    display_denom: str | None,
) -> str | None:
    if not coins:
        return None

    parts: list[str] = []
    for coin in coins:
        denom = str(coin.get("denom") or "")
        amount_raw = coin.get("amount")
        amount_display = to_float_amount(amount_raw, exponent if denom == preferred_denom else 0)
        if amount_display is None:
            parts.append(f"{amount_raw} {denom}")
        else:
            label = display_denom if denom == preferred_denom and display_denom else denom
            parts.append(f"{amount_display:.6f} {label}")

    return ", ".join(parts) if parts else None


def normalize_base_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    return url.rstrip("/")


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def http_get_json(session: requests.Session, url: str, timeout: int = HTTP_TIMEOUT) -> tuple[int | None, dict[str, Any]]:
    resp = session.get(
        url,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    status_code = resp.status_code
    resp.raise_for_status()
    return status_code, resp.json()


def http_get_status(session: requests.Session, rpc_url: str) -> tuple[int | None, dict[str, Any]]:
    return http_get_json(session, join_url(rpc_url, "/status"))


def http_get_validator(session: requests.Session, rest_url: str, operator_address: str) -> tuple[int | None, dict[str, Any]]:
    return http_get_json(
        session,
        join_url(rest_url, f"/cosmos/staking/v1beta1/validators/{operator_address}"),
    )


def http_get_pool(session: requests.Session, rest_url: str) -> tuple[int | None, dict[str, Any]]:
    return http_get_json(session, join_url(rest_url, "/cosmos/staking/v1beta1/pool"))


def http_get_annual_provisions(session: requests.Session, rest_url: str) -> tuple[int | None, dict[str, Any]]:
    return http_get_json(session, join_url(rest_url, "/cosmos/mint/v1beta1/annual_provisions"))


def http_get_commission(session: requests.Session, rest_url: str, operator_address: str) -> tuple[int | None, dict[str, Any]]:
    return http_get_json(
        session,
        join_url(rest_url, f"/cosmos/distribution/v1beta1/validators/{operator_address}/commission"),
    )


def http_get_delegation(
    session: requests.Session,
    rest_url: str,
    operator_address: str,
    delegator_address: str | None,
) -> tuple[int | None, dict[str, Any]] | tuple[None, dict[str, Any]]:
    if not delegator_address:
        return None, {}
    return http_get_json(
        session,
        join_url(
            rest_url,
            f"/cosmos/staking/v1beta1/validators/{operator_address}/delegations/{delegator_address}",
        ),
    )


def request_with_fallback(
    candidates: list[str],
    fn,
) -> tuple[str | None, int | None, dict[str, Any] | None, str | None]:
    last_error = None

    with requests.Session() as session:
        for base_url in candidates:
            try:
                status_code, payload = fn(session, base_url)
                return base_url, status_code, payload, None
            except Exception as e:
                last_error = f"{base_url}: {e}"

    return None, None, None, last_error or "no working endpoint"


def determine_status_level(fetch_ok: int, validator_exists: int, jailed: int | None, validator_status: str | None) -> str:
    if not fetch_ok:
        return "critical"
    if not validator_exists:
        return "critical"
    if jailed == 1:
        return "critical"

    status_upper = (validator_status or "").upper()
    if "BONDED" in status_upper:
        return "ok"
    if status_upper:
        return "warning"

    return "warning"


def build_task_rows(db: Session) -> list[ValidatorTask]:
    validators = db.execute(
        select(Validator, Network)
        .join(Network, Network.chain_id == Validator.chain_id)
        .where(Validator.is_enabled == 1)
        .order_by(Validator.chain_id.asc(), Validator.operator_address.asc())
    ).all()

    tasks: list[ValidatorTask] = []

    for validator, network in validators:
        endpoints = db.execute(
            select(NetworkEndpoint)
            .where(
                NetworkEndpoint.chain_id == validator.chain_id,
                NetworkEndpoint.is_enabled == 1,
                NetworkEndpoint.is_public == 1,
                NetworkEndpoint.endpoint_type.in_(["rpc", "rest"]),
            )
            .order_by(
                NetworkEndpoint.selected_for_dashboard.desc(),
                NetworkEndpoint.last_check_ok.desc(),
                NetworkEndpoint.latency_ms.asc().nulls_last(),
                NetworkEndpoint.priority.asc(),
                NetworkEndpoint.id.asc(),
            )
        ).scalars().all()

        rpc_candidates: list[str] = []
        rest_candidates: list[str] = []

        for ep in endpoints:
            if ep.endpoint_type == "rpc" and ep.url and len(rpc_candidates) < MAX_ENDPOINTS_PER_TYPE:
                rpc_candidates.append(normalize_base_url(ep.url))
            elif ep.endpoint_type == "rest" and ep.url and len(rest_candidates) < MAX_ENDPOINTS_PER_TYPE:
                rest_candidates.append(normalize_base_url(ep.url))

        fallback_rpc = [
            normalize_base_url(network.rpc),
            normalize_base_url(network.rpc1),
            normalize_base_url(network.rpc2),
        ]
        fallback_rest = [
            normalize_base_url(network.rest),
            normalize_base_url(network.rest1),
            normalize_base_url(network.rest2),
        ]

        for url in fallback_rpc:
            if url and url not in rpc_candidates and len(rpc_candidates) < MAX_ENDPOINTS_PER_TYPE:
                rpc_candidates.append(url)

        for url in fallback_rest:
            if url and url not in rest_candidates and len(rest_candidates) < MAX_ENDPOINTS_PER_TYPE:
                rest_candidates.append(url)

        tasks.append(
            ValidatorTask(
                validator_id=validator.id,
                chain_id=validator.chain_id,
                moniker=validator.moniker,
                operator_address=validator.operator_address,
                delegator_address=validator.delegator_address,
                consensus_address=validator.consensus_address,
                network_base_denom=network.base_denom,
                network_display_denom=network.display_denom,
                exponent=network.exponent,
                rpc_candidates=[x for x in rpc_candidates if x],
                rest_candidates=[x for x in rest_candidates if x],
            )
        )

    return tasks


def collect_one(task: ValidatorTask) -> dict[str, Any]:
    started = time.perf_counter()

    result: dict[str, Any] = {
        "validator_id": task.validator_id,
        "chain_id": task.chain_id,
        "operator_address": task.operator_address,
        "delegator_address": task.delegator_address,
        "consensus_address": task.consensus_address,
        "moniker_snapshot": task.moniker,
        "fetch_ok": 0,
        "fetch_error": None,
        "fetch_duration_ms": None,
        "http_status": None,
        "rest_url_used": None,
        "rpc_url_used": None,
        "validator_exists": 0,
        "validator_status": None,
        "jailed": None,
        "status_level": "critical",
        "validator_tokens_raw": None,
        "validator_tokens_display": None,
        "network_bonded_tokens_raw": None,
        "network_bonded_tokens_display": None,
        "voting_power_percent": None,
        "annual_provisions_raw": None,
        "apr_percent": None,
        "commission_rate_percent": None,
        "commission_max_rate_percent": None,
        "commission_max_change_rate_percent": None,
        "self_bonded_raw": None,
        "self_bonded_display": None,
        "self_bonded_percent": None,
        "reward_commission_primary_denom": None,
        "reward_commission_primary_raw": None,
        "reward_commission_primary_display": None,
        "reward_commission_display": None,
        "reward_commission_raw_json": None,
        "raw_json": None,
        "last_success_at": None,
    }

    raw: dict[str, Any] = {
        "rpc_status": None,
        "validator": None,
        "pool": None,
        "annual_provisions": None,
        "commission": None,
        "delegation": None,
    }

    try:
        if not task.rpc_candidates:
            raise RuntimeError("no public rpc candidates")

        if not task.rest_candidates:
            raise RuntimeError("no public rest candidates")

        rpc_url, rpc_http_status, rpc_payload, rpc_error = request_with_fallback(
            task.rpc_candidates,
            http_get_status,
        )
        if not rpc_payload:
            raise RuntimeError(f"rpc failed: {rpc_error}")

        result["rpc_url_used"] = rpc_url
        result["http_status"] = rpc_http_status
        raw["rpc_status"] = rpc_payload

        rest_url, rest_http_status, validator_payload, rest_error = request_with_fallback(
            task.rest_candidates,
            lambda session, base_url: http_get_validator(session, base_url, task.operator_address),
        )
        if not validator_payload:
            raise RuntimeError(f"validator query failed: {rest_error}")

        result["rest_url_used"] = rest_url
        result["http_status"] = rest_http_status or result["http_status"]
        raw["validator"] = validator_payload

        validator_data = validator_payload.get("validator") or {}
        result["validator_exists"] = 1
        result["validator_status"] = validator_data.get("status")
        result["jailed"] = 1 if bool(validator_data.get("jailed")) else 0
        result["moniker_snapshot"] = (
            ((validator_data.get("description") or {}).get("moniker"))
            or result["moniker_snapshot"]
        )
        result["validator_tokens_raw"] = validator_data.get("tokens")
        result["validator_tokens_display"] = to_float_amount(
            validator_data.get("tokens"),
            task.exponent,
        )

        commission = validator_data.get("commission") or {}
        rates = commission.get("commission_rates") or {}
        try:
            result["commission_rate_percent"] = float(rates["rate"]) * 100 if rates.get("rate") is not None else None
        except Exception:
            pass
        try:
            result["commission_max_rate_percent"] = float(rates["max_rate"]) * 100 if rates.get("max_rate") is not None else None
        except Exception:
            pass
        try:
            result["commission_max_change_rate_percent"] = float(rates["max_change_rate"]) * 100 if rates.get("max_change_rate") is not None else None
        except Exception:
            pass

        # pool
        _, _, pool_payload, _ = request_with_fallback(
            [rest_url],
            http_get_pool,
        )
        raw["pool"] = pool_payload
        bonded_tokens = ((pool_payload or {}).get("pool") or {}).get("bonded_tokens")
        result["network_bonded_tokens_raw"] = bonded_tokens
        result["network_bonded_tokens_display"] = to_float_amount(bonded_tokens, task.exponent)

        _, _, annual_payload, _ = request_with_fallback(
            [rest_url],
            http_get_annual_provisions,
        )
        raw["annual_provisions"] = annual_payload
        annual_provisions_raw = (annual_payload or {}).get("annual_provisions")
        result["annual_provisions_raw"] = annual_provisions_raw
        result["apr_percent"] = safe_percent(
            to_decimal(annual_provisions_raw),
            to_decimal(bonded_tokens),
        )

        if result["validator_tokens_display"] is not None and result["network_bonded_tokens_display"] not in (None, 0):
            result["voting_power_percent"] = (
                float(result["validator_tokens_display"]) / float(result["network_bonded_tokens_display"])
            ) * 100.0

        # commission rewards
        _, _, commission_payload, _ = request_with_fallback(
            [rest_url],
            lambda session, base_url: http_get_commission(session, base_url, task.operator_address),
        )
        raw["commission"] = commission_payload
        comm_coins = ((commission_payload or {}).get("commission") or {}).get("commission") or []
        primary_comm = pick_primary_coin(comm_coins, task.network_base_denom)
        if primary_comm:
            result["reward_commission_primary_denom"] = primary_comm.get("denom")
            result["reward_commission_primary_raw"] = primary_comm.get("amount")
            result["reward_commission_primary_display"] = to_float_amount(
                primary_comm.get("amount"),
                task.exponent if primary_comm.get("denom") == task.network_base_denom else 0,
            )
        result["reward_commission_display"] = coins_to_display_string(
            comm_coins,
            task.network_base_denom,
            task.exponent,
            task.network_display_denom,
        )
        result["reward_commission_raw_json"] = json.dumps(comm_coins, ensure_ascii=False)

        # self delegation
        if task.delegator_address:
            _, _, delegation_payload, _ = request_with_fallback(
                [rest_url],
                lambda session, base_url: http_get_delegation(
                    session,
                    base_url,
                    task.operator_address,
                    task.delegator_address,
                ),
            )
            raw["delegation"] = delegation_payload
            balance = ((delegation_payload or {}).get("balance")) or {}
            if balance:
                result["self_bonded_raw"] = balance.get("amount")
                result["self_bonded_display"] = to_float_amount(balance.get("amount"), task.exponent)
                if result["validator_tokens_display"] not in (None, 0) and result["self_bonded_display"] is not None:
                    result["self_bonded_percent"] = (
                        float(result["self_bonded_display"]) / float(result["validator_tokens_display"])
                    ) * 100.0

        result["fetch_ok"] = 1
        result["status_level"] = determine_status_level(
            fetch_ok=1,
            validator_exists=result["validator_exists"],
            jailed=result["jailed"],
            validator_status=result["validator_status"],
        )
        result["last_success_at"] = utc_now()

    except Exception as e:
        result["fetch_ok"] = 0
        result["fetch_error"] = str(e)
        result["status_level"] = "critical"

    result["fetch_duration_ms"] = int((time.perf_counter() - started) * 1000)
    result["raw_json"] = json.dumps(raw, ensure_ascii=False)

    return result


def save_result(db: Session, payload: dict[str, Any]) -> None:
    validator_id = payload["validator_id"]

    current = db.get(ValidatorStatusCurrent, validator_id)
    if current is None:
        current = ValidatorStatusCurrent(validator_id=validator_id)
        db.add(current)

    for key, value in payload.items():
        if key == "validator_id":
            continue
        if hasattr(current, key):
            setattr(current, key, value)

    history = ValidatorStatusHistory(
        validator_id=validator_id,
        chain_id=payload.get("chain_id"),
        operator_address=payload.get("operator_address"),
        delegator_address=payload.get("delegator_address"),
        consensus_address=payload.get("consensus_address"),
        moniker_snapshot=payload.get("moniker_snapshot"),
        fetch_ok=payload.get("fetch_ok", 0),
        fetch_error=payload.get("fetch_error"),
        fetch_duration_ms=payload.get("fetch_duration_ms"),
        http_status=payload.get("http_status"),
        rest_url_used=payload.get("rest_url_used"),
        rpc_url_used=payload.get("rpc_url_used"),
        validator_exists=payload.get("validator_exists", 0),
        validator_status=payload.get("validator_status"),
        jailed=payload.get("jailed"),
        status_level=payload.get("status_level", "critical"),
        validator_tokens_raw=payload.get("validator_tokens_raw"),
        validator_tokens_display=payload.get("validator_tokens_display"),
        network_bonded_tokens_raw=payload.get("network_bonded_tokens_raw"),
        network_bonded_tokens_display=payload.get("network_bonded_tokens_display"),
        voting_power_percent=payload.get("voting_power_percent"),
        annual_provisions_raw=payload.get("annual_provisions_raw"),
        apr_percent=payload.get("apr_percent"),
        commission_rate_percent=payload.get("commission_rate_percent"),
        commission_max_rate_percent=payload.get("commission_max_rate_percent"),
        commission_max_change_rate_percent=payload.get("commission_max_change_rate_percent"),
        self_bonded_raw=payload.get("self_bonded_raw"),
        self_bonded_display=payload.get("self_bonded_display"),
        self_bonded_percent=payload.get("self_bonded_percent"),
        reward_commission_primary_denom=payload.get("reward_commission_primary_denom"),
        reward_commission_primary_raw=payload.get("reward_commission_primary_raw"),
        reward_commission_primary_display=payload.get("reward_commission_primary_display"),
        reward_commission_display=payload.get("reward_commission_display"),
        reward_commission_raw_json=payload.get("reward_commission_raw_json"),
        raw_json=payload.get("raw_json"),
    )
    db.add(history)


def main() -> None:
    db = SessionLocal()
    try:
        tasks = build_task_rows(db)
    finally:
        db.close()

    total = len(tasks)
    ok = 0
    fail = 0

    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(collect_one, task): task for task in tasks}

        for future in as_completed(future_map):
            task = future_map[future]
            try:
                payload = future.result()
                results.append(payload)
                if payload.get("fetch_ok") == 1:
                    ok += 1
                    print(
                        f"[OK] {task.chain_id} | {task.operator_address} | "
                        f"rpc={payload.get('rpc_url_used')} | rest={payload.get('rest_url_used')}"
                    )
                else:
                    fail += 1
                    print(
                        f"[ERR] {task.chain_id} | {task.operator_address} | "
                        f"{payload.get('fetch_error')}"
                    )
            except Exception as e:
                fail += 1
                print(f"[ERR] {task.chain_id} | {task.operator_address} | future crash: {e}")

    db = SessionLocal()
    try:
        for payload in results:
            save_result(db, payload)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"\nDone. total={total} ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
