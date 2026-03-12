import streamlit as st
import datetime
import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import re
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="TH Taktinen Tutka", page_icon="🚕", layout="wide")

# ── 1. FUNKTIOT JA DATAN HAKU (Pidetään täällä, jotta ne ladataan vain kerran) ──

def laske_kysyntakerroin(wb_status, klo_str):
    """Sääntöpohjainen mikro-heuristiikka, joka laskee kysyntäindeksin."""
    indeksi = 2.0
    if wb_status:
        indeksi += 5.0
    try:
        tunnit = int(klo_str.split(":")[0])
        if tunnit >= 22 or tunnit <= 4:
            indeksi += 2.5
        elif 15 <= tunnit <= 18:
            indeksi += 1.5
    except:
        pass
    indeksi = min(indeksi, 10.0)
    
    if indeksi >= 7: return f"<span style='color:#ff4b4b; font-weight:bold;'>🔥 Kysyntä: {indeksi}/10</span>"
    elif indeksi >= 4: return f"<span style='color:#ffeb3b;'>⚡ Kysyntä: {indeksi}/10</span>"
    else: return f"<span style='color:#a3c2a3;'>Kysyntä: {indeksi}/10</span>"

@st.cache_data(ttl=86400)
def hae_juna_asemat():
    asemat = {
        "HKI": "Helsinki", "PSL": "Pasila", "TKL": "Tikkurila", "KRS": "Kerava", "JRV": "Järvenpää",
        "RHI": "Riihimäki", "HML": "Hämeenlinna", "TPE": "Tampere", "TKU": "Turku", "TKA": "Turku satama",
        "POR": "Pori", "VAA": "Vaasa", "SEI": "Seinäjoki", "YV": "Ylivieska", "KOK": "Kokkola",
        "OUL": "Oulu", "KEM": "Kemi", "ROV": "Rovaniemi", "KLI": "Kolari", "KJA": "Kajaani",
        "KUO": "Kuopio", "JNS": "Joensuu", "ILO": "Iisalmi", "MIK": "Mikkeli", "KV": "Kouvola",
        "LPR": "Lappeenranta", "IMR": "Imatra", "PMI": "Parikkala", "LH": "Lahti", "KTK": "Kotka",
        "VNA": "Vainikkala", "VKO": "Vainikkala", "MÄ": "Mäntsälä", "LAE": "Lappila", "MN": "Mäntyharju",
        "KAU": "Kauhava", "LAP": "Lapua", "VTI": "Vihanti", "YST": "Ylistaro", "KRN": "Karjaa"
    }
    try:
        url = "https://rata.digitraffic.fi/api/v1/metadata/stations"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        for s in resp.json(): asemat[s["stationShortCode"]] = s["stationName"].replace(" asema", "")
    except Exception: pass
    return asemat

@st.cache_data(ttl=600)
def get_averio_ships():
    url = "https://averio.fi/laivat"
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "fi-FI,fi;q=0.9"}
    laivat = []
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for taulu in soup.find_all("table"):
            for rivi in taulu.find_all("tr"):
                solut = [td.get_text(strip=True) for td in rivi.find_all(["td", "th"])]
                if len(solut) < 3: continue
                rivi_teksti = " ".join(solut).lower()
                if any(h in rivi_teksti for h in ["alus", "laiva", "ship", "vessel"]): continue
                pax = None
                for solu in solut:
                    puhdas = re.sub(r"[^\d]", "", solu)
                    if puhdas and 50 <= int(puhdas) <= 9999:
                        pax = int(puhdas)
                        break
                nimi_kandidaatit = [s for s in solut if re.search(r"[A-Za-zÀ-ÿ]{3,}", s)]
                if not nimi_kandidaatit: continue
                nimi = max(nimi_kandidaatit, key=len)
                laivat.append({
                    "ship": nimi,
                    "terminal": _tunnista_terminaali(rivi_teksti),
                    "time": _etsi_aika(solut),
                    "pax": pax,
                })
        return laivat[:5] if laivat else [{"ship": "Averio: HTML-rakenne muuttunut", "terminal": "Tarkista", "time": "-", "pax": None}]
    except Exception as e: return [{"ship": f"Averio-virhe: {e}", "terminal": "-", "time": "-", "pax": None}]

