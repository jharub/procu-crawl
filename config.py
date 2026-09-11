"""
Configurare radar licitatii - arhitectura / urbanism / inginerie.

Editeaza liber listele de mai jos ca sa restrangi sau sa extinzi aria de interes.
"""

# Coduri CPV relevante pentru arhitectura, urbanism, inginerie, studii de fezabilitate,
# asistenta tehnica. Sursa: Vocabularul comun privind achizitiile publice (CPV), Regulamentul UE.
CPV_CODES = {
    "71000000": "Servicii de arhitectura, de constructii, de inginerie si de inspectie",
    "71200000": "Servicii de arhitectura si servicii conexe",
    "71210000": "Servicii de consultanta in arhitectura",
    "71220000": "Servicii de proiectare arhitecturala",
    "71221000": "Servicii de arhitectura pentru constructii",
    "71222000": "Servicii de arhitectura pentru spatii exterioare",
    "71223000": "Servicii de arhitectura pentru extinderi de cladiri",
    "71240000": "Servicii de arhitectura, de inginerie si de planificare",
    "71241000": "Studii de fezabilitate, servicii de consultanta, analize",
    "71242000": "Elaborare de proiecte si proiectare, pregatire de santier si estimare a costurilor",
    "71244000": "Calcularea costurilor, monitorizarea costurilor",
    "71245000": "Planuri de aprobare, planuri de lucru si specificatii",
    "71246000": "Stabilirea si redactarea specificatiilor pentru perioada de constructie",
    "71247000": "Supravegherea lucrarilor de constructii",
    "71248000": "Supravegherea proiectului si documentatiei",
    "71250000": "Servicii de arhitectura, de inginerie si de masurare",
    "71251000": "Servicii de arhitectura si de masurare a cladirilor",
    "71300000": "Servicii de inginerie",
    "71320000": "Servicii de proiectare tehnica",
    "71321000": "Servicii de proiectare tehnica pentru instalatii mecanice si electrice",
    "71322000": "Servicii de proiectare tehnica pentru constructia de lucrari publice",
    "71322500": "Servicii de proiectare tehnica pentru infrastructuri de transport",
    "71319000": "Servicii de expertiza",
    "71313410": "Evaluare a riscurilor sau a pericolelor pentru constructii",
    "71354000": "Servicii de cartografiere",
    "71400000": "Servicii de urbanism",
    "71410000": "Servicii de urbanism (planificare urbana)",
    "71420000": "Servicii de arhitectura peisagistica",
}

# Cuvinte cheie folosite ca filtru suplimentar (case-insensitive) pentru descrierile
# care nu au cod CPV corect completat de autoritatea contractanta (se intampla des).
KEYWORDS = [
    "proiectare",
    "arhitectura",
    "arhitectural",
    "urbanism",
    "documentatie tehnico-economica",
    "studiu de fezabilitate",
    "dali",
    "d.a.l.i",  # unele anunturi scriu abrevierea punctata: "D.A.L.I."
    "documentatie de avizare a lucrarilor de interventie",  # DALI scris in clar
    "expertiza tehnica",
    "asistenta tehnica din partea proiectantului",
    "faza pt",
    "faza de",
    "certificat de urbanism",
    "plan urbanistic",
    # Nota: nu am adaugat "sf" simplu (abrevierea pentru "studiu de fezabilitate") -
    # e prea scurt si s-ar potrivi si cu "Sf." (Sfantu/Sfantul), foarte frecvent in
    # denumiri de biserici/monumente aflate in reparatie ("Biserica Sf. Nicolae" etc).
    # Folosim in schimb variantele compuse, sigure, care apar des in titluri reale:
    "actualizare sf",
    "elaborare sf",
    "faza sf",
]

# Tara pentru filtrul TED (Romania)
TED_BUYER_COUNTRY = "ROU"

# Daca vrei sa primesti pe Telegram doar achizitii directe si anunturi de participare
# (SICAP), nu si licitatiile mari de pe TED, pune False. TED ramane oricum colectat si
# vizibil pe pagina web (poti filtra dupa sursa acolo oricand) - doar notificarea pe
# Telegram e oprita, ca sa nu iti aglomereze conversatia cu oportunitati mai putin
# potrivite pentru o firma mica.
NOTIFY_TED_ON_TELEGRAM = False

# Fisierul in care se tine evidenta anunturilor deja notificate (nu trimitem de doua ori)
STATE_FILE = "state/seen.json"
