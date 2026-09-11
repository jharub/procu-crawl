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

  - AdvNoticeCommon/GetAdvNoticeList - anunturi de intentie pentru achizitii
    directe ("Publicitate anunturi" in meniul site-ului): publicate INAINTE
    ca achizitia sa apara in catalogul electronic, cu caiet de sarcini/
    documentatie atasata, conditii de participare si termen de depunere.
    Initial am folosit DirectAcquisitionCommon/GetDirectAcquisitionList
    (catalogul electronic propriu-zis), dar pana ajunge acolo o achizitie e
    adesea deja decisa - anuntul de intentie e stadiul la care chiar mai poti
    aplica.
  - NoticeCommon/GetCNoticeList - anunturi de participare (CN) si anunturi de
    participare simplificate (SCN): licitatiile propriu-zise, publicate
    INAINTE de atribuire - nu anunturile de atribuire/rezultat.

Ambele accepta un interval pe data publicarii, ceea ce ne permite sa cerem
"ultimele N zile" in loc sa descarcam un export intreg pe an. Atentie: numele
campurilor de data DIFERA intre servicii (nu e o greseala aici, asa raspunde
API-ul):
  - AdvNoticeCommon foloseste publicationDateStart / publicationDateEnd
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

# Diacritice romanesti -> ASCII, ca sa comparam text indiferent daca sursa
# foloseste sau nu diacritice corecte (SEAP e inconsistent intre seturi de date).
_DIACRITICS = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaisstt" "AAISSTT")


def _normalize_ro(text: str) -> str:
    return text.translate(_DIACRITICS).lower()


def _matched_keywords(text: str, keywords: list[str]) -> list[str]:
    """Potrivire pe cuvant intreg (nu substring), ca sa evitam false-pozitive
    de genul cuvantul cheie "dali" (DALI) gasit in brandul de cascaval "Dalia"."""
    norm = _normalize_ro(text)
    return [kw for kw in keywords if re.search(rf"\b{re.escape(_normalize_ro(kw))}\b", norm)]


def _match_relevant(cpv_and_name: str, title: str) -> tuple[bool, list[str], dict]:
    """Intoarce (e_relevant, cpv_gasit_in_anunt, motivul_potrivirii). Motivul
    arata explicit daca anuntul a fost prins prin cod CPV din lista noastra,
    prin cuvant cheie, sau ambele - util pe pagina web, pentru ca des se
    intampla ca autoritatea sa completeze CPV-ul gresit si anuntul sa fie
    relevant doar datorita textului."""
    cpv_code = (cpv_and_name or "").split(" - ")[0].strip()
    matched_cpv_codes = [code for code in CPV_CODES if code in cpv_code]
    kw_from_title = _matched_keywords(title or "", KEYWORDS)
    kw_from_cpv_name = _matched_keywords(cpv_and_name or "", KEYWORDS)
    matched_keywords = list(dict.fromkeys(kw_from_title + kw_from_cpv_name))

    match_reason = {"cpv": matched_cpv_codes, "keywords": matched_keywords}
    matched = bool(matched_cpv_codes) or bool(matched_keywords)
    return matched, ([cpv_code] if cpv_code else []), match_reason


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


def fetch_adv_notices(days_back: int = 3) -> list[dict]:
    """Anunturi de intentie pentru achizitii directe. Verificat live: spre
    deosebire de DirectAcquisitionCommon, aceasta sursa NU are plafon de
    rezultate incomplete la ferestre de cateva zile (testat pana la 7 zile
    fara searchTooLong), deci nu are nevoie de interogare in bucati."""
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    until = datetime.now(timezone.utc)
    payload = {
        "publicationDateStart": _iso(since),
        "publicationDateEnd": _iso(until),
    }
    return _paginate(f"{BASE_URL}/AdvNoticeCommon/GetAdvNoticeList/", payload)


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


def normalize_adv_notice(item: dict) -> dict | None:
    cpv_and_name = item.get("cpvCode") or ""
    title = item.get("contractObject") or ""
    matched, cpv_list, match_reason = _match_relevant(cpv_and_name, title)
    if not matched:
        return None

    adv_id = item.get("advNoticeId")
    return {
        "source": "SICAP (achizitie directa)",
        "id": item.get("noticeNo") or str(adv_id),
        "title": title or "(fara descriere)",
        "authority": item.get("contractingAuthority") or "",
        "cpv": cpv_list,
        "published": item.get("publicationDate") or "",
        "deadline": item.get("tenderReceiptDeadline") or "",
        "value": str(item.get("estimatedValue") or ""),
        "url": f"https://e-licitatie.ro/pub/notices/adv-notices/view/{adv_id}",
        "match_reason": match_reason,
        "_adv_notice_id": adv_id,
    }


def normalize_notice(item: dict) -> dict | None:
    if (item.get("sysProcedureState") or {}).get("id") != OPEN_PROCEDURE_STATE_ID:
        return None

    cpv_and_name = item.get("cpvCodeAndName") or ""
    title = item.get("contractTitle") or ""
    matched, cpv_list, match_reason = _match_relevant(cpv_and_name, title)
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
        "match_reason": match_reason,
        "_procedure_id": procedure_id,
    }


def fetch_adv_notice_detail(adv_notice_id: int) -> dict:
    """Descriere completa, conditii de participare/contractuale, criteriul de
    atribuire si documentul atasat (caiet de sarcini) al unui anunt de intentie."""
    resp = requests.get(f"{BASE_URL}/PUBLICAdvNotice/getForView/{adv_notice_id}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    requirements = []
    if data.get("participationConditions"):
        requirements.append({"name": "Conditii de participare", "description": data["participationConditions"]})
    if data.get("contractRelatedConditions"):
        requirements.append({"name": "Conditii contractuale", "description": data["contractRelatedConditions"]})
    if data.get("awardCriteria"):
        requirements.append({"name": "Criteriul de atribuire", "description": data["awardCriteria"]})

    # Nota: linkul direct catre fisier (data["documentUrl"]) NU functioneaza fara
    # sesiunea de browser care il genereaza (POST+GET legate, verificat live -
    # un GET simplu, chiar cu Referer/cookie corecte, da eroare "fisierul nu se
    # regaseste pe server"). Trimitem in schimb catre pagina anuntului, unde
    # documentul chiar se poate descarca din click-ul propriu al site-ului.
    documents = []
    if data.get("documentName"):
        documents.append({
            "name": data["documentName"],
            "url": f"https://e-licitatie.ro/pub/notices/adv-notices/view/{adv_notice_id}",
        })

    return {
        "description": data.get("contractDescription") or "",
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
        if item.get("_adv_notice_id"):
            detail = fetch_adv_notice_detail(item["_adv_notice_id"])
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

    adv_raw = fetch_adv_notices(days_back=days_back)
    adv_relevant = [normalize_adv_notice(item) for item in adv_raw]
    adv_relevant = [item for item in adv_relevant if item]
    results.extend(adv_relevant)
    print(f"[info] SICAP achizitii directe (anunturi de intentie): {len(adv_raw)} in fereastra, {len(adv_relevant)} relevante")

    cn_raw = fetch_participation_notices(days_back=days_back)
    cn_relevant = [normalize_notice(item) for item in cn_raw]
    cn_relevant = [item for item in cn_relevant if item]
    results.extend(cn_relevant)
    print(f"[info] SICAP anunturi de participare: {len(cn_raw)} in fereastra, {len(cn_relevant)} relevante")

    return results
