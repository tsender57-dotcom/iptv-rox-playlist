#!/usr/bin/env python3

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote, urljoin, urlparse
import re
import requests
from bs4 import BeautifulSoup
import html

from playwright.async_api import async_playwright, TimeoutError

BASE_URL = "https://roxiestreams.info/"
CATEGORIES = ["", "soccer", "mlb", "nba", "nfl", "nhl", "fighting", "motorsports", "motogp",
              "ufc", "ppv", "wwe", "f1", "f1-streams", "nascar"]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0"
REFERER = BASE_URL

VLC_OUTPUT = "Roxiestreams_VLC.m3u8"
TIVIMATE_OUTPUT = "Roxiestreams_TiviMate.m3u8"

HEADERS = {"User-Agent": USER_AGENT, "Referer": REFERER, "Accept-Language": "en-US,en;q=0.9"}

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
    "f1": ("Racing.Dummy.us", "https://i.postimg.cc/yY6B2pkv/F1.png", "Formula 1"),
    "f1-streams": ("Racing.Dummy.us", "https://i.postimg.cc/yY6B2pkv/F1.png", "Formula 1"),
    "nascar": ("Racing.Dummy.us", "https://i.postimg.cc/m2dR43HV/Motorsports2.png", "NASCAR Cup Series"),
    "misc": ("Sports.Dummy.us", "https://i.postimg.cc/qMm0rc3L/247.png", "Random Events"),
}

M3U8_RE = re.compile(r"(https?://[^\s\"'<>`]+?\.m3u8(?:\?[^\"'<>`\s]*)?)", re.IGNORECASE)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.timeout = 10

def fetch(url, timeout=12):
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        text = r.text
        soup = BeautifulSoup(text, "html.parser")
        return soup, text
    except Exception as e:
        print(f"fetch failed: {url} -> {e}")
        return None, ""

def clean_event_title(raw_title):
    if not raw_title: return ""
    t = html.unescape(raw_title).strip()
    t = " ".join(t.split())
    t = re.sub(r"\s*-\s*Roxiestreams.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*-\s*Watch Live.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*-\s*Watch.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*-\s*Live Stream.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\|.*$", "", t)
    t = t.strip(" -,:")
    return t

def extract_m3u8_from_text(text, base=None):
    if not text: return None
    m = M3U8_RE.search(text)
    if m:
        url = m.group(1)
        if url.startswith("//"): url = "https:" + url
        if base and not urlparse(url).scheme: url = urljoin(base, url)
        return url
    return None

def get_category_event_candidates(category_path):
    cat_url = BASE_URL if not category_path else urljoin(BASE_URL, category_path)
    print(f"Processing category: {category_path or 'root'} -> {cat_url}")
    
    soup, html_text = fetch(cat_url)
    if not soup and not html_text: return []

    candidates = []
    seen = set()
    now_wita = datetime.now(ZoneInfo("Asia/Makassar"))
    
    rows = soup.find_all("tr")
    
    if rows:
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                a_tag = cols[0].find("a", href=True)
                if not a_tag: continue
                    
                href = a_tag["href"].strip()
                title_text = a_tag.get_text(" ", strip=True) or ""
                
                raw_time = cols[1].get_text(strip=True)
                countdown_text = cols[2].get_text(strip=True).upper()
                
                time_text = ""
                is_live = False
                
                # Mengonversi waktu ke WITA
                try:
                    clean_raw = " ".join(raw_time.split())
                    dt_web = datetime.strptime(clean_raw, "%B %d, %Y %I:%M %p")
                    dt_source = dt_web.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
                    dt_wita = dt_source.astimezone(ZoneInfo("Asia/Makassar"))
                    time_str = f"[{dt_wita.strftime('%H:%M WITA')}]"
                    
                    diff_seconds = (now_wita - dt_wita).total_seconds()
                    if 0 <= diff_seconds <= 12600:
                        is_live = True
                        
                except ValueError:
                    time_match = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)", raw_time, re.IGNORECASE)
                    time_str = f"[{time_match.group(1).upper()}]" if time_match else f"[{raw_time}]"
                
                if "LIVE" in countdown_text or "STARTED" in countdown_text or is_live:
                    time_text = f"[🔴 LIVE] {time_str} "
                else:
                    time_text = f"{time_str} "
                
                full_title = f"{time_text}{title_text}".strip()
                if not href or href.startswith(("mailto:", "javascript:")): continue
                    
                full = href if href.startswith("http") else urljoin(cat_url, href)
                low = href.lower()
                
                if ".m3u8" in href or any(k in low for k in ("stream", "streams", "match", "game", "event")) or re.search(r"-\d+$", low):
                    if full not in seen:
                        seen.add(full)
                        # Penambahan status is_live ke candidate agar bot tahu mana yg perlu dieksekusi Playwright
                        candidates.append((full_title, full, is_live or "LIVE" in countdown_text))
                        
    print(f"  → Found {len(candidates)} candidate links on category page")
    return candidates

def get_tv_data_for_category(cat_path):
    key = (cat_path or "misc").lower().strip()
    key = key.replace("-streams", "").replace("streams", "")
    if key in TV_INFO: return TV_INFO[key]
    for k in TV_INFO:
        if k in key: return TV_INFO[k]
    return TV_INFO["misc"]

