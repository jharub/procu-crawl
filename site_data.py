"""
Gestioneaza baza de date (docs/data.json) care alimenteaza site-ul static
(docs/index.html), publicat prin GitHub Pages.

Spre deosebire de state/seen.json (care tine minte doar cheile deja
notificate, ca sa nu trimitem de doua ori acelasi anunt pe Telegram), acest
fisier tine si datele complete (titlu, autoritate, termen, cerinte,
documente) ale anunturilor recente, ca sa poata fi afisate intr-o interfata.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

DATA_FILE = os.path.join("docs", "data.json")

# Cat timp pastram un anunt in site dupa ce a fost publicat, chiar daca
# termenul lui de depunere a trecut - util ca istoric recent, fara sa lasam
# fisierul sa creasca la nesfarsit.
RETENTION_DAYS = 60


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_items() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_items(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _should_keep(item: dict, now: datetime, cutoff: datetime) -> bool:
    deadline = _parse_dt(item.get("deadline"))
    if deadline and deadline >= now:
        return True
    published = _parse_dt(item.get("published"))
    return bool(published and published >= cutoff)


def merge_new_items(new_items: list[dict]) -> None:
    """Adauga anunturile noi (deja imbogatite cu detalii) in baza de date a
    site-ului si elimina intrarile expirate/vechi."""
    existing = load_items()
    existing_keys = {item["key"] for item in existing}

    for item in new_items:
        key = f"{item['source']}::{item['id']}"
        if key in existing_keys:
            continue
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        clean["key"] = key
        existing.append(clean)
        existing_keys.add(key)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    kept = [item for item in existing if _should_keep(item, now, cutoff)]
    kept.sort(key=lambda item: item.get("published") or "", reverse=True)

    _save_items(kept)
    print(f"[info] site: {len(kept)} anunturi in {DATA_FILE} ({len(new_items)} noi adaugate acum)")
