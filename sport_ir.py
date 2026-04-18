import asyncio
import os
from functools import partial
from urllib.parse import urljoin, quote
from datetime import datetime
from zoneinfo import ZoneInfo

from utils import Cache, Time, get_logger, leagues, network

log = get_logger(__name__)

urls: dict[str, dict[str, str | float]] = {}

TAG = "SPORTir"

CACHE_FILE = Cache(TAG, exp=10_800)

API_URLS = {
    sport: f"https://api.{sport.lower()}24all.ir"
    for sport in [
        "MLB",
        "NBA",
        # "NFL",
        "NHL",
    ]
}

BASE_URLS = {sport: url.replace("api.", "") for sport, url in API_URLS.items()}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# Output files
VLC_OUTPUT = "sport_ir_vlc.m3u8"
TIVIMATE_OUTPUT = "sport_ir_tivimate.m3u8"


# ---------------------------------------------------------
# PLAYLIST GENERATOR
# ---------------------------------------------------------

def generate_playlists():
    """
    Generate VLC and Tivimate playlist files from captured streams
    """
    vlc_lines = ["#EXTM3U"]
    tivimate_lines = ["#EXTM3U"]
    
    ua_encoded = quote(USER_AGENT, safe="")
    
    valid_streams = 0
    
    for chno, (name, data) in enumerate(urls.items(), start=1):
        
        url = data.get("url")
        logo = data.get("logo") or ""
        tvg_id = data.get("id")
        base = data.get("base")
        ts = data.get("timestamp")  # Mengambil timestamp waktu pertandingan
        
        if not url:
            continue
        
        valid_streams += 1
        
        # Format Waktu ke WIB
        time_prefix = ""
        if ts:
            try:
                # Ubah timestamp UTC ke format datetime, lalu konversi ke WIB
                dt_utc = datetime.fromtimestamp(float(ts), tz=ZoneInfo("UTC"))
                dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                time_prefix = f"[{dt_wib.strftime('%H:%M WIB')}] "
            except Exception as e:
                log.warning(f"Gagal memformat waktu untuk {name}: {e}")

        # Gabungkan Jam dan Nama Pertandingan
        display_name = f"{time_prefix}{name}"
        
        extinf = (
            f'#EXTINF:-1 tvg-chno="{chno}" tvg-id="{tvg_id}" '
            f'tvg-name="{display_name}" tvg-logo="{logo}" group-title="Live Events",{display_name}'
        )
        
        # VLC format (with #EXTVLCOPT headers)
        vlc_lines.append(extinf)
        vlc_lines.append(f"#EXTVLCOPT:http-referrer={base}")
        vlc_lines.append(f"#EXTVLCOPT:http-origin={base}")
        vlc_lines.append(f"#EXTVLCOPT:http-user-agent={USER_AGENT}")
        vlc_lines.append(url)
        vlc_lines.append("")  # Empty line for readability
        
        # Tivimate format (pipe-separated headers)
        tivimate_lines.append(extinf)
        tivimate_url = (
            f"{url}"
            f"|referer={base}"
            f"|origin={base}"
            f"|user-agent={ua_encoded}"
        )
        tivimate_lines.append(tivimate_url)
        tivimate_lines.append("")  # Empty line for readability
    
    # Write VLC playlist
    with open(VLC_OUTPUT, "w", encoding="utf8") as f:
        f.write("\n".join(vlc_lines))
    log.info(f"Generated {VLC_OUTPUT} with {valid_streams} streams")
    
    # Write Tivimate playlist
    with open(TIVIMATE_OUTPUT, "w", encoding="utf8") as f:
        f.write("\n".join(tivimate_lines))
    log.info(f"Generated {TIVIMATE_OUTPUT} with {valid_streams} streams")


# ---------------------------------------------------------
# PROCESS EVENT
# ---------------------------------------------------------

async def process_event(
    sport: str,
    flavor_id: str,
    media_id: int,
    url_num: int,
) -> str | None:

    r = await network.client.post(
        urljoin(API_URLS[sport], "api/v2/generate_stream_info"),
        headers={"Referer": BASE_URLS[sport]},
        json={"flavor_id": flavor_id, "media_event_id": media_id},
    )

    if r.status_code != 200:
        log.warning(f"URL {url_num}) Failed to create post request. Status: {r.status_code}")
        return

    data: dict[str, str] = r.json()

    if not (m3u8_url := data.get("url")):
        log.warning(f"URL {url_num}) No M3U8 found in response")
        return

    log.info(f"URL {url_num}) Captured M3U8")

    return m3u8_url


