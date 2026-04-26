const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  // 1. Inisialisasi Browser dengan Identitas Resmi (Logika Pro)
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 720 },
    // Injeksi Header Resmi secara Global berdasarkan data valid
    extraHTTPHeaders: {
      'Accept': 'application/json, text/plain, */*',
      'Accept-Language': 'en',
      'Origin': 'https://www.camel1.tv',
      'Referer': 'https://www.camel1.tv/',
      'AppVersion': '20.0.0.0',
      'Device': 'WEB',
      'region': 'XM',
      'node': 'camel1_g2',
      'deviceId': '07fc8207-5b16-4b3f-b46e-e1f7e986a2aa'
    }
  });
  
  const page = await context.newPage();
  const m3u8Links = new Set();
  
  // Menggunakan domain utama yang diizinkan oleh Origin server
  const targetUrl = "https://www.camel1.tv/"; 

  // 2. Intersepsi Jaringan (Network Sniffing)
  page.on('response', async (response) => {
    const url = response.url();
    // Logika Pro: Menangkap URL m3u8 yang valid
    if (url.includes('.m3u8')) {
      console.log(`[FOUND] M3U8 Detected: ${url}`);
      m3u8Links.add(url);
    }
  });

  try {
    console.log(`[LOG] Navigating to ${targetUrl}...`);
    // 3. Eksekusi Navigasi
    await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 60000 });
    
    // Logika tunggu untuk membiarkan script halaman berjalan dan memuat stream
    await page.waitForTimeout(15000);

    // 4. Manajemen Output M3U
    if (m3u8Links.size > 0) {
      let playlistContent = "#EXTM3U\n";
      let i = 1;
      
      for (let link of m3u8Links) {
        playlistContent += `#EXTINF:-1 tvg-id="CH${i}" group-title="AUTO_CAPTURED", CAMEL_LIVE_${i}\n`;
        // Injeksi header ke playlist agar bisa diputar di player IPTV
        playlistContent += `#EXTVLCOPT:http-origin=https://www.camel1.tv\n`;
        playlistContent += `#EXTVLCOPT:http-referrer=https://www.camel1.tv/\n`;
        playlistContent += `${link}\n`;
        i++;
      }
      
      fs.writeFileSync('playlist.m3u', playlistContent);
      console.log("[LOG] Success: playlist.m3u has been updated.");
    } else {
      console.log("[LOG] Status: No active m3u8 streams found in this session.");
    }

  } catch (error) {
    console.error(`[ERROR] Runtime Error: ${error.message}`);
  } finally {
    await browser.close();
  }
})();

