# Radar licitatii publice - arhitectura / urbanism

Monitorizeaza automat licitatiile publice din Romania relevante pentru firma ta
(arhitectura, urbanism, inginerie, studii de fezabilitate, asistenta tehnica) si
trimite notificare pe Telegram cand apare ceva nou. Ruleaza gratuit pe GitHub Actions,
nu tine niciun calculator pornit.

## Surse de date

1. **TED (Tenders Electronic Daily)** - API public oficial al UE, fara autentificare.
   Acopera licitatiile **peste pragul UE** (aprox. 140.000-215.000 EUR pentru servicii).
2. **API-ul intern al platformei e-licitatie.ro (SICAP)** - acelasi API JSON pe care il
   foloseste chiar formularul de cautare de pe site. Nu e documentat oficial, dar e
   folosit public de site, fara autentificare si fara sa ocolim vreo protectie (nu e
   nevoie de CAPTCHA sau login - vezi `sicap_api.py` pentru detalii). Acopera:
   - **achizitiile directe** (cumparari sub prag, catalogul electronic)
   - **anunturile de participare** (CN) si **anunturile de participare simplificate**
     (SCN) - licitatiile propriu-zise, publicate inainte de atribuire, indiferent de
     valoare

Ambele surse ofera date in timp real (nu exporturi actualizate periodic), deci radarul
poate rula de 1-2 ori pe zi si tot prinde aproape orice aparut de la rularea anterioara.

Nu se foloseste niciun fel de scraping care ocoleste protectiile e-licitatie.ro.

## Configurare (o singura data, ~15 minute)

### 1. Pune codul intr-un repository GitHub

Daca nu ai deja cont GitHub, creeaza unul gratuit pe github.com. Apoi:

```bash
cd seap-radar
git init
git add .
git commit -m "Radar licitatii - setup initial"
git branch -M main
git remote add origin https://github.com/<user-ul-tau>/seap-radar.git
git push -u origin main
```

