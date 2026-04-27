import asyncio
import os
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# --- KONFIGURASI ---
TARGET_URL = "https://www.tvonline.my/2024/09/rakettv.html?m=1"
IFRAME_ORIGIN = "https://styleanecdotes.blogspot.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = Path("rakettv.m3u8")
BWF_LOGO = "https://corporate.bwfbadminton.com/wp-content/uploads/2017/09/BWF-Logo-Text-Sized.jpg"

async def scrape_raket():
    async with async_playwright() as p:
        print(f"🚀 Memulai Scraper RaketTV High-Speed...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        found_streams = []
        # Event untuk memberitahu bot bahwa link baru sudah tertangkap
        stream_found_event = asyncio.Event()

        async def intercept_request(request):
            url = request.url
            # LOGIKA SAPU JAGAT: Tangkap semua .m3u8 (kecuali iklan/analytics)
            if ".m3u8" in url and not any(x in url for x in ["google", "doubleclick", "analytics"]):
                if url not in found_streams:
                    print(f"🎯 Tertangkap: {url[:60]}...")
                    found_streams.append(url)
                    stream_found_event.set() # Bangunkan bot untuk klik tombol selanjutnya

        page.on("request", intercept_request)

        try:
            # 1. Buka halaman utama
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 2. Masuk ke Iframe
            iframe_element = page.frame_locator('iframe#video-player')
            
            # 3. Logika Klik Berurutan (Smart Wait)
            # Kita akan mencoba mengklik hingga 5 tombol court yang ada
            for i in range(5):
                stream_found_event.clear() # Reset sinyal
                
                # Gunakan pemilih posisi (index) karena lebih cepat & akurat dari teks
                # Mencari elemen button atau link yang tampak seperti tombol tab
                tab_selector = iframe_element.locator("button, a, .tab, .btn").nth(i)
                
                if await tab_selector.count() > 0:
                    btn_text = await tab_selector.inner_text()
                    print(f"🖱️ Mengklik Court Index-{i} ({btn_text.strip() or 'No Text'})...")
                    
                    await tab_selector.click(force=True)
                    
                    # SMART WAIT: Tunggu link m3u8 muncul ATAU maksimal 6 detik
                    try:
                        await asyncio.wait_for(stream_found_event.wait(), timeout=6.0)
                        print(f"✅ Berhasil menjaring link untuk Court {i+1}.")
                    except asyncio.TimeoutError:
                        print(f"⚠️ Timeout: Court {i+1} mungkin sedang offline atau tidak ada link.")
                else:
                    # Jika tombol ke-i sudah tidak ada, berarti court sudah habis
                    break
                    
        except Exception as e:
            print(f"❌ Error Sistem: {e}")

        await browser.close()

        if found_streams:
            save_playlist(found_streams)
        else:
            print("💀 Gagal total: Tidak ada link M3U8 yang terjaring.")

def save_playlist(streams):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M WIB")
    lines = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    for idx, m3u8_url in enumerate(streams, start=1):
        # Membersihkan link dari whitespace
        clean_url = m3u8_url.strip()
        
        lines.extend([
            f'#EXTINF:-1 tvg-logo="{BWF_LOGO}" tvg-id="Badminton.Live" group-title="BONE TV",LIVE BADMINTON - Bone TV (COURT {idx})',
            f'#EXTVLCOPT:http-referrer={IFRAME_ORIGIN}/',
            f'#EXTVLCOPT:http-origin={IFRAME_ORIGIN}',
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
            clean_url,
            ''
        ])
    
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"🏁 SELESAI: {len(streams)} court siap dihidangkan di BONE TV!")

if __name__ == "__main__":
    asyncio.run(scrape_raket())
    
