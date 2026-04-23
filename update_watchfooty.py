#!/usr/bin/env python3

import asyncio
import json
import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlencode

from playwright.async_api import async_playwright

# Konfigurasi Dasar
BASE_DOMAIN = "watchfooty.st"
API_URL = f"https://api.{BASE_DOMAIN}"
BASE_URL = f"https://www.{BASE_DOMAIN}"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT, "Referer": BASE_URL + "/"}

VLC_OUTPUT = "Watchfooty_VLC.m3u8"
TIVIMATE_OUTPUT = "Watchfooty_TiviMate.m3u8"

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

def get_wfty_live_events():
    """Mengambil jadwal pertandingan LIVE melalui API TRPC Watchfooty."""
    print(f"Mencari jadwal LIVE di API {BASE_DOMAIN}...")
    
    now = datetime.utcnow()
    start_iso = now.isoformat() + "Z"
    end_iso = (now + timedelta(days=1)).isoformat() + "Z"

    url = f"{API_URL}/_internal/trpc/sports.getSportsLiveMatchesCount,sports.getPopularMatches,sports.getPopularLiveMatches"
    input_data = {
        "0": {"json": {"start": start_iso, "end": end_iso}},
        "1": {"json": None, "meta": {"values": ["undefined"]}},
        "2": {"json": None, "meta": {"values": ["undefined"]}}
    }
    
    params = {"batch": "1", "input": json.dumps(input_data, separators=(",", ":"))}

    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        # Data berada di elemen terakhir array balasan API
        api_data = data[-1].get("result", {}).get("data", {}).get("json", [])
        if not api_data:
            return []

        events = []
        for link in api_data:
            if not link.get("viewerCount"): continue
            
            event_id = link.get("id")
            sport = link.get("league", "misc")
            title = link.get("title", "Unknown Event")
            start_time_utc = link.get("startTime")
            
            # --- JURUS KONVERSI WIB ---
            time_str = ""
            if start_time_utc:
                try:
                    dt_utc = datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
                    dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                    time_str = f"[{dt_wib.strftime('%H:%M WIB')}] "
                except:
                    pass

            # Karena diambil dari endpoint getPopularLiveMatches, asumsikan status LIVE
            full_title = f"[🔴 LIVE] {time_str}{title} - WFTY"
            
            events.append({
                "id": event_id,
                "sport": sport,
                "title": full_title
            })
            
        return events
    except Exception as e:
        print(f"Gagal mengakses API WFTY: {e}")
        return []

def get_embed_url(event_id):
    """Mendapatkan link Iframe (sportsembed.su) dari ID pertandingan."""
    now = datetime.utcnow()
    start_iso = now.isoformat() + "Z"
    end_iso = (now + timedelta(days=1)).isoformat() + "Z"

    url = f"{API_URL}/_internal/trpc/sports.getSportsLiveMatchesCount,sports.getMatchById"
    input_data = {
        "0": {"json": {"start": start_iso, "end": end_iso}},
        "1": {"json": {"id": event_id, "withoutAdditionalInfo": True, "withoutLinks": False}}
    }
    params = {"batch": "1", "input": json.dumps(input_data, separators=(",", ":"))}

    try:
        r = SESSION.get(url, params=params, timeout=10)
        data = r.json()
        
        api_data = data[-1].get("result", {}).get("data", {}).get("json", {})
        links = api_data.get("fixtureData", {}).get("links", [])
        
        # Filter link rusak/terenkripsi (e) dan ambil yang viewer-nya paling banyak
        valid_links = []
        for link in links:
            wld = link.get("wld", {})
            if wld and "e" not in wld:
                valid_links.append(link)
                
        valid_links.sort(key=lambda x: x.get("viewerCount", -1), reverse=True)
        if not valid_links: return None
        
        best = valid_links[0]
        gi, t = best.get("gi"), best.get("t")
        wld = best.get("wld", {})
        cn, sn = wld.get("cn"), wld.get("sn")
        
        if not all([gi, t, cn, sn]): return None
        
        return f"https://sportsembed.su/embed/{gi}/{t}/{cn}/{sn}?player=clappr&autoplay=true"

    except Exception:
        return None

# --- JURUS MENCURI M3U8 (Playwright) ---
async def extract_m3u8_playwright(page, url):
    stream_url = None

    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and "ad" not in request.url.lower():
            if not stream_url: stream_url = request.url

    page.on("request", handle_request)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # Hajar Clappr Player
        try:
            btn = page.locator("button.streambutton").first
            if await btn.count() > 0:
                await btn.dblclick(force=True, timeout=2000)
        except: pass

        # Curi dari memori Iframe
        try:
            src = await page.evaluate("() => clapprPlayer.options.source")
            if src and ".m3u8" in src: stream_url = src
        except: pass

    except Exception:
        pass

    page.remove_listener("request", handle_request)
    return stream_url

async def main():
    print("Memulai Watchfooty playlist generation...")
    events = get_wfty_live_events()
    
    if not events:
        print("Tidak ada jadwal LIVE yang ditemukan dari API.")
        return

    print(f"Menemukan {len(events)} jadwal LIVE. Mempersiapkan Sniper...")
    all_streams = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-web-security"
            ]
        )
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        for ev in events:
            print(f"Memproses: {ev['title']}")
            
            # Step 1: Dapatkan URL Iframe Sportsembed
            embed_url = get_embed_url(ev['id'])
            if not embed_url:
                print("  ❌ Gagal mendapatkan Iframe embed.")
                continue
                
            # Step 2: Curi M3U8 dengan Playwright
            m3u8_link = await extract_m3u8_playwright(page, embed_url)
            
            if m3u8_link:
                all_streams.append((ev['sport'], ev['title'], m3u8_link))
                print(f"  ✅ BERHASIL: {m3u8_link}")
            else:
                print(f"  ⚠️ M3U8 tidak terdeteksi.")

        await browser.close()

    if not all_streams:
        print("\nGagal mengekstrak stream apapun.")
        return

    # Tulis playlist
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = f'#EXTM3U x-tvg-url="https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"\n# Last Updated: {ts}\n\n'

    with open(VLC_OUTPUT, "w", encoding="utf-8") as f:
        f.write(header)
        for sport, title, url in all_streams:
            tvg_id, logo, group_name = get_tv_data(sport)
            f.write(f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="Watchfooty - {group_name}",{title}\n{url}\n\n')

    ua_enc = quote(USER_AGENT, safe="")
    with open(TIVIMATE_OUTPUT, "w", encoding="utf-8") as f:
        f.write(header)
        for sport, title, url in all_streams:
            tvg_id, logo, group_name = get_tv_data(sport)
            # Referer harus sportsembed.su karena server video aslinya mendeteksi itu
            f.write(f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="Watchfooty - {group_name}",{title}\n{url}|referer=https://sportsembed.su/|user-agent={ua_enc}\n\n')

    print(f"\nSelesai! {len(all_streams)} tayangan berhasil disimpan.")

if __name__ == "__main__":
    asyncio.run(main())
