import os
import json
from datetime import datetime

PORTAL_URL = "http://main.light-ott.net"
MAC_ADDRESS = "00:1A:79:17:3e:34"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/tsender57-dotcom/iptv-rox-playlist/main/MyIPTV/channels/" 
OUTPUT_FOLDER = "channels"
MASTER_PLAYLIST = "playlist.m3u"
LOCAL_CHANNELS_FILE = "mac_channels.json"
LOCAL_GENRES_FILE = "mac_genres.json"

def load_genres():
    genre_map = {}
    try:
        with open(LOCAL_GENRES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            genres = data.get("js", [])
            for g in genres:
                if g.get("id") and g.get("title"):
                    genre_map[str(g.get("id"))] = g.get("title")
    except Exception:
        pass
    return genre_map

def process_channels():
    genre_map = load_genres()
    try:
        with open(LOCAL_CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("[!] File JSON tidak ditemukan!")
        return

    channels = data.get("js", {}).get("data", [])
    if not channels: return

    if not os.path.exists(OUTPUT_FOLDER): os.makedirs(OUTPUT_FOLDER)

    with open(MASTER_PLAYLIST, "w", encoding="utf-8") as master_file:
        master_file.write("#EXTM3U\n# ==========================================\n")
        master_file.write("# TYPE: MAC Portal to M3U8 Conversion\n")
        master_file.write(f"# GENERATED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        master_file.write("# ==========================================\n\n")

        counter = 0
        for channel in channels:
            ch_id = str(channel.get("id", ""))
            if not ch_id: continue

            ch_name = channel.get("name", "Unknown Channel").strip()
            ch_logo = channel.get("logo", "")
            ch_group = genre_map.get(str(channel.get("tv_genre_id", "")), "Uncategorized")

            m3u8_content = f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2200000\n{PORTAL_URL}/play/live.php?mac={MAC_ADDRESS}&stream={ch_id}&extension=m3u8\n"
            
            with open(os.path.join(OUTPUT_FOLDER, f"{ch_id}.m3u8"), "w", encoding="utf-8") as f:
                f.write(m3u8_content)

            master_file.write(f'#EXTINF:-1 group-title="{ch_group}" tvg-logo="{ch_logo}", {ch_name}\n')
            master_file.write(f'{GITHUB_RAW_BASE}{ch_id}.m3u8\n')
            counter += 1
            
    print(f"[+] SELESAI KILAT! Memproduksi {counter} file .m3u8")

if __name__ == "__main__":
    process_channels()
