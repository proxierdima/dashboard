#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from sqlalchemy import delete, select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.models_chainid import Network, NetworkAsset

POSTHUMAN_FILE = Path("config/posthuman_endpoints.txt")
CHAIN_REGISTRY_DIR = Path("chain-registry")

CHAIN_RE = re.compile(r"^\s*chain_id:\s*(.+?)\s*$")


def clean_value(s: str) -> str:
    return s.strip().strip('"').strip("'")


def normalize_chain_id(chain_id: str | None) -> str | None:
    if not chain_id:
        return None
    return " ".join(chain_id.strip().split())


def parse_required_chain_ids(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    result: list[str] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        m = CHAIN_RE.match(raw_line.rstrip())
        if not m:
            continue

        chain_id = normalize_chain_id(clean_value(m.group(1)))
        if chain_id and chain_id not in result:
            result.append(chain_id)

    return result


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_chain_dirs_by_chain_id(chain_registry_dir: Path) -> dict[str, Path]:
    """
    Рекурсивно ищет все chain.json в chain-registry и testnets.
    Строит map:
      chain_id -> <dir>
    """
    result: dict[str, Path] = {}

    if not chain_registry_dir.exists():
        raise FileNotFoundError(f"Chain registry dir not found: {chain_registry_dir}")

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
        rpc = rpc_items[0].get("address")
    if rest_items:
        rest = rest_items[0].get("address")
    if grpc_items:
        grpc = grpc_items[0].get("address")

    return rpc, rest, grpc


def extract_main_asset(assetlist_json: dict | None) -> dict:
    if not assetlist_json:
        return {}

    assets = assetlist_json.get("assets") or []
    if not assets:
        return {}

    asset = assets[0] or {}
    base = asset.get("base")
    symbol = asset.get("symbol")
    display = asset.get("display")
    coingecko_id = asset.get("coingecko_id")

    exponent = None
    denom_units = asset.get("denom_units") or []
    for unit in denom_units:
        if unit.get("denom") == display:
            exponent = unit.get("exponent")
            break

    if exponent is None and denom_units:
        exponent = denom_units[-1].get("exponent")

    return {
        "base_denom": base,
        "symbol": symbol,
        "display": display,
        "display_denom": display,
        "exponent": exponent,
        "coingecko_id": coingecko_id,
    }


def detect_network_type(chain_json: dict, chain_dir: Path) -> str:
    status = str(chain_json.get("status") or "").lower()
    parts = [p.lower() for p in chain_dir.parts]

    if "testnet" in status:
        return "testnet"

    if "testnets" in parts:
        return "testnet"

    if "testnet" in chain_dir.name.lower():
        return "testnet"

    return "mainnet"


def ensure_network(db, chain_id: str) -> Network:
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


def main() -> None:
    required_chain_ids = parse_required_chain_ids(POSTHUMAN_FILE)
    chain_dir_map = find_chain_dirs_by_chain_id(CHAIN_REGISTRY_DIR)

    db = SessionLocal()
    try:
        imported = 0
        enriched = 0
        not_found: list[str] = []

        for chain_id in required_chain_ids:
            network = ensure_network(db, chain_id)

            chain_dir = chain_dir_map.get(chain_id)
            if not chain_dir:
                not_found.append(chain_id)
                print(f"[MISS] {chain_id}: not found in chain-registry/testnets")
                continue

            chain_json = load_json(chain_dir / "chain.json") or {}
            assetlist_json = load_json(chain_dir / "assetlist.json") or {}

            rpc, rest, grpc = extract_rpc_rest_grpc(chain_json)
            asset = extract_main_asset(assetlist_json)

            network.name = chain_json.get("chain_name") or network.name or chain_id
            network.display_name = chain_json.get("pretty_name") or network.display_name or chain_id
            network.directory = chain_dir.name
            network.chain_id = chain_id
            network.chain_type = "cosmos"
            network.network_type = detect_network_type(chain_json, chain_dir)
            network.status = chain_json.get("status")
            network.website = chain_json.get("website")
            network.bech32_prefix = chain_json.get("bech32_prefix")
            network.daemon_name = chain_json.get("daemon_name")
            network.node_home = chain_json.get("node_home")
            network.key_algos = json.dumps(chain_json.get("key_algos")) if chain_json.get("key_algos") else None
            network.slip44 = chain_json.get("slip44")

            network.base_denom = asset.get("base_denom")
            network.display_denom = asset.get("display_denom")
            network.exponent = asset.get("exponent")
            network.coingecko_id = asset.get("coingecko_id")

            network.fee_tokens = json.dumps(chain_json.get("fees")) if chain_json.get("fees") else None
            network.staking_tokens = json.dumps(chain_json.get("staking")) if chain_json.get("staking") else None

            codebase = chain_json.get("codebase") or {}
            network.git_repo = codebase.get("git_repo")
            network.recommended_version = codebase.get("recommended_version")
            network.compatible_versions = json.dumps(codebase.get("compatible_versions")) if codebase.get("compatible_versions") else None

            network.genesis_url = (chain_json.get("genesis") or {}).get("genesis_url")

            network.rpc = rpc
            network.rest = rest
            network.grpc = grpc

            db.execute(delete(NetworkAsset).where(NetworkAsset.chain_id == chain_id))

            if asset.get("base_denom"):
                db.add(
                    NetworkAsset(
                        chain_id=chain_id,
                        base_denom=asset["base_denom"],
                        symbol=asset.get("symbol"),
                        display=asset.get("display"),
                        display_denom=asset.get("display_denom"),
                        exponent=asset.get("exponent"),
                        coingecko_id=asset.get("coingecko_id"),
                    )
                )

            enriched += 1
            imported += 1

            print(
                f"[OK] {chain_id}: dir={chain_dir.name} type={network.network_type} "
                f"rpc={rpc or '-'} rest={rest or '-'} grpc={grpc or '-'}"
            )

        db.commit()

        print("\nChain registry import complete")
        print(f"Imported networks: {imported}")
        print(f"Enriched networks: {enriched}")

        if not_found:
            print("\nNot found in chain-registry/testnets:")
            for chain_id in not_found:
                print(f"  - {chain_id}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
