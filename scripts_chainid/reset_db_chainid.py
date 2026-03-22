#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.db import engine
from app.models_chainid.base import Base

from app.models_chainid import (  # noqa: F401
    EndpointCheck,
    Event,
    Network,
    NetworkAsset,
    NetworkEndpoint,
    NetworkStatusCurrent,
    PublicRpcCheck,
    PublicRpcEndpoint,
    SnapshotCheck,
    SnapshotTarget,
    TrackedNetwork,
    Validator,
    ValidatorStatusCurrent,
    ValidatorStatusHistory,
)


def main() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("ChainID DB reset complete")


if __name__ == "__main__":
    main()
