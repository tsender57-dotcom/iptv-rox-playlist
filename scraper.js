const { chromium } = require('playwright');
const fs = require('fs');

// Logika Pro: Ekstraksi data API cerdas
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

function extractTeamName(teamObj) {
    if (!teamObj) return "Unknown Team";
    if (typeof teamObj === 'string') return teamObj;
    return teamObj.name || teamObj.team_name || teamObj.teamName || teamObj.title || "Unknown Team";
}

(async () => {
    console.log("[LOG] Memulai Operasi Hybrid (CLEAN URL MODE)...");
    const matchesMap = new Map();

    // ==========================================
    // FASE 1: DATA INTELLIGENCE (API)
    // ==========================================
    try {
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

            let homeName = extractTeamName(m.homeTeamName || m.home_team || m.homeName || m.home);
            let awayName = extractTeamName(m.awayTeamName || m.away_team || m.awayName || m.away);
            
            let logoUrl = "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png";
            if (m.home_team && m.home_team.logo) logoUrl = m.home_team.logo;
            else if (m.homeLogo) logoUrl = m.homeLogo;
            
            matchesMap.set(String(id).toLowerCase(), {
                title: `${homeName} VS ${awayName} [CAMEL LIVE]`,
                logo: logoUrl
            });
        }
        console.log(`[LOG] Memetakan ${matchesMap.size} jadwal dari API.`);
    } catch (error) {
        console.error(`[ERROR] API: ${error.message}`);
    }

    // ==========================================
    // FASE 2: EXECUTION ENGINE (PLAYWRIGHT)
    // ==========================================
    const targetMainDomain = "https://www.camellive.top"; 
    const globalUserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, gecko) Chrome/122.0.0.0 Safari/537.36';

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        userAgent: globalUserAgent,
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
        
        // Resource Blocker untuk kecepatan maksimal
        await page.route('**/*', route => {
            const type = route.request().resourceType();
            if (['image', 'stylesheet', 'font'].includes(type)) {
                route.abort();
            } else {
                route.continue();
            }
        });

        await page.goto(targetMainDomain + '/', { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(3000); 

        const liveLinks = await page.$$eval('a', as => {
            return [...new Set(as.map(a => a.href).filter(href => href.includes('/live/') || href.includes('/football/')))];
        });
        
        console.log(`[LOG] Ditemukan ${liveLinks.length} tautan aktif.`);

        for (const link of liveLinks) {
            try {
                const urlParts = link.split('/');
                let urlId = urlParts[urlParts.length - 1].toLowerCase();
                if(urlId.includes('?')) urlId = urlId.split('?')[0];

                const matchData = matchesMap.get(urlId) || {
                    title: `CAMEL LIVE EVENT ${streamFoundCount + 1}`,
                    logo: "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png"
                };

                const streamPage = await context.newPage();
                let capturedM3u8 = null;

                const m3u8Promise = new Promise((resolve) => {
                    streamPage.on('response', async (response) => {
                        const resUrl = response.url();
                        if (resUrl.includes('.m3u8') && (resUrl.includes('txSecret') || resUrl.includes('auth='))) {
                            capturedM3u8 = resUrl;
                            resolve(true); 
                        }
                    });
                });

                console.log(`[>>] Sniffing: ${matchData.title}`);
                await streamPage.goto(link, { waitUntil: 'domcontentloaded', timeout: 30000 });
                
                const playBtn = streamPage.locator('[class*="play"], video').first();
                if (await playBtn.isVisible()) {
                    await playBtn.click().catch(() => {});
                }

                await Promise.race([
                    m3u8Promise,
                    streamPage.waitForTimeout(8000)
                ]);

                await streamPage.close(); 

                if (capturedM3u8) {
                    // LOGIKA MURNI: Menggunakan baris EXTVLCOPT terpisah, URL tetap bersih
                    playlistContent += `#EXTINF:-1 tvg-logo="${matchData.logo}" group-title="CAMEL SPORTS", ${matchData.title}\n`;
                    playlistContent += `#EXTVLCOPT:http-origin=${targetMainDomain}\n`;
                    playlistContent += `#EXTVLCOPT:http-referrer=${targetMainDomain}/\n`;
                    playlistContent += `#EXTVLCOPT:http-user-agent=${globalUserAgent}\n`;
                    playlistContent += `${capturedM3u8}\n`;
                    streamFoundCount++;
                }

            } catch (err) {
                console.log(`[SKIP] Timeout.`);
            }
        }

        if (streamFoundCount > 0) {
            fs.writeFileSync('playlist.m3u', playlistContent);
            console.log(`[LOG] SUCCESS! ${streamFoundCount} stream murni tersimpan.`);
        } else {
            console.log("[LOG] Tidak ada stream.");
            fs.writeFileSync('playlist.m3u', "#EXTM3U\n#EXTINF:-1,Tidak Ada Siaran Langsung\nhttp://offline.local");
        }

    } catch (error) {
        console.error(`[ERROR FATAL] ${error.message}`);
    } finally {
        await browser.close();
    }
})();
