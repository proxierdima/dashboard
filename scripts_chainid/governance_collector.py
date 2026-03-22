#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import select, update

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.models_chainid import GovernanceProposal, Network, Validator

HTTP_TIMEOUT = 8
CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

ACTIVE_STATUSES_V1 = {
    "PROPOSAL_STATUS_VOTING_PERIOD",
    "PROPOSAL_STATUS_DEPOSIT_PERIOD",
}
ACTIVE_STATUSES_V1BETA1 = {
    "VotingPeriod",
    "DepositPeriod",
}


def parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def get_rest_candidates(network: Network | None) -> list[str]:
    if not network:
        return []

    result = []
    for value in [network.rest, getattr(network, "rest1", None), getattr(network, "rest2", None)]:
        if value and value not in result:
            result.append(value.rstrip("/"))
    return result


def parse_votes(final_tally: dict | None) -> tuple[float, float, float, float]:
    if not final_tally:
        return 0.0, 0.0, 0.0, 0.0

    return (
        float(final_tally.get("yes_count") or 0),
        float(final_tally.get("no_count") or 0),
        float(final_tally.get("abstain_count") or 0),
        float(final_tally.get("no_with_veto_count") or 0),
    )


def fetch_active_proposals(rest_url: str) -> tuple[list[dict], str] | tuple[list, None]:
    candidates = [
        (
            f"{rest_url}/cosmos/gov/v1/proposals?proposal_status=PROPOSAL_STATUS_VOTING_PERIOD",
            "v1",
        ),
        (
            f"{rest_url}/cosmos/gov/v1beta1/proposals?proposal_status=VotingPeriod",
            "v1beta1",
        ),
    ]

    for url, api_version in candidates:
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            if resp.status_code != 200:
                continue

            data = resp.json() or {}
            proposals = data.get("proposals") or []
            return proposals, api_version
        except Exception:
            continue

    return [], None


def fetch_tally_v1(rest_url: str, proposal_id: int) -> tuple[float, float, float, float] | None:
    try:
        url = f"{rest_url}/cosmos/gov/v1/proposals/{proposal_id}/tally"
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return None

        data = resp.json() or {}
        tally = data.get("tally") or data.get("final_tally_result") or {}
        return parse_votes(tally)
    except Exception:
        return None


def fetch_tally_v1beta1(rest_url: str, proposal_id: int) -> tuple[float, float, float, float] | None:
    try:
        url = f"{rest_url}/cosmos/gov/v1beta1/proposals/{proposal_id}/tally"
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return None

        data = resp.json() or {}
        tally = data.get("tally_result") or data.get("final_tally_result") or {}
        return parse_votes(tally)
    except Exception:
        return None


def fetch_proposal_tally(rest_url: str, api_version: str, proposal_id: int, proposal: dict) -> tuple[float, float, float, float]:
    fetchers = []
    if api_version == "v1":
        fetchers = [fetch_tally_v1, fetch_tally_v1beta1]
    elif api_version == "v1beta1":
        fetchers = [fetch_tally_v1beta1, fetch_tally_v1]
    else:
        fetchers = [fetch_tally_v1, fetch_tally_v1beta1]

    for fetcher in fetchers:
        result = fetcher(rest_url, proposal_id)
        if result is not None:
            return result

    return parse_votes(proposal.get("final_tally_result"))


def normalize_title(proposal: dict) -> str:
    return (
        proposal.get("title")
        or (proposal.get("content") or {}).get("title")
        or "No title"
    )


def normalize_status(proposal: dict) -> str:
    return str(proposal.get("status") or "").strip()


def is_active_status(status: str) -> bool:
    return status in ACTIVE_STATUSES_V1 or status in ACTIVE_STATUSES_V1BETA1


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


def get_voter_candidates(validator: Validator) -> list[str]:
    candidates: list[str] = []
    for value in [
        getattr(validator, "delegator_address", None),
        valoper_to_delegator_address(getattr(validator, "operator_address", None)),
        getattr(validator, "operator_address", None),
    ]:
        if value:
            addr = str(value).strip()
            if addr and addr not in candidates:
                candidates.append(addr)
    return candidates


def extract_vote_option(vote: dict | None) -> str | None:
    if not vote:
        return None

    option = vote.get("option")
    if isinstance(option, str) and option.strip():
        return option.strip()
    if isinstance(option, list) and option:
        first = option[0] or {}
        value = first.get("option")
        if value:
            return str(value).strip()

    for key in ("options", "weighted_vote_options"):
        options = vote.get(key)
        if isinstance(options, list) and options:
            def sort_key(item):
                try:
                    return float(item.get("weight") or 0)
                except Exception:
                    return 0.0
            best = sorted(options, key=sort_key, reverse=True)[0] or {}
            value = best.get("option")
            if value:
                return str(value).strip()

    return None


def fetch_vote_v1(rest_url: str, proposal_id: int, voter_address: str) -> tuple[int, str | None]:
    try:
        url = f"{rest_url}/cosmos/gov/v1/proposals/{proposal_id}/votes/{voter_address}"
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return 0, None

        data = resp.json() or {}
        vote = data.get("vote") or {}
        return 1, extract_vote_option(vote)
    except Exception:
        return 0, None


