#!/usr/bin/env python3

import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Konfigurasi Dasar
BASE_URL = "https://sharkstreams.net"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": BASE_URL + "/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

VLC_OUTPUT = "Sharkstreams_VLC.m3u8"
TIVIMATE_OUTPUT = "Sharkstreams_TiviMate.m3u8"

# Dictionary Logo
TV_INFO = {
    "soccer": ("Soccer.Dummy.us", "https://i.postimg.cc/HsWHFvV0/Soccer.png", "Soccer"),
    "mlb": ("MLB.Baseball.Dummy.us", "https://i.postimg.cc/FsFmwC7K/Baseball3.png", "MLB"),
    "nba": ("NBA.Basketball.Dummy.us", "https://i.postimg.cc/jdqKB3LW/Basketball-2.png", "NBA"),
    "nfl": ("Football.Dummy.us", "https://i.postimg.cc/tRNpSGCq/Maxx.png", "NFL"),
    "nhl": ("NHL.Hockey.Dummy.us", "https://i.postimg.cc/mgMRQ7FR/nhl-logo-png-seeklogo-534236.png", "NHL"),
    "fighting": ("PPV.EVENTS.Dummy.us", "https://i.postimg.cc/8c4GjMnH/Combat-Sports.png", "Combat Sports"),
    "motorsports": ("Racing.Dummy.us", "https://i.postimg.cc/yY6B2pkv/F1.png", "Motorsports"),
    "ufc": ("UFC.Fight.Pass.Dummy.us", "https://i.postimg.cc/59Sb7W9D/Combat-Sports2.png", "UFC"),
    "ppv": ("PPV.EVENTS.Dummy.us", "https://i.postimg.cc/mkj4tC62/PPV.png", "PPV"),
    "wwe": ("PPV.EVENTS.Dummy.us", "https://i.postimg.cc/wTxHn47J/WWE2.png", "WWE"),
    "misc": ("Sports.Dummy.us", "https://i.postimg.cc/qMm0rc3L/247.png", "Random Events"),
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def get_tv_data(sport_name):
    key = sport_name.lower().strip()
    if key in TV_INFO: return TV_INFO[key]
    for k in TV_INFO:
        if k in key: return TV_INFO[k]
    return TV_INFO["misc"]

def get_shark_events():
    """Mengambil daftar jadwal dari halaman utama Sharkstreams."""
    print(f"Mengambil jadwal dari {BASE_URL}...")
    try:
        r = SESSION.get(BASE_URL, timeout=15)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"Gagal memuat web utama: {e}")
        return []

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    events = []
    
    embed_pattern = re.compile(r"openEmbed\('([^']+)'\)", re.IGNORECASE)
    now_wib = datetime.now(ZoneInfo("Asia/Jakarta")) # Target Waktu: WIB

    for row in soup.find_all("div", class_="row"):
        date_node = row.find(class_="ch-date")
        sport_node = row.find(class_="ch-category")
        name_node = row.find(class_="ch-name")
        embed_btn = row.find("a", class_="hd-link secondary")

        if not (date_node and sport_node and name_node and embed_btn):
            continue

        raw_time = date_node.get_text(strip=True)
        sport = sport_node.get_text(strip=True)
        event_name = name_node.get_text(strip=True)
        
        onclick = embed_btn.get("onclick", "")
        match = embed_pattern.search(onclick)
        if not match: continue

        api_link = match.group(1).replace("player.php", "get-stream.php")

        try:
            # Sharkstreams menggunakan zona waktu New York (EST)
            dt_est = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
            dt_source = dt_est.replace(tzinfo=ZoneInfo("America/New_York"))
            
            # Konversi ke WIB
            dt_wib = dt_source.astimezone(ZoneInfo("Asia/Jakarta"))
            
            # Abaikan jadwal lawas
            if dt_wib.date() < now_wib.date() - timedelta(days=1):
                continue
                
            time_str = f"[{dt_wib.strftime('%H:%M WIB')}]"
            diff_seconds = (now_wib - dt_wib).total_seconds()
            is_live = (0 <= diff_seconds <= 12600)
            
        except ValueError:
            time_str = f"[{raw_time}]"
            is_live = False

        time_tag = f"[🔴 LIVE] {time_str}" if is_live else time_str
        full_title = f"{time_tag} {event_name}".strip()

        events.append({
            "sport": sport,
            "title": full_title,
            "api_link": api_link,
            "is_live": is_live
        })

    return events

def extract_api_m3u8(api_url):
    """Menembak API get-stream.php untuk mendapatkan M3U8 mentah."""
    try:
        if not api_url.startswith("http"):
            api_url = f"{BASE_URL}/{api_url.lstrip('/')}"
            
        r = SESSION.get(api_url, timeout=10)
        data = r.json()
        
        urls = data.get("urls")
        if not urls: return None
        
        raw_m3u8 = urls[0]
        clean_m3u8 = re.sub(r"playlist\.m3u8\?.*$", "chunks.m3u8", raw_m3u8, flags=re.IGNORECASE)
        
        return clean_m3u8
    except Exception:
        return None

def main():
    events = get_shark_events()
    if not events:
        print("Tidak ada jadwal yang ditemukan.")
        return

    print(f"Menemukan {len(events)} kandidat jadwal.")
    all_streams = []

    for ev in events:
        print(f"Memproses API: {ev['title']}")
        
        m3u8_link = extract_api_m3u8(ev["api_link"])
        
        if m3u8_link:
            # Format: [Waktu WIB] Nama Acara - SHRK
            display_name = f"{ev['title']} - SHRK"
            
            all_streams.append((ev["sport"], display_name, m3u8_link))
            print(f"  ✅ BERHASIL: {m3u8_link}")
        else:
            print(f"  ❌ M3U8 tidak ditemukan di API.")

    if not all_streams:
        print("\nGagal mengekstrak stream apapun.")
        return

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = f'#EXTM3U x-tvg-url="https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"\n# Last Updated: {ts}\n\n'

    # Menulis untuk VLC Output dengan tag per baris
    with open(VLC_OUTPUT, "w", encoding="utf-8") as f:
        f.write(header)
        for sport, title, url in all_streams:
            tvg_id, logo, group_name = get_tv_data(sport)
            f.write(f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="Shark - {group_name}",{title}\n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'#EXTVLCOPT:http-origin={BASE_URL}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'{url}\n\n')

    # Menulis untuk TiviMate Output dengan struktur baris yang sama (bukan disatukan dengan URL)
    with open(TIVIMATE_OUTPUT, "w", encoding="utf-8") as f:
        f.write(header)
        for sport, title, url in all_streams:
            tvg_id, logo, group_name = get_tv_data(sport)
            f.write(f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="Shark - {group_name}",{title}\n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'#EXTVLCOPT:http-origin={BASE_URL}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'{url}\n\n')

    print(f"\nSelesai! {len(all_streams)} tayangan berhasil disimpan.")

if __name__ == "__main__":
    main()