def _tunnista_terminaali(teksti):
    if "t2" in teksti or "lansisatama" in teksti or "länsisatama" in teksti: return "Länsisatama T2"
    if "t1" in teksti or "olympia" in teksti: return "Olympia T1"
    if "katajanokka" in teksti: return "Katajanokka"
    if "vuosaari" in teksti: return "Vuosaari (rahti)"
    return "Tarkista"

def _etsi_aika(osat):
    for osa in osat:
        m = re.search(r"\b([0-2]?\d:[0-5]\d)\b", str(osa))
        if m: return m.group(1)
    return "-"

def _pax_arvio(pax):
    if pax is None: return "Ei tietoa", "pax-ok"
    autoa = round(pax * 0.025)
    if pax >= 1500: return f"🔥 {pax} matkustajaa (~{autoa} autoa, HYVÄ)", "pax-good"
    if pax >= 800: return f"✅ {pax} matkustajaa (~{autoa} autoa, NORMAALI)", "pax-ok"
    return f"⬇️ {pax} matkustajaa (~{autoa} autoa, HILJAINEN)", "pax-ok"

@st.cache_data(ttl=600)
def get_port_schedule():
    url = "https://www.portofhelsinki.fi/matkustajille/matkustajatietoa/lahtevat-ja-saapuvat-matkustajalaivat/#tabs-2"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        lista = []
        for rivi in soup.find_all("tr"):
            solut = rivi.find_all("td")
            if len(solut) >= 4:
                aika = solut[0].get_text(strip=True)
                laiva = solut[1].get_text(strip=True)
                terminaali = solut[3].get_text(strip=True) if len(solut) > 3 else "?"
                if aika and laiva and re.match(r"\d{1,2}:\d{2}", aika):
                    lista.append({"time": aika, "ship": laiva, "terminal": terminaali})
        return lista[:6] if lista else []
    except Exception: return []

@st.cache_data(ttl=50)
def get_trains(asema_nimi):
    nykyhetki = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
    koodit = {"Helsinki": "HKI", "Pasila": "PSL", "Tikkurila": "TKL"}
    koodi = koodit.get(asema_nimi, "HKI")
    url = f"https://rata.digitraffic.fi/api/v1/live-trains/station/{koodi}?arrived_trains=0&arriving_trains=25&train_categories=Long-distance"
    asemat_dict = hae_juna_asemat()
    tulos = []
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for juna in data:
            if juna.get("cancelled"): continue
            tyyppi = juna.get("trainType", "")
            numero = juna.get("trainNumber", "")
            nimi = f"{tyyppi} {numero}"
            lahto_koodi = None
            for rivi in juna["timeTableRows"]:
                if rivi["type"] == "DEPARTURE":
                    lahto_koodi = rivi["stationShortCode"]
                    break
            if not lahto_koodi: lahto_koodi = juna["timeTableRows"][0]["stationShortCode"]
            if lahto_koodi in ("HKI", "PSL", "TKL", "ILA", "KRS"): continue
            lahto_kaupunki = asemat_dict.get(lahto_koodi, lahto_koodi)

            aika_obj = aika_str = None
            viive = 0
            for rivi in juna["timeTableRows"]:
                if rivi["stationShortCode"] == koodi and rivi["type"] == "ARRIVAL":
                    raaka = rivi.get("liveEstimateTime") or rivi.get("scheduledTime", "")
                    try:
                        aika_obj = datetime.datetime.strptime(raaka[:16], "%Y-%m-%dT%H:%M")
                        aika_obj = aika_obj.replace(tzinfo=datetime.timezone.utc).astimezone(ZoneInfo("Europe/Helsinki"))
                        if aika_obj < nykyhetki - datetime.timedelta(minutes=3): continue
                        aika_str = aika_obj.strftime("%H:%M")
                    except Exception: pass
                    viive = rivi.get("differenceInMinutes", 0)
                    break
            if aika_str and aika_obj: tulos.append({"train": nimi, "origin": lahto_kaupunki, "time": aika_str, "dt": aika_obj, "delay": viive if viive and viive > 0 else 0})
        tulos.sort(key=lambda k: k["dt"])
        return tulos[:6]
    except Exception as e: return [{"train": "API-virhe", "origin": str(e)[:40], "time": "-", "dt": None, "delay": 0}]

