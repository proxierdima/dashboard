#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.models_chainid import Network, NetworkEndpoint


CHAIN_REGISTRY_DIR = Path("chain-registry")

HTTP_TIMEOUT = 3
GRPC_TIMEOUT = 2

MAX_PER_TYPE = 3
MAX_WORKERS = 64
PROGRESS_EVERY = 25

RPC_MAX_LATENCY_MS = 1800
REST_MAX_LATENCY_MS = 1800
GRPC_MAX_LATENCY_MS = 1500


# ------------------------
# Utils
# ------------------------

def utcnow():
    return datetime.now(timezone.utc)


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.strip().rstrip("/")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_name(value: str | None) -> str:
    return (value or "").strip().lower()


def latency_limit(endpoint_type: str) -> int:
    if endpoint_type == "rpc":
        return RPC_MAX_LATENCY_MS
    if endpoint_type == "rest":
        return REST_MAX_LATENCY_MS
    if endpoint_type == "grpc":
        return GRPC_MAX_LATENCY_MS
    return 0


def latency_ok(endpoint_type: str, latency_ms: int) -> bool:
    limit = latency_limit(endpoint_type)
    return latency_ms > 0 and limit > 0 and latency_ms <= limit


def find_chain_json_for_network(network: Network) -> Path | None:
    direct_candidates: list[Path] = []

    if getattr(network, "directory", None):
        direct_candidates.append(CHAIN_REGISTRY_DIR / str(network.directory) / "chain.json")

    if getattr(network, "name", None):
        direct_candidates.append(CHAIN_REGISTRY_DIR / str(network.name) / "chain.json")

    if getattr(network, "chain_id", None):
        direct_candidates.append(CHAIN_REGISTRY_DIR / str(network.chain_id) / "chain.json")

    for candidate in direct_candidates:
        if candidate.exists():
            return candidate

    target_chain_id = (getattr(network, "chain_id", None) or "").strip()
    target_dir = normalize_name(getattr(network, "directory", None))
    target_name = normalize_name(getattr(network, "name", None))

    for chain_json in CHAIN_REGISTRY_DIR.rglob("chain.json"):
        if any(part.startswith(".") for part in chain_json.parts):
            continue

        data = load_json(chain_json)
        if not data:
            continue

        if target_chain_id and data.get("chain_id") == target_chain_id:
            return chain_json

        parent_name = normalize_name(chain_json.parent.name)
        if target_dir and parent_name == target_dir:
            return chain_json
        if target_name and parent_name == target_name:
            return chain_json

    return None


def extract_apis(chain_json: dict, key: str) -> list[str]:
    items = chain_json.get("apis", {}).get(key, [])
    result: list[str] = []

    for item in items:
        url = normalize_url(item.get("address"))
        if not url:
            continue

        low = url.lower()
        if "127.0.0.1" in low or "0.0.0.0" in low or "localhost" in low:
            continue

        result.append(url)

    seen = set()
    out = []
    for x in result:
        if x not in seen:
            seen.add(x)
            out.append(x)

    return out


def merge_candidate_urls(existing_urls: list[str], discovered_urls: list[str]) -> list[str]:
    """
    Сначала проверяем уже известные URL из network_endpoints,
    потом дополняем новыми из chain-registry.
    """
    merged = []
    seen = set()

    for url in existing_urls + discovered_urls:
        url = normalize_url(url)
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(url)

    return merged


# ------------------------
# requests.Session per thread
# ------------------------

_thread_local = threading.local()


def get_session():
    sess = getattr(_thread_local, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "validator-dashboard-public-rpc/6.0"})
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=0,
        )
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        _thread_local.session = sess
    return sess


# ------------------------
# Checks
# ------------------------

def check_rpc(url: str):
    start = time.time()
    try:
        session = get_session()
        r = session.get(f"{url}/status", timeout=HTTP_TIMEOUT)
        latency = int((time.time() - start) * 1000)

        if r.status_code != 200:
            return False, r.status_code, latency, None, None, f"http {r.status_code}"

        data = r.json()
        height = data.get("result", {}).get("sync_info", {}).get("latest_block_height")
        chain_id_reported = data.get("result", {}).get("node_info", {}).get("network")

        try:
            height = int(height) if height is not None else None
        except Exception:
            height = None

        return True, 200, latency, height, chain_id_reported, None
    except Exception as e:
        return False, 0, 0, None, None, str(e)[:500]


