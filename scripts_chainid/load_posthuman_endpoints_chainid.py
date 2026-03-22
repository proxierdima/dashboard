#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.models_chainid import Network, Validator

POSTHUMAN_FILE = Path("config/posthuman_endpoints.txt")
CHAIN_REGISTRY_DIR = Path("chain-registry")

CHAIN_RE = re.compile(r"^\s*chain_id:\s*(.+?)\s*$")
VALOPER_RE = re.compile(r"^\s*valoper_address:\s*(.+?)\s*$")
URL_RE = re.compile(r"^\s*-\s*url:\s*(.+?)\s*$")
URL_METRIC_RE = re.compile(r"^\s*-\s*url_metric:\s*(.+?)\s*$")

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
HTTP_TIMEOUT = 6


def clean_value(s: str) -> str:
    return s.strip().strip('"').strip("'")


def normalize_chain_id(chain_id: str | None) -> str | None:
    if not chain_id:
        return None
    return " ".join(chain_id.strip().split())


def normalize_valoper(valoper: str | None) -> str | None:
    if not valoper:
        return None
    v = valoper.strip()
    if not v:
        return None
    v = v.replace("@valoper", "valoper")
    v = " ".join(v.split())
    return v or None


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if not value:
        return None
    return value.rstrip("/")


def parse_posthuman_source(text: str) -> list[dict]:
    items = []
    current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            continue

        m = CHAIN_RE.match(line)
        if m:
            if current:
                items.append(current)
            current = {
                "chain_id": normalize_chain_id(clean_value(m.group(1))),
                "valoper_address": None,
                "urls": [],
                "metrics_url": None,
            }
            continue

        m = VALOPER_RE.match(line)
        if m and current:
            current["valoper_address"] = normalize_valoper(clean_value(m.group(1)))
            continue

        m = URL_RE.match(line)
        if m and current:
            value = normalize_url(clean_value(m.group(1)))
            if value:
                current["urls"].append(value)
            continue

        m = URL_METRIC_RE.match(line)
        if m and current:
            current["metrics_url"] = normalize_url(clean_value(m.group(1)))
            continue

    if current:
        items.append(current)

    return items


def dedup_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def is_ip_host(host: str | None) -> bool:
    if not host:
        return False
    return bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host))


def classify_url(url: str) -> str:
    if url.startswith("tcp://127.0.0.1"):
        return "validator"

    try:
        p = urlparse(url)
        host = p.hostname
    except Exception:
        return "public"

    if host in {"127.0.0.1", "localhost"}:
        return "validator"

    if is_ip_host(host):
        return "validator"

    return "public"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_chain_dirs_by_chain_id(chain_registry_dir: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}

    if not chain_registry_dir.exists():
        return result

    for chain_json in chain_registry_dir.rglob("chain.json"):
        if any(part.startswith(".") for part in chain_json.parts):
            continue

        data = load_json(chain_json)
        if not data:
            continue

        chain_id = data.get("chain_id")
        if chain_id and chain_id not in result:
            result[str(chain_id)] = chain_json.parent

    return result


def extract_rpc_rest_grpc(chain_json: dict) -> tuple[str | None, str | None, str | None]:
    apis = chain_json.get("apis") or {}

    rpc = None
    rest = None
    grpc = None

    rpc_items = apis.get("rpc") or []
    rest_items = apis.get("rest") or []
    grpc_items = apis.get("grpc") or []

    if rpc_items:
        rpc = normalize_url(rpc_items[0].get("address"))
    if rest_items:
        rest = normalize_url(rest_items[0].get("address"))
    if grpc_items:
        grpc = normalize_url(grpc_items[0].get("address"))

    return rpc, rest, grpc


def fetch_validator_moniker_from_rest(rest_url: str | None, operator_address: str | None) -> str | None:
    if not rest_url or not operator_address:
        return None

    candidates = [
        f"{rest_url}/cosmos/staking/v1beta1/validators/{operator_address}",
        f"{rest_url}/staking/validators/{operator_address}",
    ]

    for url in candidates:
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            if resp.status_code != 200:
                continue

            data = resp.json() or {}
            validator = data.get("validator") or data.get("result") or data
            description = validator.get("description") or {}
            moniker = description.get("moniker") or validator.get("moniker")

            if moniker and str(moniker).strip():
                return str(moniker).strip()
        except Exception:
            continue

    return None