def write_playlists(streams):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = f'#EXTM3U x-tvg-url="https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"\n# Last Updated: {ts}\n\n'

    with open(VLC_OUTPUT, "w", encoding="utf-8") as f:
        f.write(header)
        for cat_name, ev_name, url in streams:
            tvg_id, logo, group_name = get_tv_data_for_category(cat_name)
            f.write(f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="Roxiestreams - {group_name}",{ev_name}\n')
            f.write(f'{url}\n\n')

    ua_enc = quote(USER_AGENT, safe="")
    with open(TIVIMATE_OUTPUT, "w", encoding="utf-8") as f:
        f.write(header)
        for cat_name, ev_name, url in streams:
            tvg_id, logo, group_name = get_tv_data_for_category(cat_name)
            f.write(f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="Roxiestreams - {group_name}",{ev_name}\n')
            f.write(f'{url}|referer={REFERER}|user-agent={ua_enc}\n\n')


# ------------------------------------------------------------------
# JURUS JS CLAPPR + LOGIKA BROSUR
# ------------------------------------------------------------------
async def extract_clappr_m3u8(page, url):
    """Mengekstrak M3U8 langsung dari variabel JavaScript Clappr Player."""
    stream_url = None
    try:
        print(f"  Membuka halaman {url}")
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        if not resp or resp.status != 200:
            return None

        # JURUS 1: Cari tombol Play Clappr dan paksa klik ganda
        try:
            btn = page.locator("button.streambutton").first
            await btn.dblclick(force=True, timeout=3000)
            print("  Tombol play berhasil diklik.")
        except TimeoutError:
            print("  Tidak ada tombol play. Mencoba mengekstrak langsung...")

        # JURUS 2: Tunggu sampai mesin Clappr menyala di memori
        try:
            await page.wait_for_function("() => typeof clapprPlayer !== 'undefined'", timeout=8000)
            
            # JURUS 3: Curi langsung sumber videonya
            stream_url = await page.evaluate("() => clapprPlayer.options.source")
            if stream_url:
                print("  💥 BERHASIL MENCURI LINK DARI CLAPPR!")
        except TimeoutError:
            print("  Variabel clapprPlayer tidak ditemukan. Berpindah ke fallback.")
            
        # Fallback jika Clappr gagal (cari m3u8 statis di web)
        if not stream_url:
            content = await page.content()
            m = M3U8_RE.search(content)
            if m:
                stream_url = m.group(1)

    except Exception as e:
        print(f"  Error saat memproses {url}: {e}")

    return stream_url

async def main():
    print("Starting RoxieStreams playlist generation...")
    all_streams = []
    seen_urls = set()
    
    # 1. Kumpulkan Kandidat
    all_candidates = []
    for cat in CATEGORIES:
        try:
            candidates = get_category_event_candidates(cat)
            for anchor_text, href, is_live in candidates:
                all_candidates.append((cat, anchor_text, href, is_live))
        except Exception as e:
            print(f"Failed to parse category {cat}: {e}")
            continue

    if not all_candidates:
        print("No streams found.")
        return

    print(f"\nMulai proses Ekstraksi Clappr untuk {len(all_candidates)} pertandingan...")

    # 2. Eksekusi Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-popup-blocking"
            ]
        )
        context = await browser.new_context(user_agent=USER_AGENT)
        
        # Penutupan popup agresif (berjaga-jaga)
        async def close_popup(new_page): await new_page.close()
        context.on("page", close_popup) 

        page = await context.new_page()

        for cat, anchor_text, href, is_live in all_candidates:
            # Jika sudah berupa M3U8 statis
            if ".m3u8" in href:
                clean = extract_m3u8_from_text(href, base=href) or href
                if clean and clean not in seen_urls:
                    seen_urls.add(clean)
                    title = clean_event_title(anchor_text)
                    display_name = f"{(cat or 'Roxiestreams').title()} - {title}"
                    all_streams.append(((cat or "misc"), display_name, clean))
                continue

            clean_m3u8 = None
            
            # --- LOGIKA EKSEKUSI PINTAR ---
            # Jika web belum LIVE, jangan repot-repot buka Playwright, langsung simpan sebagai brosur.
            if is_live:
                clean_m3u8 = await extract_clappr_m3u8(page, href)

            if not clean_m3u8:
                clean_m3u8 = href # Fallback ke Logika Brosur
                
            if clean_m3u8 not in seen_urls:
                seen_urls.add(clean_m3u8)
                
                final_title = clean_event_title(anchor_text)
                time_tag_match = re.search(r"^((?:\[.*?\]\s*)+)", anchor_text)
                if time_tag_match:
                    tags = time_tag_match.group(1).strip() + " "
                    clean_ft = re.sub(r"^(?:\[.*?\]\s*)+", "", final_title)
                    final_title = tags + clean_event_title(clean_ft)
                else:
                    final_title = clean_event_title(final_title)
                    
                display_name = f"{(cat or 'Roxiestreams').title()} - {final_title}"
                all_streams.append(((cat or "misc"), display_name, clean_m3u8))
                
                if ".m3u8" in clean_m3u8:
                    print(f"  ✅ TERSIMPAN M3U8: {clean_m3u8}")
                else:
                    print(f"  ⚠️ JADWAL TERSIMPAN: {clean_m3u8}")

        await browser.close()

    print(f"\nBerhasil menangkap {len(all_streams)} streams jadwal & Live.")
    write_playlists(all_streams)
    print(f"VLC: {VLC_OUTPUT}")
    print(f"TiviMate: {TIVIMATE_OUTPUT}")
    print("Selesai.")

if __name__ == "__main__":
    asyncio.run(main())