(Poti face asta si direct din interfata web GitHub: "New repository" -> "uploading an
existing file" -> tragi toate fisierele din acest folder.)

### 2. Creeaza un bot de Telegram (gratuit, 5 minute)

1. Deschide Telegram, cauta **@BotFather**.
2. Trimite-i `/newbot`, alege un nume si un username pentru bot.
3. Primesti un **token** (arata cam asa: `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).
   Pastreaza-l, ai nevoie de el la pasul 4.
4. Cauta botul tau nou-creat in Telegram si trimite-i orice mesaj (ex: "salut"), ca sa
   pornesti conversatia.
5. In browser, acceseaza (inlocuind `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   In raspunsul JSON cauta `"chat":{"id": 123456789, ...}` - acel numar e **chat_id**-ul tau.

### 3. Adauga secretele in GitHub

In repository-ul tau: **Settings -> Secrets and variables -> Actions -> New repository secret**

Adauga doua secrete:
- `TELEGRAM_BOT_TOKEN` = tokenul de la pasul 2.3
- `TELEGRAM_CHAT_ID` = numarul de la pasul 2.5

### 4. Testeaza manual

In tab-ul **Actions** al repository-ului, selecteaza workflow-ul "Radar licitatii" si
apasa **Run workflow** (buton manual, nu trebuie sa astepti programarea automata).
Verifica log-ul rularii ca sa vezi ce a gasit.

### 5. Gata

De acum, workflow-ul ruleaza singur de 3 ori pe zi (poti schimba frecventa in
`.github/workflows/radar.yml`, linia cu `cron`) si iti trimite pe Telegram doar
licitatiile noi si relevante.

## Personalizare

- **Coduri CPV / cuvinte cheie**: editeaza `config.py`.
- **Frecventa**: editeaza linia `cron` din `.github/workflows/radar.yml`
  ([crontab.guru](https://crontab.guru) te ajuta sa scrii expresia). O rulare de 1-2
  ori pe zi e suficienta - sursele sunt in timp real, nu exporturi periodice.
- **Cate zile in urma verifica**: parametrul `days_back` in `main.py` (implicit 3, ca sa
  nu rateze nimic daca o rulare pica).

## Testare locala (optional)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; pe Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Fara `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in mediu, scriptul doar afiseaza in consola
ce ar fi trimis, deci poti testa liber inainte sa configurezi Telegram.

## Verificat live (11.09.2026)

Codul a fost testat efectiv fata de API-urile reale, nu doar scris pe baza documentatiei
(TED nu are documentatie completa public, iar API-ul SICAP n-are deloc documentatie
oficiala - a fost reverse-engineerit prin inspectarea cererilor trimise chiar de site):

- **TED**: sintaxa de data initiala (`NOW-3DAY`) era respinsa de API (HTTP 400) -
  corectata la formatul acceptat `today(-N)`. Campurile `notice-title` si `buyer-name`
  vin ca obiecte multilingve (`{"ron": ["..."]}`), nu ca liste simple - `normalize()`
  extrage textul corect (preferand romana).
- **SICAP**: initial am incercat exportul CKAN de pe data.gov.ro (fisiere Excel/ODS de
  ~60MB, actualizate doar trimestrial) - functional, dar greoi si cu date invechite.
  L-am inlocuit cu API-ul intern al e-licitatie.ro, care da acces in timp real la
  aceleasi date plus la licitatiile mari (nu doar achizitii directe). Detalii tehnice:
  - Endpoint-urile (`DirectAcquisitionCommon/GetDirectAcquisitionList`,
    `NoticeCommon/GetCNoticeList`) resping cererile fara un header Referer/Origin
    ("Access Denied: Referrer cannot be null") - `sicap_api.py` trimite headere care
    imita un browser obisnuit.
  - Numele campurilor de filtrare pe data **difera** intre cele doua endpoint-uri:
    `publicationDateStart`/`publicationDateEnd` la achizitii directe, dar
    `startPublicationDate`/`endPublicationDate` la anunturi.
  - Achizitiile directe au un volum foarte mare la nivel de tara (mii/zi, toate
    categoriile) - peste ~1 zi in fereastra de cautare API-ul incepe sa dea rezultate
    plafonate/incomplete (`searchTooLong: true`). De-aia le interogam in bucati de
    maxim 20 de ore, cu suprapunere, indiferent cat de mare e `days_back`.
  - `sysNoticeTypeIds: [2, 17]` = anunt de participare (CN) + anunt de participare
    simplificat (SCN) - identificate live, nu din documentatie.
- **Filtrare cuvinte cheie**: potrivirea initiala pe substring facea ca certul cheie
  "dali" (DALI, un document tehnic) sa se potriveasca si cu brandul de cascaval
  "Dalia", aparut des in achizitiile de alimente - mii de rezultate false. Filtrarea
  foloseste acum potrivire pe cuvant intreg, cu normalizare de diacritice (unele
  seturi de date SEAP scriu "Achizitii", altele "Achiziții").

## Limitari cunoscute

- TED nu acopera achizitiile mici (sub pragul UE) - de aceea avem si sursa SICAP.
- API-ul SICAP nu e documentat oficial - daca site-ul e-licitatie.ro isi schimba
  structura interna, `sicap_api.py` se poate strica fara avertisment. Verifica periodic
  log-ul rularilor din GitHub Actions.
- Link-ul generat pentru anunturile de participare (`noticeId`) nu a putut fi verificat
  100% ca duce exact la pagina corecta a anuntului (ambiguitate intre `noticeId` si
  `cNoticeId` in raspunsul API-ului) - daca observi ca link-ul nu se potriveste cu
  anuntul, spune-mi si ajustez.
- Pentru achizitii foarte urgente/mici, publicate azi si care nu au ajuns inca in
  fereastra de interogare, tot merita o verificare manuala ocazionala pe e-licitatie.ro.