@st.cache_data(ttl=60)
def get_flights():
    laajarunko = {"359", "350", "333", "330", "340", "788", "789", "777", "77W", "388", "744", "74H"}
    FINAVIA_API_KEY = st.secrets.get("FINAVIA_API_KEY", "")
    endpoints = [
        (f"https://apigw.finavia.fi/flights/public/v0/flights/arr/HEL?subscription-key={FINAVIA_API_KEY}", {}),
        ("https://apigw.finavia.fi/flights/public/v0/flights/arr/HEL", {"Ocp-Apim-Subscription-Key": FINAVIA_API_KEY}),
    ]
    for url, extra_headers in endpoints:
        hdrs = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"}
        hdrs.update(extra_headers)
        try:
            resp = requests.get(url, headers=hdrs, timeout=10)
            if resp.status_code in (401, 403): continue
            resp.raise_for_status()
            data = resp.json()
            saapuvat = []
            if isinstance(data, list): saapuvat = data
            elif isinstance(data, dict):
                for avain in ("arr", "flights", "body"):
                    k = data.get(avain)
                    if isinstance(k, list):
                        saapuvat = k
                        break
                if not saapuvat and isinstance(data.get("body"), dict):
                    for ala in ("arr", "flight"):
                        if isinstance(data["body"].get(ala), list):
                            saapuvat = data["body"][ala]
                            break
            if not saapuvat: continue
            tulos = []
            for lento in saapuvat:
                nro    = lento.get("fltnr") or lento.get("flightNumber", "??")
                kohde  = lento.get("route_n_1") or lento.get("airport", "Tuntematon")
                aika_r = str(lento.get("sdt") or lento.get("scheduledTime", ""))
                actype = str(lento.get("actype") or lento.get("aircraftType", ""))
                status = str(lento.get("prt_f") or lento.get("statusInfo", "Odottaa"))
                aika   = aika_r[11:16] if "T" in aika_r else aika_r[:5]
                wb     = any(c in actype for c in laajarunko)
                tyyppi = f"Laajarunko (✈ {actype})" if wb else f"Kapearunko ({actype})"
                if wb and "laskeutunut" not in status.lower() and "landed" not in status.lower():
                    status = f"🔥 Odottaa massapurkua – {status}"
                elif "delay" in status.lower() or "myohassa" in status.lower(): status = f"🔴 {status}"
                tulos.append({"flight": nro, "origin": kohde, "time": aika, "type": tyyppi, "wb": wb, "status": status})
            tulos.sort(key=lambda x: (not x["wb"], x["time"]))
            return tulos[:8], None
        except Exception: continue
    return [], "Finavia API ei vastannut."

@st.cache_data(ttl=3600)
def get_culture_live_events():
    live_tapahtumat = {}
    try:
        now = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
        start_date = now.replace(hour=0, minute=0, second=0).isoformat()
        url = f"https://linkedevents.api.hel.fi/v1/event/?start={start_date}&include=location"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        for e in data:
            nimi = e.get("name", {}).get("fi", "Tuntematon esitys")
            loc = e.get("location", {})
            paikka_nimi = (loc.get("name", {}).get("fi") or "").lower()
            end_time_str = e.get("end_time")
            if not end_time_str or not paikka_nimi: continue
            try:
                end_dt = datetime.datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Helsinki"))
                if end_dt > now and end_dt.date() == now.date():
                    if paikka_nimi not in live_tapahtumat: live_tapahtumat[paikka_nimi] = []
                    live_tapahtumat[paikka_nimi].append(f"{nimi} ({end_dt.strftime('%H:%M')})")
            except Exception: pass
    except Exception: pass
    return live_tapahtumat