def check_rest(url: str):
    start = time.time()
    try:
        session = get_session()
        r = session.get(
            f"{url}/cosmos/base/tendermint/v1beta1/syncing",
            timeout=HTTP_TIMEOUT,
        )
        latency = int((time.time() - start) * 1000)

        if r.status_code != 200:
            return False, r.status_code, latency, None, None, f"http {r.status_code}"

        return True, r.status_code, latency, None, None, None
    except Exception as e:
        return False, 0, 0, None, None, str(e)[:500]


def check_grpc(url: str):
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 443

        if not host:
            return False, 0, 0, None, None, "invalid grpc url"

        start = time.time()
        with socket.create_connection((host, port), timeout=GRPC_TIMEOUT):
            latency = int((time.time() - start) * 1000)
            return True, 0, latency, None, None, None
    except Exception as e:
        return False, 0, 0, None, None, str(e)[:500]


def run_check(endpoint_type: str, url: str):
    if endpoint_type == "rpc":
        return check_rpc(url)
    if endpoint_type == "rest":
        return check_rest(url)
    if endpoint_type == "grpc":
        return check_grpc(url)
    return False, 0, 0, None, None, "unknown endpoint_type"


# ------------------------
# Scan chain/type
# ------------------------

def scan_first_working(chain_id: str, endpoint_type: str, urls: list[str]):
    """
    Проверяем URL по порядку и выбираем первые MAX_PER_TYPE живых.
    Нерабочие уже известные endpoint'ы потом будут помечены в network_endpoints.
    """
    selected = []
    checked = []

    for url in urls:
        ok, http_status, latency, remote_height, chain_id_reported, error_message = run_check(endpoint_type, url)

        if ok and latency_ok(endpoint_type, latency):
            row_status = "ok"
        elif ok:
            row_status = "warning"
            error_message = f"latency {latency}ms exceeds limit {latency_limit(endpoint_type)}ms"
        else:
            row_status = "dead"

        row = {
            "chain_id": chain_id,
            "endpoint_type": endpoint_type,
            "url": url,
            "http_status": http_status,
            "latency_ms": latency,
            "remote_height": remote_height if isinstance(remote_height, int) else None,
            "chain_id_reported": chain_id_reported,
            "error_message": error_message,
            "status": row_status,
        }
        checked.append(row)

        if row_status == "ok":
            selected.append(row)
            if len(selected) >= MAX_PER_TYPE:
                break

    return {
        "chain_id": chain_id,
        "endpoint_type": endpoint_type,
        "selected": selected,
        "checked": checked,
    }


# ------------------------
# DB helpers
# ------------------------

def preload_networks(db):
    return db.execute(
        select(Network)
        .where(Network.is_enabled == 1)
        .order_by(Network.name.asc())
    ).scalars().all()


def preload_existing_public_endpoints(db):
    rows = db.execute(
        select(NetworkEndpoint)
        .where(NetworkEndpoint.is_public == 1)
        .order_by(
            NetworkEndpoint.chain_id.asc(),
            NetworkEndpoint.endpoint_type.asc(),
            NetworkEndpoint.priority.asc(),
            NetworkEndpoint.id.asc(),
        )
    ).scalars().all()

    cache: dict[tuple[str, str, str], NetworkEndpoint] = {}
    by_chain_type: dict[tuple[str, str], list[str]] = {}

    for ep in rows:
        url = normalize_url(ep.url)
        if not url:
            continue

        cache[(ep.chain_id, ep.endpoint_type, url)] = ep
        by_chain_type.setdefault((ep.chain_id, ep.endpoint_type), []).append(url)

    return cache, by_chain_type


