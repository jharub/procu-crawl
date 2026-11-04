"""
Trimite notificari prin bot Telegram.

Setup (o singura data, 5 minute):
  1. In Telegram, cauta @BotFather, trimite /newbot, urmeaza pasii.
     Primesti un TOKEN (arata cam asa: 123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx).
  2. Cauta botul tau (numele ales la pasul 1) si trimite-i orice mesaj (ex: "salut"),
     ca sa "deblochezi" conversatia.
  3. Acceseaza in browser:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     (inlocuieste <TOKEN> cu tokenul tau). Cauta in raspuns "chat":{"id": ...} - acela
     e CHAT_ID-ul tau.
  4. Pune TOKEN si CHAT_ID ca secrete in GitHub Actions (vezi README.md).
"""

from __future__ import annotations

import os
import time

import requests


def send_message(text: str) -> None:
    """Trimite un mesaj. Nu ridica niciodata exceptii: o problema de retea sau un
    refuz de la Telegram se scrie in log, ca sa nu opreasca restul rularii (altfel
    nu se mai salveaza nici evidenta anunturilor, nici datele site-ului)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[avertisment] TELEGRAM_BOT_TOKEN sau TELEGRAM_CHAT_ID lipsesc - afisez doar in log:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    # O singura reincercare: la 429 (prea multe mesaje deodata, ex. dupa o rulare
    # ratata se aduna zeci de anunturi) asteptam cat cere Telegram; la erori de
    # retea, cateva secunde.
    for attempt in (1, 2):
        try:
            resp = requests.post(url, json=payload, timeout=15)
        except requests.RequestException as exc:
            print(f"[eroare] trimitere Telegram esuata (incercarea {attempt}): {exc}")
            if attempt == 1:
                time.sleep(5)
            continue

        if resp.ok:
            return
        if resp.status_code == 429 and attempt == 1:
            try:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
            except ValueError:
                retry_after = 5
            time.sleep(min(retry_after, 60))
            continue
        print(f"[eroare] Telegram a raspuns {resp.status_code}: {resp.text}")
        return
