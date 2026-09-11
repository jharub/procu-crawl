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

import requests


def send_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[avertisment] TELEGRAM_BOT_TOKEN sau TELEGRAM_CHAT_ID lipsesc - afisez doar in log:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=15,
    )
    if not resp.ok:
        print(f"[eroare] Telegram a raspuns {resp.status_code}: {resp.text}")
