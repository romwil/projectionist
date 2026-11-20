#!/usr/bin/env bash
# Lane A throwaway: remux one MKV to fMP4 HLS (-c copy) + household WebVTT.
# Not part of the release path. Example used 2026-11-19:
#   rating_key=121986  "3 Ninjas (1992)"  h264 + ac3 + household en.srt
set -euo pipefail

SRC="${1:?Usage: $0 /path/to/file.mkv /path/to/en.srt [out_dir] [seconds]}"
SRT="${2:?}"
OUT="${3:-./tmp/spike-engine-remux}"
SECS="${4:-600}"

rm -rf "$OUT"
mkdir -p "$OUT/av" "$OUT/subs"
cp "$SRT" "$OUT/subs/en.srt"

ffmpeg -y -i "$OUT/subs/en.srt" -t "$SECS" -f webvtt "$OUT/subs/en.vtt"
cat > "$OUT/subs/en.m3u8" <<EOF
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:${SECS}
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:${SECS}.000,
en.vtt
#EXT-X-ENDLIST
EOF

ffmpeg -y -ss 0 -t "$SECS" -i "$SRC" \
  -map 0:v:0 -map 0:a:0 \
  -c copy \
  -f hls -hls_time 6 -hls_playlist_type vod \
  -hls_segment_type fmp4 \
  -hls_fmp4_init_filename init.mp4 \
  -hls_segment_filename "$OUT/av/seg_%04d.m4s" \
  "$OUT/av/stream.m3u8"

cat > "$OUT/master.m3u8" <<'EOF'
#EXTM3U
#EXT-X-VERSION:7
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",DEFAULT=YES,AUTOSELECT=YES,FORCED=NO,LANGUAGE="en",URI="subs/en.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=6000000,CODECS="avc1.640028,ac-3",RESOLUTION=1920x1080,SUBTITLES="subs"
av/stream.m3u8
EOF

echo "Wrote $OUT/master.m3u8"