def fetch_moniker_from_rpc_status(rpc_url: str | None) -> str | None:
    if not rpc_url:
        return None

    try:
        resp = requests.get(f"{rpc_url}/status", timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return None

        data = resp.json() or {}
        result = data.get("result") or {}
        node_info = result.get("node_info") or {}
        moniker = node_info.get("moniker")
        if moniker and str(moniker).strip():
            return str(moniker).strip()
    except Exception:
        return None

    return None


def resolve_moniker(
    chain_id: str,
    operator_address: str,
    primary_rpc_url: str | None,
    chain_dir_map: dict[str, Path],
) -> str:
    rest_url = None
    chain_dir = chain_dir_map.get(chain_id)
    if chain_dir:
        chain_json = load_json(chain_dir / "chain.json") or {}
        _, rest_url, _ = extract_rpc_rest_grpc(chain_json)

    moniker = fetch_validator_moniker_from_rest(rest_url, operator_address)
    if moniker:
        return moniker

    moniker = fetch_moniker_from_rpc_status(primary_rpc_url)
    if moniker:
        return moniker

    return "PostHuman"


def bech32_polymod(values):
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            chk ^= generator[i] if ((b >> i) & 1) else 0
    return chk


def bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bech32_verify_checksum(hrp, data):
    return bech32_polymod(bech32_hrp_expand(hrp) + data) == 1


def bech32_create_checksum(hrp, data):
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp, data):
    combined = data + bech32_create_checksum(hrp, data)
    return hrp + "1" + "".join([CHARSET[d] for d in combined])


def bech32_decode(bech: str):
    if not bech or any(ord(x) < 33 or ord(x) > 126 for x in bech):
        return None, None

    bech = bech.strip()
    if bech.lower() != bech and bech.upper() != bech:
        return None, None

    bech = bech.lower()
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech):
        return None, None

    hrp = bech[:pos]
    data_part = bech[pos + 1:]

    try:
        data = [CHARSET.index(c) for c in data_part]
    except ValueError:
        return None, None

    if not bech32_verify_checksum(hrp, data):
        return None, None

    return hrp, data[:-6]


def valoper_to_delegator_address(operator_address: str | None) -> str | None:
    if not operator_address:
        return None

    value = operator_address.strip()
    if "valoper1" not in value:
        return None

    try:
        old_hrp, data = bech32_decode(value)
        if old_hrp is None or data is None:
            return None

        if not old_hrp.endswith("valoper"):
            return None

        new_hrp = old_hrp[:-7]
        if not new_hrp:
            return None

        return bech32_encode(new_hrp, data)
    except Exception:
        return None


def get_or_create_network(db, chain_id: str) -> Network:
    network = db.execute(
        select(Network).where(Network.chain_id == chain_id)
    ).scalar_one_or_none()

    if network:
        return network

    network = Network(
        chain_id=chain_id,
        name=chain_id,
        display_name=chain_id,
        is_enabled=1,
    )
    db.add(network)
    db.flush()
    return network


def get_validator(db, chain_id: str, operator_address: str) -> Validator | None:
    return db.execute(
        select(Validator)
        .where(Validator.chain_id == chain_id)
        .where(Validator.operator_address == operator_address)
    ).scalar_one_or_none()


def main() -> None:
    if not POSTHUMAN_FILE.exists():
        raise FileNotFoundError(f"Source file not found: {POSTHUMAN_FILE}")

    raw = POSTHUMAN_FILE.read_text(encoding="utf-8")
    items = parse_posthuman_source(raw)
    chain_dir_map = find_chain_dirs_by_chain_id(CHAIN_REGISTRY_DIR)

    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        created_networks = 0
        created_validators = 0
        updated_validators = 0

        for item in items:
            chain_id = item["chain_id"]
            valoper = item["valoper_address"]
            urls = dedup_keep_order(item["urls"])
            metrics_url = normalize_url(item.get("metrics_url"))

            if not chain_id or not valoper:
                continue

            network_before = db.execute(
                select(Network).where(Network.chain_id == chain_id)
            ).scalar_one_or_none()

            get_or_create_network(db, chain_id)
            if network_before is None:
                created_networks += 1

            validator_urls = dedup_keep_order([u for u in urls if classify_url(u) == "validator"])
            primary_rpc_url = validator_urls[0] if validator_urls else None
            delegator_address = valoper_to_delegator_address(valoper)

            moniker = resolve_moniker(
                chain_id=chain_id,
                operator_address=valoper,
                primary_rpc_url=primary_rpc_url,
                chain_dir_map=chain_dir_map,
            )

            validator = get_validator(db, chain_id, valoper)

            if validator is None:
                validator = Validator(
                    chain_id=chain_id,
                    moniker=moniker,
                    operator_address=valoper,
                    delegator_address=delegator_address,
                    consensus_address=None,
                    rpc_url=primary_rpc_url,
                    metrics_url=metrics_url,
                    is_main=1,
                    is_enabled=1,
                    created_at=now,
                    updated_at=now,
                )
                db.add(validator)
                created_validators += 1
            else:
                validator.moniker = moniker or validator.moniker or "PostHuman"
                validator.delegator_address = delegator_address or validator.delegator_address
                validator.rpc_url = primary_rpc_url or validator.rpc_url
                validator.metrics_url = metrics_url or validator.metrics_url
                validator.is_main = 1
                validator.is_enabled = 1
                validator.updated_at = now
                updated_validators += 1

            print(
                f"[OK] {chain_id}: moniker={moniker} rpc={primary_rpc_url or '-'} metrics={metrics_url or '-'}"
            )

        db.commit()

        print("\nPostHuman validators import complete")
        print(f"Created networks: {created_networks}")
        print(f"Created validators: {created_validators}")
        print(f"Updated validators: {updated_validators}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
