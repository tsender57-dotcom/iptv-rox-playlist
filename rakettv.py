import asyncio
import os
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# Konfigurasi Dasar
TARGET_URL = "https://www.tvonline.my/2024/09/rakettv.html?m=1"
IFRAME_ORIGIN = "https://styleanecdotes.blogspot.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = Path("rakettv.m3u8")

# Logo BWF Default
BWF_LOGO = "https://corporate.bwfbadminton.com/wp-content/uploads/2017/09/BWF-Logo-Text-Sized.jpg"

async def scrape_raket():
    async with async_playwright() as p:
        print(f"Membuka browser untuk {TARGET_URL}...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        # Kita ubah menjadi list (daftar) agar bisa menampung banyak link
        found_streams = []

        # Alat Penyadap Jaringan
        async def intercept_request(request):
            url = request.url
            if ".m3u8" in url and "vtvprime.vn" in url:
                # Pastikan link belum pernah ditambahkan sebelumnya (hindari duplikat)
                if url not in found_streams:
                    print(f"✅ Harta Karun Ditemukan: {url}")
                    found_streams.append(url)

        page.on("request", intercept_request)

        try:
            # 1. Buka halaman utama
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            print("⏳ Menunggu Court 1 (CR1) termuat otomatis...")
            await page.wait_for_timeout(8000)
            
            # 2. Persiapan "Auto-Clicker" (Masuk ke dalam Iframe)
            iframe = page.frame_locator('iframe#video-player')
            
            # Daftar nama tombol tab yang biasanya ada di layar
            courts_to_try = ["CR2", "CR3", "CR4", "Court 2", "Court 3", "Court 4"]
            
            # 3. Eksekusi sapu bersih
            for court in courts_to_try:
                try:
                    # Cari elemen di dalam iframe yang memiliki tulisan CR2, CR3, dst.
                    btn = iframe.get_by_text(court, exact=False)
                    
                    if await btn.count() > 0:
                        print(f"👆 Mengklik tab {court}...")
                        # Gunakan force=True untuk memaksa klik jika tertutup elemen transparan
                        await btn.first.click(force=True, timeout=3000)
                        
                        # Tunggu 5 detik agar bot sempat mencegat request m3u8 yang baru
                        await page.wait_for_timeout(5000)
                except Exception:
                    # Abaikan dengan tenang jika tab-nya tidak ada hari ini
                    pass
                    
        except Exception as e:
            print(f"⚠️ Timeout atau Error pada halaman: {e}")

        await browser.close()

        # 4. Simpan semua hasilnya
        if found_streams:
            save_playlist(found_streams)
        else:
            print("❌ Gagal menemukan link M3U8 apapun.")

def save_playlist(streams):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M WIB")
    
    lines = [
        '#EXTM3U',
        f'# Last Updated: {ts}',
        ''
    ]
    
    # Looping sebanyak jumlah link yang berhasil dirampok
    for idx, m3u8_url in enumerate(streams, start=1):
        court_name = f"COURT {idx}"
        lines.extend([
            f'#EXTINF:-1 tvg-logo="{BWF_LOGO}" tvg-id="Badminton.Live" group-title="R TV",LIVE BADMINTON - Bone TV ({court_name})',
            f'#EXTVLCOPT:http-referrer={IFRAME_ORIGIN}/',
            f'#EXTVLCOPT:http-origin={IFRAME_ORIGIN}',
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
            m3u8_url,
            ''  # Baris kosong untuk pemisah antar court
        ])
    
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Berhasil menyusun {len(streams)} tayangan ke {OUTPUT_FILE}!")

if __name__ == "__main__":
    asyncio.run(scrape_raket())