def yhdista_kulttuuridata(paikat):
    live_data = get_culture_live_events()
    for p in paikat:
        hakusanat = p.get("hakusanat", [])
        loydetty_live = False
        for api_paikka, tapahtumat in live_data.items():
            if any(sana in api_paikka for sana in hakusanat):
                esitykset_str = " | ".join(tapahtumat)
                p["lopetus_html"] = f"<span class='live-event'>🟢 LIVE TÄNÄÄN: {esitykset_str}</span>"
                loydetty_live = True
                break
        if not loydetty_live:
            if hakusanat: p["lopetus_html"] = f"<span class='no-event'>⚪ Ei julkista esitystä tänään.</span><br><span style='color:#777;'>Tyypillisesti: {p['lopetus']}</span>"
            else: p["lopetus_html"] = f"<span class='endtime'>⏱ Tyypillinen lopetus: {p['lopetus']}</span>"
    return paikat

@st.cache_data(ttl=3600)
def get_general_live_events():
    tulos = []
    try:
        now = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
        url = "https://linkedevents.api.hel.fi/v1/event/?start=now&sort=end_time&include=location"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        for e in data:
            nimi = e.get("name", {}).get("fi", "Tuntematon tapahtuma")
            end_time_str = e.get("end_time")
            if not end_time_str: continue
            try:
                end_dt = datetime.datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Helsinki"))
                if end_dt > now and end_dt.date() == now.date() and end_dt.hour >= 16:
                    loc = e.get("location", {})
                    osoite = loc.get("name", {}).get("fi") or loc.get("street_address", {}).get("fi") or "Helsinki"
                    tulos.append({"nimi": nimi, "loppu": end_dt.strftime("%H:%M"), "paikka": osoite, "dt": end_dt})
            except Exception: pass
        tulos.sort(key=lambda x: x["dt"])
        return tulos[:10]
    except Exception: return []

def viive_badge(minuutit):
    if minuutit <= 0: return "<span class='badge-green'>Aikataulussa</span>"
    if minuutit < 15: return f"<span class='badge-yellow'>+{minuutit} min</span>"
    if minuutit < 60: return f"<span class='badge-red'>⚠ +{minuutit} min</span>"
    return f"<span class='badge-red'>🚨 +{minuutit} min – VR-korvaus!</span>"

def tallenna_arvostelu(arvosana):
    """Tässä vaiheessa tulostaa konsoliin. Myöhemmin voidaan kytkeä tietokantaan."""
    print(f"[{datetime.datetime.now()}] Vuoron arvosana tallennettu: {arvosana}")
    # TODO: Lisää tietokantatallennus (esim. Firebase / Supabase) myöhemmin

# ── 2. TILANHALLINTA (STATE MACHINE) ─────────────────────────────────────────

if "page_state" not in st.session_state:
    st.session_state.page_state = "START"

if "valittu_asema" not in st.session_state:
    st.session_state.valittu_asema = "Helsinki"

# ── TILA 1: ALOITUSNÄKYMÄ ──
if st.session_state.page_state == "START":
    st.markdown("<br><br><h1 style='text-align: center; color: #5bc0de; font-size: 50px;'>🚕 TH Taktinen Tutka</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaa; font-size: 20px;'>Ennakoiva liikkuvuuden hallinta Helsinki 2026</p><br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🟢 Aloita vuoro", use_container_width=True, type="primary"):
            st.session_state.page_state = "LOGIN"
            st.rerun()

