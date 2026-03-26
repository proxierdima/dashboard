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
from app.models_chainid import EndpointCheck, Network, NetworkEndpoint


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


def find_chain_json_for_network(network: Network) -> Path | None:
    """
    Ищем chain.json максимально надежно:
    1) chain-registry/<directory>/chain.json
    2) chain-registry/<name>/chain.json
    3) chain-registry/<chain_id>/chain.json
    4) fallback по всем chain.json и совпадению chain_id
    """
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


def latency_ok(endpoint_type: str, latency_ms: int) -> bool:
    if latency_ms <= 0:
        return False

    if endpoint_type == "rpc":
        return latency_ms <= RPC_MAX_LATENCY_MS
    if endpoint_type == "rest":
        return latency_ms <= REST_MAX_LATENCY_MS
    if endpoint_type == "grpc":
        return latency_ms <= GRPC_MAX_LATENCY_MS

    return False


# ------------------------
# requests.Session per thread
# ------------------------

_thread_local = threading.local()


def get_session():
    sess = getattr(_thread_local, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "validator-dashboard-public-rpc/4.0"})
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
            return False, r.status_code, latency, None, None

        data = r.json()
        height = data.get("result", {}).get("sync_info", {}).get("latest_block_height")

        try:
            height = int(height) if height is not None else None
        except Exception:
            height = None

        chain_id_reported = data.get("result", {}).get("node_info", {}).get("network")

        return True, 200, latency, height, chain_id_reported
    except Exception:
        return False, 0, 0, None, None


def check_rest(url: str):
    start = time.time()
    try:
        session = get_session()
        r = session.get(
            f"{url}/cosmos/base/tendermint/v1beta1/syncing",
            timeout=HTTP_TIMEOUT,
        )
        latency = int((time.time() - start) * 1000)

        ok = r.status_code == 200
        return ok, r.status_code, latency, None, None
    except Exception:
        return False, 0, 0, None, None


def check_grpc(url: str):
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 443

        if not host:
            return False, 0, 0, None, None

        start = time.time()
        with socket.create_connection((host, port), timeout=GRPC_TIMEOUT):
            latency = int((time.time() - start) * 1000)
            return True, 0, latency, None, None
    except Exception:
        return False, 0, 0, None, None


# ------------------------
# Scan first 3 working
# ------------------------

def scan_first_working(chain_id: str, endpoint_type: str, urls: list[str]):
    """
    Идем по списку по порядку и останавливаемся,
    когда нашли первые MAX_PER_TYPE живых endpoint'ов.
    """
    selected = []

    for url in urls:
        if endpoint_type == "rpc":
            ok, http_status, latency, remote_height, chain_id_reported = check_rpc(url)
        elif endpoint_type == "rest":
            ok, http_status, latency, remote_height, chain_id_reported = check_rest(url)
        elif endpoint_type == "grpc":
            ok, http_status, latency, remote_height, chain_id_reported = check_grpc(url)
        else:
            ok, http_status, latency, remote_height, chain_id_reported = False, 0, 0, None, None

        if ok and latency_ok(endpoint_type, latency):
            selected.append(
                {
                    "chain_id": chain_id,
                    "endpoint_type": endpoint_type,
                    "url": url,
                    "latency_ms": latency,
                    "http_status": http_status,
                    "remote_height": remote_height if isinstance(remote_height, int) else None,
                    "chain_id_reported": chain_id_reported,
                }
            )

            if len(selected) >= MAX_PER_TYPE:
                break

    return {
        "chain_id": chain_id,
        "endpoint_type": endpoint_type,
        "selected": selected,
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
    ).scalars().all()

    cache = {}
    for ep in rows:
        cache[(ep.chain_id, ep.endpoint_type, ep.url)] = ep
    return cache


def get_or_create_public_endpoint(
    db,
    cache: dict,
    chain_id: str,
    endpoint_type: str,
    url: str,
    priority: int,
):
    key = (chain_id, endpoint_type, url)
    ep = cache.get(key)
    now = utcnow()

    if ep is not None:
        changed = False

        if ep.priority != priority:
            ep.priority = priority
            changed = True

        if ep.is_public != 1:
            ep.is_public = 1
            changed = True

        if ep.is_enabled != 1:
            ep.is_enabled = 1
            changed = True

        if ep.label != "public":
            ep.label = "public"
            changed = True

        if ep.source != "chain-registry":
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
        priority=priority,
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


def disable_old_public_endpoints_for_type(
    db,
    chain_id: str,
    endpoint_type: str,
    keep_urls: set[str],
):
    rows = db.execute(
        select(NetworkEndpoint)
        .where(NetworkEndpoint.chain_id == chain_id)
        .where(NetworkEndpoint.endpoint_type == endpoint_type)
        .where(NetworkEndpoint.is_public == 1)
    ).scalars().all()

    now = utcnow()

    for ep in rows:
        if ep.url not in keep_urls:
            ep.is_enabled = 0
            ep.selected_for_dashboard = 0
            ep.last_check_ok = 0
            ep.status = "dead"
            ep.check_error = "not selected by public_rpc_collector"
            ep.last_checked_at = now
            ep.last_fail_at = now
            ep.consecutive_fail_count = int(ep.consecutive_fail_count or 0) + 1
            ep.consecutive_ok_count = 0
            ep.updated_at = now


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

        tasks.append((network.chain_id, "rpc", rpc_list))
        tasks.append((network.chain_id, "rest", rest_list))
        tasks.append((network.chain_id, "grpc", grpc_list))

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
                    }

                scan_results.append(result)
                done_count += 1

                if done_count % PROGRESS_EVERY == 0:
                    print(f"Scanned {done_count}/{len(scan_tasks)}")

        print(f"Scan phase finished in {time.time() - started:.1f}s")
        print("Saving selected endpoints to DB...")

        network_map = {n.chain_id: n for n in preload_networks(db)}
        endpoint_cache = preload_existing_public_endpoints(db)

        check_rows = []
        selected_urls_by_chain_type = {}

        for item in scan_results:
            chain_id = item["chain_id"]
            endpoint_type = item["endpoint_type"]
            selected = item.get("selected", [])

            urls = [x["url"] for x in selected]
            selected_urls_by_chain_type[(chain_id, endpoint_type)] = urls

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

                check_rows.append(
                    {
                        "endpoint_id": ep.id,
                        "status": "OK",
                        "http_status": row["http_status"],
                        "latency_ms": row["latency_ms"],
                        "remote_height": row["remote_height"],
                        "chain_id_reported": row["chain_id_reported"],
                        "error_message": None,
                        "checked_at": checked_at,
                    }
                )

            disable_old_public_endpoints_for_type(
                db=db,
                chain_id=chain_id,
                endpoint_type=endpoint_type,
                keep_urls=set(urls),
            )

        if check_rows:
            db.bulk_insert_mappings(EndpointCheck, check_rows)

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

        print(f"Saved checks: {len(check_rows)}")
        print(f"Updated networks: {len(touched_chain_ids)}")
        print(f"Total time: {time.time() - started:.1f}s")

    finally:
        db.close()


if __name__ == "__main__":
    main()
