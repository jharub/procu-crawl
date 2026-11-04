"""
Radar de licitatii - arhitectura / urbanism.

Ruleaza periodic (vezi .github/workflows/radar.yml), aduna anunturi noi din:
  - TED (API oficial UE, licitatii peste pragul UE)
  - API-ul intern SICAP/e-licitatie.ro (achizitii directe + anunturi de participare,
    sub si peste prag, in timp real - vezi sicap_api.py)
retine ce a mai trimis deja (state/seen.json), notifica prin Telegram doar noutatile,
si actualizeaza baza de date a site-ului static (docs/data.json - vezi site_data.py).
"""

from __future__ import annotations

import html
import json
import os

import notify_telegram
import sicap_api
import site_data
import ted_client
from config import NOTIFY_TED_ON_TELEGRAM, STATE_FILE


def _load_seen() -> set[str]:
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def _save_seen(seen: set[str]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def _format_item(item: dict) -> str:
    # Mesajul pleaca cu parse_mode=HTML: orice "&" sau "<" neescapat dintr-un titlu
    # face Telegram sa refuze tot mesajul ("can't parse entities").
    esc = html.escape
    lines = [
        f"<b>{esc(item['title'][:200])}</b>",
        f"Sursa: {esc(item['source'])}",
    ]
    if item.get("authority"):
        lines.append(f"Autoritate: {esc(item['authority'])}")
    if item.get("deadline"):
        lines.append(f"Termen: {esc(str(item['deadline']))}")
    if item.get("value"):
        lines.append(f"Valoare estimata: {esc(str(item['value']))}")
    if item.get("cpv"):
        lines.append(f"CPV: {esc(', '.join(str(c) for c in item['cpv']))}")
    lines.append(esc(item.get("url", "")))
    return "\n".join(lines)


def run(days_back: int = 3) -> None:
    seen = _load_seen()
    new_items: list[dict] = []
    site_data.write_cpv_reference()

    print("[info] interogare TED...")
    try:
        ted_raw = ted_client.fetch_recent_notices(days_back=days_back)
        ted_items = [ted_client.normalize(n) for n in ted_raw]
        print(f"[info] TED: {len(ted_items)} anunturi gasite pe CPV-urile configurate")
    except Exception as exc:
        print(f"[eroare] interogare TED esuata: {exc}")
        ted_items = []

    print("[info] interogare SICAP (e-licitatie.ro)...")
    try:
        sicap_items = sicap_api.fetch_relevant_items(days_back=days_back)
        print(f"[info] SICAP: {len(sicap_items)} inregistrari relevante gasite")
    except Exception as exc:
        print(f"[eroare] interogare SICAP esuata: {exc}")
        sicap_items = []

    for item in ted_items + sicap_items:
        key = f"{item['source']}::{item['id']}"
        if key in seen:
            continue
        seen.add(key)
        new_items.append(item)

    if not new_items:
        print("[info] nimic nou de notificat.")
    else:
        print(f"[info] {len(new_items)} anunturi noi - iau detalii si trimit notificari...")
        for idx, item in enumerate(new_items):
            if item["source"].startswith("SICAP"):
                item = sicap_api.enrich_item(item)
                new_items[idx] = item
            if item["source"] == "TED" and not NOTIFY_TED_ON_TELEGRAM:
                continue
            notify_telegram.send_message(_format_item(item))
        site_data.merge_new_items(new_items)

    _save_seen(seen)


if __name__ == "__main__":
    run()
