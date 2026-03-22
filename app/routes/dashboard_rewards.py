from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

DATA_FILE = Path("commission_snapshot.json")


@router.get("/dashboard/rewards")
def rewards(request: Request):

    if not DATA_FILE.exists():
        return templates.TemplateResponse(
            "rewards.html",
            {
                "request": request,
                "networks": [],
                "tokens": []
            }
        )

    data = json.loads(DATA_FILE.read_text())

    rows = data["rows"]
    totals_by_network = data["totals_by_network"]

    # ----- networks table -----

    networks = []

    for n, total in totals_by_network.items():
        networks.append({
            "network": n,
            "total": total
        })

    networks.sort(key=lambda x: -x["total"])

    # ----- tokens table -----

    tokens_map = {}

    for r in rows:

        token = r["display"]

        if token not in tokens_map:
            tokens_map[token] = {
                "token": token,
                "amount": 0,
                "usd": 0
            }

        tokens_map[token]["amount"] += r["amount"]
        tokens_map[token]["usd"] += r["total"]

    tokens = list(tokens_map.values())
    tokens.sort(key=lambda x: -x["usd"])

    return templates.TemplateResponse(
        "rewards.html",
        {
            "request": request,
            "networks": networks,
            "tokens": tokens
        }
    )
