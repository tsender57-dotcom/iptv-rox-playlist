import asyncio
import os
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# Konfigurasi
TARGET_URL = "https://www.tvonline.my/2024/09/rakettv.html"
IFRAME_ORIGIN = "https://styleanecdotes.blogspot.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = Path("rakettv.m3u8")

async def scrape_raket():
    async with async_playwright() as p:
        print(f"Membuka browser untuk {TARGET_URL}...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        found_m3u8 = None

        # Fungsi untuk mencegat request jaringan
        async def intercept_request(request):
            nonlocal found_m3u8
            url = request.url
            if ".m3u8" in url and "vtvprime.vn" in url:
                print(f"✅ Harta Karun Ditemukan: {url}")
                found_m3u8 = url

        page.on("request", intercept_request)

        try:
            # Buka halaman dan tunggu sampai jaringan tenang (idle)
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            # Beri waktu tambahan 10 detik agar player memanggil link m3u8
            await asyncio.sleep(10)
        except Exception as e:
            print(f"⚠️ Timeout atau Error: {e}")

        await browser.close()

        if found_m3u8:
            save_playlist(found_m3u8)
        else:
            print("❌ Gagal menemukan link M3U8.")

def save_playlist(m3u8_url):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M WIB")
    
    # Rakit Header MABES ENTERPRISE
    lines = [
        '#EXTM3U',
        f'# Last Updated: {ts}',
        '',
        '#EXTINF:-1 tvg-logo="https://i.postimg.cc/HsWHFvV0/Soccer.png" tvg-id="Badminton.Live" group-title="RAKET TV",LIVE BADMINTON - RAKET TV',
        f'#EXTVLCOPT:http-referrer={IFRAME_ORIGIN}/',
        f'#EXTVLCOPT:http-origin={IFRAME_ORIGIN}',
        f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
        m3u8_url
    ]
    
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Berhasil menyimpan ke {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(scrape_raket())
