"""
Client pentru API-ul public oficial TED (Tenders Electronic Daily).

Documentatie oficiala: https://docs.ted.europa.eu/api/endpoints/ted-europa-eu.html
Nu necesita autentificare. Endpoint: POST https://api.ted.europa.eu/v3/notices/search

Acopera doar anunturile PESTE pragul UE de achizitii publice (nu achizitiile directe
si multe proceduri simplificate mici, care raman doar pe SEAP intern - vezi seap_direct.py).
"""

from __future__ import annotations

import requests

from config import CPV_CODES, TED_BUYER_COUNTRY

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

# Campurile pe care le cerem inapoi de la API (tinem lista scurta ca sa nu depasim
# limita de "fields per page" a modului de paginare simplu).
FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "publication-date",
    "deadline-receipt-tender-date-lot",
    "deadline",
    "estimated-value-proc",
    "estimated-value-lot",
    "links",
]


def _build_query(days_back: int) -> str:
    """Construieste query-ul in sintaxa TED expert search."""
    cpv_clause = " OR ".join(f"classification-cpv={code}" for code in CPV_CODES)
    return (
        f"buyer-country={TED_BUYER_COUNTRY} "
        f"AND ({cpv_clause}) "
        f"AND publication-date >= today(-{days_back})"
    )


def fetch_recent_notices(days_back: int = 3, page_size: int = 100) -> list[dict]:
    """
    Intoarce anunturile TED pentru Romania, publicate in ultimele `days_back` zile,
    pe codurile CPV configurate. Pagineaza automat pana epuizeaza rezultatele
    (limita API-ului in modul simplu de paginare este 15.000 anunturi / query,
    suficient de larg pentru un query filtrat pe tara + CPV).
    """
    query = _build_query(days_back)
    all_notices: list[dict] = []
    page = 1

    while True:
        payload = {
            "query": query,
            "fields": FIELDS,
            "page": page,
            "limit": page_size,
        }
        resp = requests.post(TED_SEARCH_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        notices = data.get("notices", [])
        if not notices:
            break

        all_notices.extend(notices)

        total = data.get("totalNoticeCount", 0)
        if page * page_size >= total:
            break
        page += 1

    return all_notices


def _flatten_text(val):
    """
    Multe campuri TED sunt fie liste, fie obiecte multilingve de forma
    {"ron": ["text"], "eng": ["text"]}. Extrage un text simplu, preferand
    romana, apoi orice alta limba disponibila.
    """
    if isinstance(val, list):
        val = val[0] if val else None
    if isinstance(val, dict):
        preferred = val.get("ron") or next(iter(val.values()), None)
        return _flatten_text(preferred)
    return val


def normalize(notice: dict) -> dict:
    """Aduce un anunt TED la un format comun cu cel din seap_direct.py."""

    def first(field):
        return _flatten_text(notice.get(field))

    links = notice.get("links") or {}
    html_links = links.get("html") or {}
    url = html_links.get("ROU") or html_links.get("ENG") or next(iter(html_links.values()), "")

    return {
        "source": "TED",
        "id": notice.get("publication-number"),
        "title": first("notice-title") or "(fara titlu)",
        "authority": first("buyer-name") or "",
        "cpv": notice.get("classification-cpv") or [],
        "published": first("publication-date") or "",
        "deadline": first("deadline-receipt-tender-date-lot") or first("deadline") or "",
        "value": first("estimated-value-proc") or first("estimated-value-lot") or "",
        "url": url or f"https://ted.europa.eu/en/notice/-/detail/{notice.get('publication-number')}",
    }