# ── TILA 2: KIRJAUTUMINEN ──
elif st.session_state.page_state == "LOGIN":
    st.markdown("<br><br><h2 style='text-align: center; color: #ffffff;'>🔒 Turvatarkastus</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        pwd = st.text_input("Syötä salakoodi", type="password")
        if st.button("Kirjaudu", use_container_width=True):
            if pwd == st.secrets.get("APP_PASSWORD", "2026"):
                st.session_state.page_state = "DASHBOARD"
                st.rerun()
            else:
                st.error("Väärä salasana.")
        if st.button("Takaisin", use_container_width=True):
            st.session_state.page_state = "START"
            st.rerun()

# ── TILA 4: ARVOSTELU (Lopeta vuoro) ──
elif st.session_state.page_state == "RATING":
    st.markdown("<br><br><h1 style='text-align: center; color: #ffeb3b;'>Miten vuoro meni?</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #e0e0e0; font-size: 20px;'>Anna arvostelusi, se auttaa kehittämään tekoälyä ja tutkaa!</p><br>", unsafe_allow_html=True)
    
    c1, c2, c3, c4, c5 = st.columns(5)
    
    # Napit ja niiden toiminta
    if c1.button("🤬 Ihan paska!", use_container_width=True): 
        tallenna_arvostelu("Ihan paska!")
        st.session_state.page_state = "THANKS"
        st.rerun()
    if c2.button("🙁 Huono", use_container_width=True): 
        tallenna_arvostelu("Huono")
        st.session_state.page_state = "THANKS"
        st.rerun()
    if c3.button("😐 Normivuoro", use_container_width=True): 
        tallenna_arvostelu("Normivuoro")
        st.session_state.page_state = "THANKS"
        st.rerun()
    if c4.button("🙂 Hyvä", use_container_width=True): 
        tallenna_arvostelu("Hyvä")
        st.session_state.page_state = "THANKS"
        st.rerun()
    if c5.button("🤩 Ihan vitun hyvä!", use_container_width=True): 
        tallenna_arvostelu("Ihan vitun hyvä!")
        st.session_state.page_state = "THANKS"
        st.rerun()

# ── TILA 5: KIITOS JA LOPETUS ──
elif st.session_state.page_state == "THANKS":
    st.markdown("<br><br><h1 style='text-align: center; color: #88d888;'>✅ Kiitos palautteesta!</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaa; font-size: 18px;'>Arviosi on tallennettu analyysiä varten. Turvallista kotimatkaa ja lepoa.</p><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Palaa etusivulle", use_container_width=True):
            st.session_state.page_state = "START"
            st.rerun()

# ── TILA 3: PÄÄSOVELLUS (DASHBOARD) ──
elif st.session_state.page_state == "DASHBOARD":
    
    # Taustapäivitys vain kun dashboard on auki
    st_autorefresh(interval=300000, key="datan_paivitys")

    st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    .main { background-color: #121212; }
    .header-container { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #333; padding-bottom: 15px; margin-bottom: 20px; }
    .app-title { font-size: 32px; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
    .time-display { font-size: 38px; font-weight: bold; color: #e0e0e0; line-height: 1; }
    .taksi-card { background-color: #1e1e2a; color: #e0e0e0; padding: 22px; border-radius: 12px; margin-bottom: 20px; font-size: 20px; border: 1px solid #3a3a50; box-shadow: 0 4px 8px rgba(0,0,0,0.3); line-height: 1.7; }
    .card-title { font-size: 24px; font-weight: bold; margin-bottom: 12px; color: #ffffff; border-bottom: 2px solid #444; padding-bottom: 8px; }
    .taksi-link { color: #5bc0de; text-decoration: none; font-size: 18px; display: inline-block; margin-top: 12px; font-weight: bold; }
    .badge-red { background:#7a1a1a; color:#ff9999; padding:2px 8px; border-radius:4px; font-size:16px; font-weight:bold; }
    .badge-yellow { background:#5a4a00; color:#ffeb3b; padding:2px 8px; border-radius:4px; font-size:16px; font-weight:bold; }
    .badge-green { background:#1a4a1a; color:#88d888; padding:2px 8px; border-radius:4px; font-size:16px; font-weight:bold; }
    .badge-blue { background:#1a2a5a; color:#8ab4f8; padding:2px 8px; border-radius:4px; font-size:16px; font-weight:bold; }
    .sold-out { color: #ff4b4b; font-weight: bold; }
    .pax-good { color: #ffeb3b; font-weight: bold; }
    .pax-ok { color: #a3c2a3; }
    .delay-bad { color: #ff9999; font-weight: bold; }
    .on-time { color: #88d888; }
    .section-header { color: #e0e0e0; font-size: 24px; font-weight: bold; margin-top: 28px; margin-bottom: 10px; border-left: 4px solid #5bc0de; padding-left: 12px; }
    .venue-name { color: #ffffff; font-weight: bold; }
    .venue-address { color: #aaaaaa; font-size: 16px; }
    .endtime { color: #ffeb3b; font-size: 15px; font-weight: bold; }
    .eventline { border-left: 3px solid #333; padding-left: 12px; margin-bottom: 16px; }
    .live-event { color: #88d888; font-weight: bold; }
    .no-event { color: #888888; font-style: italic; }
    </style>
    """, unsafe_allow_html=True)

    suomen_aika = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
    klo   = suomen_aika.strftime("%H:%M")
    paiva = suomen_aika.strftime("%a %d.%m.%Y").capitalize()

    HSL_LINKKI = "https://www.hsl.fi/matkustaminen/liikenne?language=fi&page=1&validityPeriod=true&transportMode=1&transportMode=2&transportMode=4&transportMode=3&transportMode=5&transportMode=6&favouritesOnly=false"

    # Yläpalkki ja LOPETA VUORO -nappi
    c_left, c_right = st.columns([3, 1])
    with c_left:
        st.markdown(f"<div class='app-title'>🚕 TH Taktinen Tutka</div><div class='time-display'>{klo} <span style='font-size:16px;color:#888;'>Helsinki – {paiva}</span></div>", unsafe_allow_html=True)
    with c_right:
        st.write("") # Tasaus
        if st.button("🛑 Lopeta vuoro", use_container_width=True):
            st.session_state.page_state = "RATING"
            st.rerun()

    st.markdown("<hr style='border-color:#333;'>", unsafe_allow_html=True)

    # ── LOHKO 1: JUNAT ──
    st.markdown("<div class='section-header'>🚆 SAAPUVAT KAUKOJUNAT</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    if c1.button("Helsinki (HKI)", use_container_width=True): st.session_state.valittu_asema = "Helsinki"
    if c2.button("Pasila (PSL)", use_container_width=True): st.session_state.valittu_asema = "Pasila"
    if c3.button("Tikkurila (TKL)", use_container_width=True): st.session_state.valittu_asema = "Tikkurila"

    valittu = st.session_state.valittu_asema
    junat = get_trains(valittu)
    vr_linkit = {
        "Helsinki": "https://www.vr.fi/radalla?station=HKI&direction=ARRIVAL&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D&follow=true",
        "Pasila": "https://www.vr.fi/radalla?station=PSL&direction=ARRIVAL&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D",
        "Tikkurila": "https://www.vr.fi/radalla?station=TKL&direction=ARRIVAL&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D&follow=true",
    }
    TAHTI_ASEMAT = {"Rovaniemi", "Kolari", "Kemi", "Oulu", "Kajaani", "Kuopio", "Joensuu", "Iisalmi", "Ylivieska"}

    juna_html = f"<span style='color:#aaa;font-size:17px;'>Asema: <b>{valittu}</b> – vain kaukoliikenne</span><br><br>"
    if junat and junat[0]["train"] != "API-virhe":
        for j in junat:
            tahti = " ⭐" if j["origin"] in TAHTI_ASEMAT else ""
            juna_html += f"<b>{j['time']}</b>  ·  {j['train']} <span style='color:#aaa;'>(lähtö: {j['origin']}{tahti})</span><br>  └ {viive_badge(j['delay'])}<br><br>"
        if any(j["delay"] >= 60 for j in junat): juna_html += "<br><span class='badge-red'>🚨 Yli 60 min myöhässä – tarkista VR-korvauskäytäntö!</span><br>"
    else: juna_html += "Ei saapuvia kaukojunia lähiaikoina."

    st.markdown(f"<div class='taksi-card'>{juna_html}<a href='{vr_linkit[valittu]}' class='taksi-link' target='_blank'>VR Live ({valittu}) &#x2192;</a></div>", unsafe_allow_html=True)

    # ── LOHKO 2: LAIVAT ──
    st.markdown("<div class='section-header'>🚢 MATKUSTAJALAIVAT</div>", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        averio_laivat = get_averio_ships()
        averio_html = "<div class='card-title'>Averio – Matkustajamäärät</div><span style='color:#aaa;font-size:15px;'>⚠ klo 00:30 MS Finlandia → <b>Länsisatama T2</b></span><br><br>"
        for laiva in averio_laivat:
            arvio_teksti, arvio_css = _pax_arvio(laiva["pax"])
            averio_html += f"<b>{laiva['time']}</b>  ·  {laiva['ship']}<br>  └ Terminaali: {laiva['terminal']}<br>  └ <span class='{arvio_css}'>{arvio_teksti}</span><br><br>"
        st.markdown(f"<div class='taksi-card'>{averio_html}<a href='https://averio.fi/laivat' class='taksi-link' target='_blank'>Avaa Averio →</a></div>", unsafe_allow_html=True)
    with col_b:
        port_laivat = get_port_schedule()
        port_html = "<div class='card-title'>Helsingin Satama – Aikataulu</div><span style='color:#aaa;font-size:15px;'>Virallinen saapumisaika</span><br><br>"
        if port_laivat:
            for laiva in port_laivat: port_html += f"<b>{laiva['time']}</b>  ·  {laiva['ship']}<br>  └ {laiva['terminal']}<br><br>"
        else: port_html += "Ei dataa – sivu vaatii JavaScript-renderöinnin.<br>"
        st.markdown(f"<div class='taksi-card'>{port_html}<a href='https://www.portofhelsinki.fi/matkustajille/matkustajatietoa/lahtevat-ja-saapuvat-matkustajalaivat/#tabs-2' class='taksi-link' target='_blank'>Helsingin Satama →</a></div>", unsafe_allow_html=True)

    # ── LOHKO 3: LENNOT ──
    st.markdown("<div class='section-header'>✈️ LENTOKENTTÄ (Helsinki-Vantaa)</div>", unsafe_allow_html=True)
    lennot, lento_virhe = get_flights()
    if lento_virhe: st.markdown(f"<div class='taksi-card'><div class='card-title'>Finavia API</div><span style='color:#ff9999;'>⚠ {lento_virhe}</span></div>", unsafe_allow_html=True)
    else:
        lento_html = "<div class='card-title'>Taktiset poiminnat – saapuvat</div><span style='color:#aaa;font-size:15px;'>Frankfurt arki-iltaisin = paras business-lento | Sähköautoilla tolppaetuoikeus</span><br><br>"
        for lento in lennot:
            tyyppi_css = "pax-good" if lento["wb"] else "pax-ok"
            kysynta_arvio = laske_kysyntakerroin(lento["wb"], lento["time"])
            lento_html += f"<b>{lento['time']}</b>  ·  {lento['origin']} <span style='color:#aaa;'>({lento['flight']})</span><br>  └ <span class='{tyyppi_css}'>{lento['type']}</span> | {lento['status']}<br>  └ {kysynta_arvio}<br><br>"
        st.markdown(f"<div class='taksi-card'>{lento_html}<a href='https://www.finavia.fi/fi/lentoasemat/helsinki