# ---------------------------------------------------------
# EVENT DISCOVERY
# ---------------------------------------------------------

async def get_api_data() -> dict[str, dict[str, list[dict]]]:
    tasks = [
        (
            sport,
            network.request(urljoin(url, "api/v2/stateshot"), log=log),
        )
        for sport, url in API_URLS.items()
    ]

    results = await asyncio.gather(*(task for _, task in tasks))

    return {sport: r.json() for (sport, _), r in zip(tasks, results) if r}


async def get_events(cached_keys: list[str]) -> list[dict[str, str]]:
    now = Time.clean(Time.now())

    api_data = await get_api_data()

    events = []

    # Expanded time window: 6 hours back and 6 hours forward
    start_dt = now.delta(hours=-6)
    end_dt = now.delta(hours=6)

    for sport in api_data:
        data = api_data[sport]

        teams = data.get("teams", {})

        flavors = data.get("flavors", {})

        media_events = data.get("media_events", {})

        team_identifier: dict[int, str] = {t.get("id"): t.get("name") for t in teams}

        event_to_flavor_id: dict[int, str] = {
            event_id: flavor["id"]
            for flavor in flavors
            for event_id in flavor.get("media_event_ids", [])
        }

        parsed_media_events: dict[int, int] = {
            x.get("game_id"): x.get("id") for x in media_events
        }

        for game in data.get("games", {}):
            game_id = game["id"]

            game_time = game["datetime"]

            event_dt = Time.from_str(game_time, timezone="UTC")

            if not start_dt <= event_dt <= end_dt:
                continue

            away = team_identifier.get(game["away_team_id"])
            home = team_identifier.get(game["home_team_id"])

            if not away or not home:
                continue

            event_name = f"{away} vs {home}"
            cache_key = f"[{sport}] {event_name} ({TAG})"
            
            if cache_key in cached_keys:
                continue

            media_id = parsed_media_events.get(game_id, 0)

            if (flavor_id := event_to_flavor_id.get(media_id)) and (
                flavor_id.lower().startswith("free.live")
            ):
                events.append(
                    {
                        "sport": sport,
                        "event": event_name,
                        "timestamp": event_dt.timestamp(),
                        "flavor_id": flavor_id,
                        "media_id": media_id,
                    }
                )
                log.info(f"Found event: {sport} - {event_name} at {event_dt}")

    return events


# ---------------------------------------------------------
# SCRAPER
# ---------------------------------------------------------

async def scrape() -> None:
    cached_urls = CACHE_FILE.load()

    valid_urls = {k: v for k, v in cached_urls.items() if v.get("url")}

    valid_count = cached_count = len(valid_urls)

    urls.update(valid_urls)

    log.info(f"Loaded {cached_count} event(s) from cache")

    log.info('Scraping from "https://mainportal66.com"')

    if events := await get_events(cached_urls.keys()):
        log.info(f"Processing {len(events)} new URL(s)")

        for i, ev in enumerate(events, start=1):
            handler = partial(
                process_event,
                sport=(sport := ev["sport"]),
                flavor_id=ev["flavor_id"],
                media_id=ev["media_id"],
                url_num=i,
            )

            url = await network.safe_process(
                handler,
                url_num=i,
                semaphore=network.PW_S,
                log=log,
            )

            event, ts = ev["event"], ev["timestamp"]

            key = f"[{sport}] {event} ({TAG})"

            tvg_id, logo = leagues.get_tvg_info(sport, event)

            entry = {
                "url": url,
                "logo": logo,
                "base": BASE_URLS[sport],
                "timestamp": ts,
                "id": tvg_id or "Live.Event.us",
            }

            cached_urls[key] = entry

            if url:
                valid_count += 1
                urls[key] = entry
                log.info(f"URL {i}) Stream captured for {sport}: {event}")
            else:
                log.warning(f"URL {i}) No stream found for {sport}: {event}")

        log.info(f"Collected and cached {valid_count - cached_count} new event(s)")

    else:
        log.info("No new events found")

    CACHE_FILE.write(cached_urls)
    
    # Generate playlists after processing
    generate_playlists()


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

async def main():
    log.info("Starting SPORTir updater")
    
    try:
        await scrape()
    except Exception as e:
        log.error(f"Scraping failed: {e}")
        raise
    finally:
        await network.client.aclose()
    
    log.info("SPORTir updater finished")


if __name__ == "__main__":
    asyncio.run(main())