def get_or_create_public_endpoint(
    db,
    cache: dict,
    chain_id: str,
    endpoint_type: str,
    url: str,
    priority: int | None = None,
):
    key = (chain_id, endpoint_type, url)
    ep = cache.get(key)
    now = utcnow()

    if ep is not None:
        changed = False

        if priority is not None and ep.priority != priority:
            ep.priority = priority
            changed = True

        if ep.is_public != 1:
            ep.is_public = 1
            changed = True

        if ep.label != "public":
            ep.label = "public"
            changed = True

        if not getattr(ep, "source", None):
            ep.source = "chain-registry"
            changed = True

        if ep.first_seen_at is None:
            ep.first_seen_at = now
            changed = True

        if changed:
            ep.updated_at = now

        return ep

    ep = NetworkEndpoint(
        chain_id=chain_id,
        endpoint_type=endpoint_type,
        label="public",
        url=url,
        priority=priority or 999,
        source="chain-registry",
        is_public=1,
        is_enabled=1,
        first_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(ep)
    db.flush()

    cache[key] = ep
    return ep


def reset_selected_flags_for_type(db, chain_id: str, endpoint_type: str):
    rows = db.execute(
        select(NetworkEndpoint)
        .where(NetworkEndpoint.chain_id == chain_id)
        .where(NetworkEndpoint.endpoint_type == endpoint_type)
        .where(NetworkEndpoint.is_public == 1)
    ).scalars().all()

    now = utcnow()
    for ep in rows:
        ep.selected_for_dashboard = 0
        ep.updated_at = now


def mark_existing_endpoint_result(
    cache: dict,
    chain_id: str,
    endpoint_type: str,
    url: str,
    http_status: int,
    latency_ms: int,
    remote_height: int | None,
    chain_id_reported: str | None,
    error_message: str | None,
    status: str,
):
    ep = cache.get((chain_id, endpoint_type, url))
    if ep is None:
        return

    now = utcnow()

    ep.status = status
    ep.http_status = http_status
    ep.latency_ms = latency_ms
    ep.remote_height = remote_height
    ep.chain_id_reported = chain_id_reported
    ep.check_error = error_message
    ep.last_checked_at = now
    ep.updated_at = now

    if status == "ok":
        ep.selected_for_dashboard = 1
        ep.last_check_ok = 1
        ep.last_ok_at = now
        ep.consecutive_ok_count = int(ep.consecutive_ok_count or 0) + 1
        ep.consecutive_fail_count = 0
        ep.is_enabled = 1
    else:
        ep.selected_for_dashboard = 0
        ep.last_check_ok = 0
        ep.last_fail_at = now
        ep.consecutive_fail_count = int(ep.consecutive_fail_count or 0) + 1
        ep.consecutive_ok_count = 0
        ep.is_enabled = 0


def update_network_fields(network: Network, prefix: str, urls: list[str]):
    vals = list(urls[:MAX_PER_TYPE])
    while len(vals) < MAX_PER_TYPE:
        vals.append(None)

    setattr(network, prefix, vals[0])
    setattr(network, f"{prefix}1", vals[1])
    setattr(network, f"{prefix}2", vals[2])


def build_tasks(db):
    tasks = []
    networks = preload_networks(db)
    _, existing_by_chain_type = preload_existing_public_endpoints(db)

    for network in networks:
        path = find_chain_json_for_network(network)
        if not path:
            print(f"[MISS] chain.json not found for network={network.name} chain_id={network.chain_id}")
            continue

        data = load_json(path)
        if not data:
            print(f"[MISS] invalid chain.json for network={network.name} chain_id={network.chain_id}")
            continue

        rpc_list = extract_apis(data, "rpc")
        rest_list = extract_apis(data, "rest")
        grpc_list = extract_apis(data, "grpc")

        for endpoint_type, discovered in (
            ("rpc", rpc_list),
            ("rest", rest_list),
            ("grpc", grpc_list),
        ):
            existing = existing_by_chain_type.get((network.chain_id, endpoint_type), [])
            merged_urls = merge_candidate_urls(existing, discovered)
            tasks.append((network.chain_id, endpoint_type, merged_urls))

    return tasks


# ------------------------
# MAIN
# ------------------------

def main():
    started = time.time()
    db = SessionLocal()

    try:
        print("Collecting tasks from current project networks...")
        scan_tasks = build_tasks(db)
        print(f"Total scan tasks: {len(scan_tasks)}")

        if not scan_tasks:
            print("No tasks found.")
            return

        workers = min(MAX_WORKERS, max(1, len(scan_tasks)))
        print(f"Using workers: {workers}")

        scan_results = []
        done_count = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(scan_first_working, chain_id, endpoint_type, urls): (chain_id, endpoint_type)
                for chain_id, endpoint_type, urls in scan_tasks
            }

            for future in as_completed(future_map):
                chain_id, endpoint_type = future_map[future]
                try:
                    result = future.result()
                except Exception as e:
                    print(f"[ERR] {chain_id} {endpoint_type}: {e}")
                    result = {
                        "chain_id": chain_id,
                        "endpoint_type": endpoint_type,
                        "selected": [],
                        "checked": [],
                    }

                scan_results.append(result)
                done_count += 1

                if done_count % PROGRESS_EVERY == 0:
                    print(f"Scanned {done_count}/{len(scan_tasks)}")

        print(f"Scan phase finished in {time.time() - started:.1f}s")
        print("Saving results to network_endpoints...")

        network_map = {n.chain_id: n for n in preload_networks(db)}
        endpoint_cache, _ = preload_existing_public_endpoints(db)

        selected_urls_by_chain_type: dict[tuple[str, str], list[str]] = {}

        for item in scan_results:
            chain_id = item["chain_id"]
            endpoint_type = item["endpoint_type"]
            selected = item.get("selected", [])
            checked = item.get("checked", [])

            reset_selected_flags_for_type(db, chain_id, endpoint_type)

            # 1) Сначала обновляем уже известные endpoint'ы по результатам проверки
            for row in checked:
                mark_existing_endpoint_result(
                    cache=endpoint_cache,
                    chain_id=chain_id,
                    endpoint_type=endpoint_type,
                    url=row["url"],
                    http_status=row["http_status"],
                    latency_ms=row["latency_ms"],
                    remote_height=row["remote_height"],
                    chain_id_reported=row["chain_id_reported"],
                    error_message=row["error_message"],
                    status=row["status"],
                )

            # 2) Затем создаём/обновляем рабочие endpoint'ы и выбираем top-N
            selected_urls = []
            for idx, row in enumerate(selected, start=1):
                ep = get_or_create_public_endpoint(
                    db=db,
                    cache=endpoint_cache,
                    chain_id=chain_id,
                    endpoint_type=endpoint_type,
                    url=row["url"],
                    priority=idx,
                )

                checked_at = utcnow()
                ep.status = "ok"
                ep.http_status = row["http_status"]
                ep.latency_ms = row["latency_ms"]
                ep.remote_height = row["remote_height"]
                ep.chain_id_reported = row["chain_id_reported"]
                ep.check_error = None
                ep.selected_for_dashboard = 1
                ep.last_check_ok = 1
                ep.last_checked_at = checked_at
                ep.last_ok_at = checked_at
                ep.consecutive_ok_count = int(ep.consecutive_ok_count or 0) + 1
                ep.consecutive_fail_count = 0
                ep.updated_at = checked_at
                ep.is_enabled = 1

                selected_urls.append(row["url"])

            selected_urls_by_chain_type[(chain_id, endpoint_type)] = selected_urls

            # 3) Всё, что публичное, но не попало в текущий top-N и не проверялось,
            #    просто убираем из selected_for_dashboard
            rows = db.execute(
                select(NetworkEndpoint)
                .where(NetworkEndpoint.chain_id == chain_id)
                .where(NetworkEndpoint.endpoint_type == endpoint_type)
                .where(NetworkEndpoint.is_public == 1)
            ).scalars().all()

            checked_urls = {row["url"] for row in checked}
            keep_urls = set(selected_urls)
            now = utcnow()

            for ep in rows:
                ep_url = normalize_url(ep.url)
                if not ep_url:
                    continue
                if ep_url in keep_urls:
                    continue
                if ep_url in checked_urls:
                    continue
                ep.selected_for_dashboard = 0
                ep.updated_at = now

        touched_chain_ids = {chain_id for chain_id, _ in selected_urls_by_chain_type.keys()}

        for chain_id in touched_chain_ids:
            network = network_map.get(chain_id)
            if not network:
                continue

            rpc_urls = selected_urls_by_chain_type.get((chain_id, "rpc"), [])
            rest_urls = selected_urls_by_chain_type.get((chain_id, "rest"), [])
            grpc_urls = selected_urls_by_chain_type.get((chain_id, "grpc"), [])

            update_network_fields(network, "rpc", rpc_urls)
            update_network_fields(network, "rest", rest_urls)
            update_network_fields(network, "grpc", grpc_urls)

            print(f"[OK] {chain_id}")
            print(f"  RPC : {rpc_urls}")
            print(f"  REST: {rest_urls}")
            print(f"  GRPC: {grpc_urls}")

        db.commit()

        print(f"Updated networks: {len(touched_chain_ids)}")
        print(f"Total time: {time.time() - started:.1f}s")

    finally:
        db.close()


if __name__ == "__main__":
    main()