def fetch_vote_v1beta1(rest_url: str, proposal_id: int, voter_address: str) -> tuple[int, str | None]:
    try:
        url = f"{rest_url}/cosmos/gov/v1beta1/proposals/{proposal_id}/votes/{voter_address}"
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            return 0, None

        data = resp.json() or {}
        vote = data.get("vote") or {}
        return 1, extract_vote_option(vote)
    except Exception:
        return 0, None


def fetch_validator_vote(rest_url: str, api_version: str, proposal_id: int, validator: Validator) -> tuple[int, str | None]:
    voter_candidates = get_voter_candidates(validator)
    if not voter_candidates:
        return 0, None

    if api_version == "v1":
        fetchers = [fetch_vote_v1, fetch_vote_v1beta1]
    elif api_version == "v1beta1":
        fetchers = [fetch_vote_v1beta1, fetch_vote_v1]
    else:
        return 0, None

    for voter_address in voter_candidates:
        for fetcher in fetchers:
            voted, option = fetcher(rest_url, proposal_id, voter_address)
            if voted:
                return voted, option

    return 0, None


def upsert_active_proposal(
    db,
    chain_id: str,
    proposal_id: int,
    title: str,
    status: str,
    voting_start_time,
    voting_end_time,
    yes_votes: float,
    no_votes: float,
    abstain_votes: float,
    no_with_veto_votes: float,
    validator_voted: int,
    validator_vote_option: str | None,
    now,
) -> None:
    db.execute(
        update(GovernanceProposal)
        .where(GovernanceProposal.chain_id == chain_id)
        .where(GovernanceProposal.proposal_id == proposal_id)
        .values(is_latest=0, updated_at=now)
    )

    db.add(
        GovernanceProposal(
            chain_id=chain_id,
            proposal_id=proposal_id,
            title=title,
            status=status,
            voting_start_time=voting_start_time,
            voting_end_time=voting_end_time,
            yes_votes=yes_votes,
            no_votes=no_votes,
            abstain_votes=abstain_votes,
            no_with_veto_votes=no_with_veto_votes,
            validator_voted=validator_voted,
            validator_vote_option=validator_vote_option,
            is_latest=1,
            created_at=now,
            updated_at=now,
        )
    )


def main():
    db = SessionLocal()
    try:
        validators = db.execute(
            select(Validator).where(Validator.is_enabled == 1)
        ).scalars().all()

        if not validators:
            print("No enabled validators found.")
            return

        networks = {
            n.chain_id: n
            for n in db.execute(select(Network)).scalars().all()
        }

        processed_chains = set()

        for validator in validators:
            chain_id = validator.chain_id
            if chain_id in processed_chains:
                continue
            processed_chains.add(chain_id)

            network = networks.get(chain_id)
            rest_candidates = get_rest_candidates(network)
            if not rest_candidates:
                print(f"[MISS] {chain_id}: no REST endpoint in networks table")
                continue

            proposals = []
            api_version = None
            used_rest = None

            for rest_url in rest_candidates:
                proposals, api_version = fetch_active_proposals(rest_url)
                if api_version:
                    used_rest = rest_url
                    break

            if not used_rest:
                print(f"[MISS] {chain_id}: active proposals endpoint unavailable")
                continue

            print(f"\n=== {chain_id} ===")
            print(f"REST: {used_rest}")
            print(f"Voter candidates: {', '.join(get_voter_candidates(validator)) or '-'}")
            print(f"Found active proposals: {len(proposals)}")

            now = datetime.now(timezone.utc)

            for proposal in proposals:
                try:
                    proposal_id = int(proposal.get("id"))
                except Exception:
                    continue

                title = normalize_title(proposal)
                status = normalize_status(proposal)

                if not is_active_status(status):
                    continue

                voting_start_time = parse_time(proposal.get("voting_start_time"))
                voting_end_time = parse_time(proposal.get("voting_end_time"))

                yes_votes, no_votes, abstain_votes, no_with_veto_votes = fetch_proposal_tally(
                    used_rest,
                    api_version,
                    proposal_id,
                    proposal,
                )

                validator_voted, validator_vote_option = fetch_validator_vote(
                    used_rest,
                    api_version,
                    proposal_id,
                    validator,
                )

                upsert_active_proposal(
                    db=db,
                    chain_id=chain_id,
                    proposal_id=proposal_id,
                    title=title,
                    status=status,
                    voting_start_time=voting_start_time,
                    voting_end_time=voting_end_time,
                    yes_votes=yes_votes,
                    no_votes=no_votes,
                    abstain_votes=abstain_votes,
                    no_with_veto_votes=no_with_veto_votes,
                    validator_voted=validator_voted,
                    validator_vote_option=validator_vote_option,
                    now=now,
                )

                print(
                    f"[OK] proposal={proposal_id} "
                    f"voted={validator_voted} "
                    f"vote={validator_vote_option or '-'} "
                    f"tally=yes:{yes_votes} no:{no_votes} abstain:{abstain_votes} veto:{no_with_veto_votes} "
                    f"title={title}"
                )

        db.commit()
        print("\nGovernance collector complete.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
