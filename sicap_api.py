"""
Client pentru API-ul intern (nedocumentat oficial) al platformei e-licitatie.ro
(SICAP), verificat live pe 11.09.2026.

Acest API e cel folosit chiar de front-end-ul site-ului pentru formularele de
cautare - raspunde in JSON, nu are CAPTCHA, dar respinge cererile fara un
header Referer/Origin care sa para ca vine dintr-un browser ("Access Denied:
Referrer cannot be null"). Nu ocolim nicio protectie reala (nu e nevoie de
autentificare sau token), doar ne prezentam ca un browser obisnuit.

Doua surse, gasite prin inspectarea cererilor reale trimise de formularele de
filtrare ale site-ului (nu ghicite din documentatie, pentru ca nu exista):

  - DirectAcquisitionCommon/GetDirectAcquisitionList - achizitii directe
    (cumparari sub prag, catalogul electronic de achizitii directe)
  - NoticeCommon/GetCNoticeList - anunturi de participare (CN) si anunturi de
    participare simplificate (SCN): licitatiile propriu-zise, publicate
    INAINTE de atribuire - nu anunturile de atribuire/rezultat.

Ambele accepta un interval pe data publicarii, ceea ce ne permite sa cerem
"ultimele N zile" in loc sa descarcam un export intreg pe an. Atentie: numele
campurilor de data DIFERA intre cele doua servicii (nu e o greseala aici, asa
raspunde API-ul):
  - DirectAcquisitionCommon foloseste publicationDateStart / publicationDateEnd
  - NoticeCommon foloseste startPublicationDate / endPublicationDate
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import requests

from config import CPV_CODES, KEYWORDS

BASE_URL = "https://e-licitatie.ro/api-pub"

HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://e-licitatie.ro/pub/notices/contract-notices/list/0/0",
    "Origin": "https://e-licitatie.ro",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

# sysNoticeTypeId pentru "Anunt de participare" (CN) si "Anunt de participare
# simplificat" (SCN) - identificate live bifand tipurile respective in
# formularul de filtrare si inspectand cererea trimisa. Sunt anunturile de
# oportunitati NOI (inainte de atribuire), nu cele de atribuire/rezultat.
NOTICE_TYPE_IDS = [2, 17]

# sysProcedureState.id = 2 înseamna "In desfasurare" (procedura e inca
# deschisa, se mai pot depune oferte). Filtram dupa el ca sa nu raportam
# anunturi deja atribuite/anulate care intra intamplator in fereastra de date.
OPEN_PROCEDURE_STATE_ID = 2

PAGE_SIZE = 100
MAX_PAGES = 50  # limita de siguranta, sa nu intram intr-o bucla infinita

# Achizitiile directe au un volum foarte mare la nivel de tara (mii/zi, toate
# categoriile, nu doar arhitectura). Verificat live: la peste ~1 zi in
# fereastra de cautare, API-ul raspunde cu total plafonat la 2000 si
# searchTooLong=true, ceea ce inseamna rezultate INCOMPLETE (risc sa ratam
# achizitii relevante). De-aia interogam aceasta sursa in bucati de maxim
# 1 zi, cu o mica suprapunere, indiferent cat de mare e days_back cerut.
DIRECT_ACQUISITION_CHUNK_HOURS = 20
DIRECT_ACQUISITION_OVERLAP_HOURS = 1

# Diacritice romanesti -> ASCII, ca sa comparam text indiferent daca sursa
# foloseste sau nu diacritice corecte (SEAP e inconsistent intre seturi de date).
_DIACRITICS = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaisstt" "AAISSTT")


def _normalize_ro(text: str) -> str:
    return text.translate(_DIACRITICS).lower()


def _keyword_match(text: str, keywords: list[str]) -> bool:
    """Potrivire pe cuvant intreg (nu substring), ca sa evitam false-pozitive
    de genul cuvantul cheie "dali" (DALI) gasit in brandul de cascaval "Dalia"."""
    norm = _normalize_ro(text)
    return any(re.search(rf"\b{re.escape(_normalize_ro(kw))}\b", norm) for kw in keywords)


def _match_relevant(cpv_and_name: str, title: str) -> tuple[bool, list[str]]:
    cpv_code = (cpv_and_name or "").split(" - ")[0].strip()
    cpv_match = any(code in cpv_code for code in CPV_CODES)
    keyword_match = _keyword_match(title or "", KEYWORDS) or _keyword_match(cpv_and_name or "", KEYWORDS)
    return (cpv_match or keyword_match), ([cpv_code] if cpv_code else [])


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _paginate(url: str, base_payload: dict) -> list[dict]:
    items: list[dict] = []
    page = 0
    while page < MAX_PAGES:
        payload = {**base_payload, "pageIndex": page, "pageSize": PAGE_SIZE}
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("searchTooLong"):
            print(f"  [avertisment] cautarea la {url} e prea larga (searchTooLong) - "
                  f"micsoreaza days_back sau intervalul de date")
        batch = data.get("items", [])
        items.extend(batch)
        total = data.get("total", 0)
        if not batch or len(items) >= total:
            break
        page += 1
    return items


def fetch_direct_acquisitions(days_back: int = 3) -> list[dict]:
    """Interogheaza achizitiile directe in bucati de maxim
    DIRECT_ACQUISITION_CHUNK_HOURS ore (vezi comentariul de la constanta),
    ca sa evitam plafonul de rezultate incomplete al API-ului."""
    url = f"{BASE_URL}/DirectAcquisitionCommon/GetDirectAcquisitionList/"
    range_end = datetime.now(timezone.utc)
    range_start = range_end - timedelta(days=days_back)

    seen_ids: set = set()
    items: list[dict] = []

    chunk_end = range_end
    while True:
        chunk_start = max(chunk_end - timedelta(hours=DIRECT_ACQUISITION_CHUNK_HOURS), range_start)
        payload = {
            "showOngoingDa": True,
            "sysDirectAcquisitionStateId": None,
            "finalizationDateStart": None,
            "finalizationDateEnd": None,
            "publicationDateStart": _iso(chunk_start),
            "publicationDateEnd": _iso(chunk_end),
            "directAcquisitionName": None,
            "cookieContext": None,
        }
        for item in _paginate(url, payload):
            item_id = item.get("directAcquisitionId")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            items.append(item)

        if chunk_start <= range_start:
            break
        chunk_end = chunk_start + timedelta(hours=DIRECT_ACQUISITION_OVERLAP_HOURS)

    return items


def fetch_participation_notices(days_back: int = 3) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    until = datetime.now(timezone.utc)
    payload = {
        "sysNoticeTypeIds": NOTICE_TYPE_IDS,
        "sortProperties": [],
        "hasUnansweredQuestions": False,
        "startPublicationDate": _iso(since),
        "endPublicationDate": _iso(until),
    }
    return _paginate(f"{BASE_URL}/NoticeCommon/GetCNoticeList/", payload)


def normalize_direct_acquisition(item: dict) -> dict | None:
    cpv_and_name = item.get("cpvCode") or ""
    title = item.get("directAcquisitionName") or ""
    matched, cpv_list = _match_relevant(cpv_and_name, title)
    if not matched:
        return None

    da_id = item.get("directAcquisitionId")
    return {
        "source": "SICAP (achizitie directa)",
        "id": item.get("uniqueIdentificationCode") or str(da_id),
        "title": title or "(fara descriere)",
        "authority": item.get("contractingAuthority") or "",
        "cpv": cpv_list,
        "published": item.get("publicationDate") or "",
        "deadline": item.get("supplierDecisionDeadline") or item.get("caDecisionDeadline") or "",
        "value": str(item.get("estimatedValueRon") or ""),
        "url": f"https://e-licitatie.ro/pub/direct-acquisition/view/{da_id}",
        "_da_id": da_id,
    }


def normalize_notice(item: dict) -> dict | None:
    if (item.get("sysProcedureState") or {}).get("id") != OPEN_PROCEDURE_STATE_ID:
        return None

    cpv_and_name = item.get("cpvCodeAndName") or ""
    title = item.get("contractTitle") or ""
    matched, cpv_list = _match_relevant(cpv_and_name, title)
    if not matched:
        return None

    notice_id = item.get("noticeId") or item.get("cNoticeId")
    procedure_id = item.get("procedureId")
    # Pagina de detaliu foloseste procedureId (verificat live), NU noticeId/cNoticeId -
    # acelea apartin altor tabele si pot coincide accidental cu ID-uri complet
    # nelegate. Fara procedureId (rar, dar posibil) trimitem catre cautarea
    # generala dupa numarul anuntului, ca sa nu link-uim gresit.
    if procedure_id:
        url = f"https://e-licitatie.ro/pub/procedure/view/{procedure_id}/"
    else:
        url = f"https://e-licitatie.ro/pub/notices/contract-notices/list/0/0?search={item.get('noticeNo', '')}"
    return {
        "source": "SICAP (anunt de participare)",
        "id": item.get("noticeNo") or str(notice_id),
        "title": title or "(fara descriere)",
        "authority": item.get("contractingAuthorityNameAndFN") or "",
        "cpv": cpv_list,
        "published": item.get("noticeStateDate") or "",
        "deadline": item.get("maxTenderReceiptDeadline") or item.get("minTenderReceiptDeadline") or "",
        "value": item.get("estimatedValueExport") or str(item.get("estimatedValueRon") or ""),
        "url": url,
        "_procedure_id": procedure_id,
    }


def fetch_direct_acquisition_detail(da_id: int) -> dict:
    """Descriere completa + reperele achizitionate (echivalentul 'cerintelor'
    pentru o achizitie directa - nu are criterii de evaluare, e cumparare simpla)."""
    resp = requests.get(f"{BASE_URL}/PublicDirectAcquisition/getView/{da_id}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    requirements = [
        {
            "name": it.get("catalogItemName") or "",
            "description": it.get("catalogItemDescription") or "",
        }
        for it in (data.get("directAcquisitionItems") or [])
    ]
    documents = [
        {"name": d.get("name") or "document", "url": d.get("url") or ""}
        for d in (data.get("documents") or [])
    ]
    return {
        "description": data.get("directAcquisitionDescription") or "",
        "requirements": requirements,
        "documents": documents,
    }


def fetch_procedure_detail(procedure_id: int) -> dict:
    """Termenul real de depunere (per lot) + criteriile de evaluare (cerintele
    specifice, cu descriere si algoritm de punctaj) + documentele atasate."""
    detail: dict = {"requirements": [], "documents": [], "deadline": None}

    try:
        resp = requests.post(f"{BASE_URL}/PUBLICProcedure/GetProcedureLots/{procedure_id}",
                              json={}, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        deadlines = [lot.get("offerDeadline") for lot in (resp.json().get("items") or []) if lot.get("offerDeadline")]
        if deadlines:
            detail["deadline"] = min(deadlines)
    except requests.RequestException as exc:
        print(f"  [avertisment] nu am putut lua loturile procedurii {procedure_id}: {exc}")

    try:
        resp = requests.get(
            f"{BASE_URL}/PUBLICProcedure/GetProcedureEvaluationCriterias/",
            params={"procedureId": procedure_id, "procedureLotId": "undefined"},
            headers=HEADERS, timeout=30,
        )
        resp.raise_for_status()
        detail["requirements"] = [
            {
                "name": c.get("procEvalCriteriaName") or "",
                "description": c.get("procEvalCriteriaDescription") or "",
                "weight": c.get("weight"),
            }
            for c in (resp.json().get("items") or [])
        ]
    except requests.RequestException as exc:
        print(f"  [avertisment] nu am putut lua criteriile procedurii {procedure_id}: {exc}")

    try:
        resp = requests.post(f"{BASE_URL}/NoticeDocument/GetAll/",
                              json={"procedureId": procedure_id}, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        detail["documents"] = [
            {"name": d.get("name") or "document", "url": d.get("url") or ""}
            for d in (resp.json().get("items") or [])
        ]
    except requests.RequestException as exc:
        print(f"  [avertisment] nu am putut lua documentele procedurii {procedure_id}: {exc}")

    return detail


def enrich_item(item: dict) -> dict:
    """Adauga descriere/cerinte/documente unui item deja normalizat, apeland
    API-ul de detaliu corespunzator sursei. Folosit doar pentru anunturile
    NOI (dupa deduplicare), ca sa nu multiplicam cererile inutil."""
    try:
        if item.get("_da_id"):
            detail = fetch_direct_acquisition_detail(item["_da_id"])
            return {**item, **detail}
        if item.get("_procedure_id"):
            detail = fetch_procedure_detail(item["_procedure_id"])
            enriched = {**item, "requirements": detail["requirements"], "documents": detail["documents"]}
            if detail.get("deadline"):
                enriched["deadline"] = detail["deadline"]
            return enriched
    except requests.RequestException as exc:
        print(f"  [avertisment] nu am putut lua detalii pentru {item.get('id')}: {exc}")
    return item


def fetch_relevant_items(days_back: int = 3) -> list[dict]:
    """Interogheaza ambele surse SICAP si intoarce doar liniile relevante
    (cod CPV din lista noastra SAU cuvinte cheie in titlu/CPV)."""
    results: list[dict] = []

    da_raw = fetch_direct_acquisitions(days_back=days_back)
    da_relevant = [normalize_direct_acquisition(item) for item in da_raw]
    da_relevant = [item for item in da_relevant if item]
    results.extend(da_relevant)
    print(f"[info] SICAP achizitii directe: {len(da_raw)} in fereastra, {len(da_relevant)} relevante")

    cn_raw = fetch_participation_notices(days_back=days_back)
    cn_relevant = [normalize_notice(item) for item in cn_raw]
    cn_relevant = [item for item in cn_relevant if item]
    results.extend(cn_relevant)
    print(f"[info] SICAP anunturi de participare: {len(cn_raw)} in fereastra, {len(cn_relevant)} relevante")

    return results
