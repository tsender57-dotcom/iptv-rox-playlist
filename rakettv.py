import asyncio
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# --- KONFIGURASI DASAR ---
TARGET_URL = "https://www.tvonline.my/2024/09/rakettv.html?m=1"
IFRAME_ORIGIN = "https://styleanecdotes.blogspot.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = Path("rakettv.m3u8")
BWF_LOGO = "https://corporate.bwfbadminton.com/wp-content/uploads/2017/09/BWF-Logo-Text-Sized.jpg"

async def scrape_raket():
    async with async_playwright() as p:
        print("🚀 Memulai Scraper RaketTV (Sapu Jagat & Smart-Wait)...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        found_streams = []
        # Alarm cerdas untuk membangunkan bot seketika saat link tertangkap
        stream_found_event = asyncio.Event()

        async def intercept_request(request):
            url = request.url
            # FILTER SAPU JAGAT: Tangkap semua .m3u8, apa pun nama servernya (buang link iklan)
            if ".m3u8" in url and not any(x in url for x in ["google", "doubleclick", "analytics", "ads"]):
                if url not in found_streams:
                    print(f"🎯 HARTA KARUN TERTANGKAP: {url[:70]}...")
                    found_streams.append(url)
                    stream_found_event.set() # Bangunkan bot untuk lanjut klik tombol berikutnya

        page.on("request", intercept_request)

        try:
            # 1. Buka web (domcontentloaded jauh lebih cepat dari networkidle)
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            print("⏳ Menunggu Court 1 (Default) termuat otomatis...")
            try:
                # Tunggu maksimal 8 detik untuk tangkapan pertama
                await asyncio.wait_for(stream_found_event.wait(), timeout=8.0)
            except asyncio.TimeoutError:
                print("⚠️ CR1 lambat atau sedang offline, lanjut periksa tab lain.")

            # 2. Masuk ke Iframe untuk mencari tombol CR2, CR3, dst.
            iframe = page.frame_locator('iframe#video-player')
            
            # 3. Eksekusi Klik Presisi & Cepat
            courts_to_try = ["CR2", "CR3", "CR4", "Court 2", "Court 3", "Court 4"]
            
            for court in courts_to_try:
                stream_found_event.clear() # Reset alarm jaring
                
                # Cari tombol berdasarkan teks yang PASTI (anti salah pencet)
                btn = iframe.get_by_text(court, exact=False)
                
                if await btn.count() > 0:
                    print(f"👆 Mengklik tab {court}...")
                    await btn.first.click(force=True)
                    
                    # SMART-WAIT: Bot hanya akan diam sampai link ketangkap, maksimal 6 detik
                    try:
                        await asyncio.wait_for(stream_found_event.wait(), timeout=6.0)
                        print(f"✅ Link {court} berhasil diamankan.")
                    except asyncio.TimeoutError:
                        print(f"⚠️ {court} di-klik tapi tidak mengeluarkan link (Mungkin Offline).")
                        
        except Exception as e:
            print(f"❌ Error Sistem: {e}")

        await browser.close()

        # 4. Tahap Akhir: Penyimpanan
        if found_streams:
            save_playlist(found_streams)
        else:
            print("💀 Gagal Total: Tidak ada satupun link M3U8 yang terjaring.")

def save_playlist(streams):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M WIB")
    lines = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    for idx, m3u8_url in enumerate(streams, start=1):
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
    print(f"🏁 SELESAI: {len(streams)} court siap mengudara di BONE TV!")

if __name__ == "__main__":
    asyncio.run(scrape_raket())
    
