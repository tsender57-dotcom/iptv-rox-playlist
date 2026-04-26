const { chromium } = require('playwright');
const fs = require('fs');

// Logika Pro: Fungsi cerdas untuk membongkar JSON dan mencari data pertandingan
function smartExtractMatches(json) {
    let matches = [];
    function searchNode(obj) {
        if (Array.isArray(obj)) {
            if (obj.length > 0 && typeof obj[0] === 'object' && obj[0] !== null) {
                const sampleStr = JSON.stringify(obj[0]).toLowerCase();
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

// Logika Pro: Fungsi untuk mengekstrak nama tim dengan aman dari struktur Nested Object
function extractTeamName(teamObj) {
    if (!teamObj) return "Unknown Team";
    if (typeof teamObj === 'string') return teamObj;
    // Jika bentuknya objek, cari properti yang biasa dipakai untuk nama
    return teamObj.name || teamObj.team_name || teamObj.teamName || teamObj.title || "Unknown Team";
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

        for (const m of rawMatches) {
            let id = m.id || m.matchId || m.match_id || m.sv_id || null;
            if (!id) continue;

            // Perbaikan [object Object]: Memanggil fungsi ekstraksi nama tim yang aman
            let homeName = extractTeamName(m.homeTeamName || m.home_team || m.homeName || m.home);
            let awayName = extractTeamName(m.awayTeamName || m.away_team || m.awayName || m.away);
            
            let logoUrl = "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png";
            // Coba ambil logo asli jika ada dalam objek
            if (m.home_team && m.home_team.logo) logoUrl = m.home_team.logo;
            else if (m.homeLogo) logoUrl = m.homeLogo;
            
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
    
    // PEMBARUAN KRUSIAL: Update Target dan Header Origin/Referer
    const targetMainDomain = "https://www.camellive.top"; 
    
    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        viewport: { width: 1280, height: 720 },
        extraHTTPHeaders: {
            'Origin': targetMainDomain,
            'Referer': targetMainDomain + '/'
        }
    });

    let playlistContent = "#EXTM3U\n";
    let streamFoundCount = 0;

    try {
        const page = await context.newPage();
        console.log(`[LOG] Membuka beranda ${targetMainDomain} untuk mencari link video...`);
        await page.goto(targetMainDomain + '/', { waitUntil: 'networkidle', timeout: 60000 });
        await page.waitForTimeout(5000); 

        // Scrape link yang mengarah ke live, antisipasi variasi path (/football/ atau /live/)
        const liveLinks = await page.$$eval('a', as => {
            return [...new Set(as.map(a => a.href).filter(href => href.includes('/live/') || href.includes('/football/')))];
        });
        
        console.log(`[LOG] Menemukan ${liveLinks.length} tautan halaman pertandingan. Memulai intersepsi...`);

        for (const link of liveLinks) {
            try {
                // Ambil ID dari URL dengan asumsi ID selalu berada di segmen paling akhir
                const urlParts = link.split('/');
                let urlId = urlParts[urlParts.length - 1].toLowerCase();
                
                // Bersihkan query string jika ada (misal: id?param=1)
                if(urlId.includes('?')) urlId = urlId.split('?')[0];

                const matchData = matchesMap.get(urlId) || {
                    title: `CAMEL LIVE EVENT ${streamFoundCount + 1}`,
                    logo: "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png"
                };

                console.log(`[LOG] Mengakses: ${matchData.title}`);
                const streamPage = await context.newPage();
                let capturedM3u8 = null;

                streamPage.on('response', async (response) => {
                    const resUrl = response.url();
                    // Tangkap hanya m3u8 yang memiliki parameter rahasia dari server utama
                    if (resUrl.includes('.m3u8') && (resUrl.includes('txSecret') || resUrl.includes('auth='))) {
                        capturedM3u8 = resUrl;
                    }
                });

                await streamPage.goto(link, { waitUntil: 'domcontentloaded', timeout: 30000 });
                
                const playBtn = streamPage.locator('[class*="play"], video').first();
                if (await playBtn.isVisible()) {
                    await playBtn.click().catch(() => {});
                }

                await streamPage.waitForTimeout(10000);
                await streamPage.close(); 

                if (capturedM3u8) {
                    console.log(`[SUCCESS] M3U8 Ditangkap: ${capturedM3u8}`);
                    playlistContent += `#EXTINF:-1 tvg-logo="${matchData.logo}" group-title="CAMEL SPORTS", ${matchData.title}\n`;
                    // Update Header VLC Output untuk player IPTV
                    playlistContent += `#EXTVLCOPT:http-origin=${targetMainDomain}\n`;
                    playlistContent += `#EXTVLCOPT:http-referrer=${targetMainDomain}/\n`;
                    playlistContent += `${capturedM3u8}\n`;
                    streamFoundCount++;
                }

            } catch (err) {
                console.log(`[SKIP] Waktu habis atau gagal memproses link.`);
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
            fs.writeFileSync('playlist.m3u', "#EXTM3U\n#EXTINF:-1,Tidak Ada Siaran Langsung Saat Ini\nhttp://offline.local");
        }

    } catch (error) {
        console.error(`[ERROR FATAL] ${error.message}`);
    } finally {
        await browser.close();
    }
})();
