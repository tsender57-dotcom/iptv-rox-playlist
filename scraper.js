const { chromium } = require('playwright');
const fs = require('fs');

// Logika Pro: Fungsi cerdas untuk membongkar JSON apa pun dan mencari data pertandingan
function smartExtractMatches(json) {
    let matches = [];
    function searchNode(obj) {
        if (Array.isArray(obj)) {
            if (obj.length > 0 && typeof obj[0] === 'object' && obj[0] !== null) {
                const sampleStr = JSON.stringify(obj[0]).toLowerCase();
                // Jika objek dalam array ini punya kata 'home' dan 'away', ini pasti array pertandingan!
                if (sampleStr.includes('home') && sampleStr.includes('away')) {
                    matches = matches.concat(obj);
                }
            }
            obj.forEach(searchNode);
        } else if (typeof obj === 'object' && obj !== null) {
            Object.values(obj).forEach(searchNode);
        }
    }
    searchNode(json);
    return matches;
}

(async () => {
    console.log("[LOG] Memulai Operasi Hybrid (API + Playwright)...");
    const matchesMap = new Map();

    // ==========================================
    // FASE 1: TARIK DATA DARI API (Jadwal & Logo)
    // ==========================================
    try {
        console.log("[LOG] Menembak API Camelscore...");
        const apiResponse = await fetch('https://api.cameltv.live/camel-service/ee/sports_live/home?page=1&size=20', {
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Accept-Language': 'en',
                'AppVersion': '20.0.0.0',
                'Device': 'WEB',
                'region': 'XM',
                'node': 'camel1_g2',
                'deviceId': '07fc8207-5b16-4b3f-b46e-e1f7e986a2aa'
            }
        });

        const apiJson = await apiResponse.json();
        const rawMatches = smartExtractMatches(apiJson);

        // Membersihkan dan memetakan data API
        for (const m of rawMatches) {
            // Ekstrak ID, Nama, dan Logo dengan logika fallback (anti-error)
            let id = m.id || m.matchId || m.match_id || m.sv_id || null;
            if (!id) continue;

            // Logika pencarian properti nama tim yang dinamis
            let homeName = m.homeTeamName || m.home_team || m.homeName || m.home || "Home Team";
            let awayName = m.awayTeamName || m.away_team || m.awayName || m.away || "Away Team";
            // Ambil logo jika ada, jika tidak pakai logo default OGI Bone
            let logoUrl = m.homeLogo || m.home_logo || m.logo || "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png";
            
            matchesMap.set(String(id).toLowerCase(), {
                title: `${homeName} VS ${awayName} [CAMEL LIVE]`,
                logo: logoUrl
            });
        }
        console.log(`[LOG] Berhasil memetakan ${matchesMap.size} jadwal pertandingan dari API.`);
    } catch (error) {
        console.error(`[ERROR] Gagal mengambil data API: ${error.message}`);
    }

    // ==========================================
    // FASE 2: PLAYWRIGHT NETWORK SNIFFER
    // ==========================================
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        viewport: { width: 1280, height: 720 },
        extraHTTPHeaders: {
            'Origin': 'https://www.camel1.tv',
            'Referer': 'https://www.camel1.tv/'
        }
    });

    const targetUrl = "https://www.camel1.tv/";
    let playlistContent = "#EXTM3U\n";
    let streamFoundCount = 0;

    try {
        const page = await context.newPage();
        console.log(`[LOG] Membuka beranda ${targetUrl} untuk mencari link video...`);
        await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 60000 });
        await page.waitForTimeout(5000); // Tunggu render DOM

        // Scrape semua link yang mengarah ke halaman live streaming
        const liveLinks = await page.$$eval('a', as => {
            return [...new Set(as.map(a => a.href).filter(href => href.includes('/live/')))];
        });
        
        console.log(`[LOG] Menemukan ${liveLinks.length} tautan Live Streaming. Memulai intersepsi...`);

        // Iterasi ke setiap link untuk menangkap m3u8
        for (const link of liveLinks) {
            try {
                // Ambil ID dari URL (biasanya segmen terakhir dari link seperti .../live/4jwq2ghnn9onm0v)
                const urlParts = link.split('/');
                const urlId = urlParts[urlParts.length - 1].toLowerCase();

                // Cocokkan dengan data API, jika tidak ada di API buat judul standar
                const matchData = matchesMap.get(urlId) || {
                    title: `CAMEL LIVE EVENT ${streamFoundCount + 1}`,
                    logo: "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png"
                };

                console.log(`[LOG] Mengakses: ${matchData.title}`);
                const streamPage = await context.newPage();
                let capturedM3u8 = null;

                // Pasang pendengar jaringan (Network Sniffer)
                streamPage.on('response', async (response) => {
                    const resUrl = response.url();
                    if (resUrl.includes('.m3u8')) {
                        capturedM3u8 = resUrl;
                    }
                });

                await streamPage.goto(link, { waitUntil: 'domcontentloaded', timeout: 30000 });
                
                // Pancing tombol play jika video belum otomatis terputar
                const playBtn = streamPage.locator('[class*="play"], video').first();
                if (await playBtn.isVisible()) {
                    await playBtn.click().catch(() => {});
                }

                // Tunggu maksimal 10 detik agar m3u8 ter-generate di Network
                await streamPage.waitForTimeout(10000);
                await streamPage.close(); // Tutup tab untuk hemat memori

                if (capturedM3u8) {
                    console.log(`[SUCCESS] M3U8 Ditangkap: ${capturedM3u8}`);
                    playlistContent += `#EXTINF:-1 tvg-logo="${matchData.logo}" group-title="CAMEL SPORTS", ${matchData.title}\n`;
                    playlistContent += `#EXTVLCOPT:http-origin=https://www.camel1.tv\n`;
                    playlistContent += `#EXTVLCOPT:http-referrer=https://www.camel1.tv/\n`;
                    playlistContent += `${capturedM3u8}\n`;
                    streamFoundCount++;
                }

            } catch (err) {
                console.log(`[SKIP] Gagal memproses link, lanjut ke link berikutnya...`);
            }
        }

        // ==========================================
        // FASE 3: SIMPAN OUTPUT KE PLAYLIST
        // ==========================================
        if (streamFoundCount > 0) {
            fs.writeFileSync('playlist.m3u', playlistContent);
            console.log(`[LOG] Selesai! Berhasil menyimpan ${streamFoundCount} stream ke playlist.m3u`);
        } else {
            console.log("[LOG] Tidak ada stream aktif yang ditemukan pada sesi ini.");
            // Buat file kosong agar git tetap berjalan rapi
            fs.writeFileSync('playlist.m3u', "#EXTM3U\n#EXTINF:-1,Tidak Ada Siaran Langsung Saat Ini\nhttp://offline.local");
        }

    } catch (error) {
        console.error(`[ERROR FATAL] ${error.message}`);
    } finally {
        await browser.close();
    }
})();
