# Safari stops after the opening burst

2026-11-20, QA `http://10.10.1.202:8792` running the Hub image `1.41.1`. The title is Purgatory, rating key `238445`, duration 5,664,749 ms, file size 1,932,120,688 bytes. Plex's universal-start parameters were not changed (`protocol=hls`, `directPlay=0`, `directStream=1`, and the rest of that request).

The Apple-client notes for the same symptom are in the private client repo at `Projectionist.iOS/docs/specs/2026-11-20-playback-stall.md`. That file is for the client lane to update. This note is the server evidence.

## What the master advertises

On 1.41.1 the master playlist for this title is one variant:

`BANDWIDTH=3410779,AVERAGE-BANDWIDTH=3410779`

Both numbers are the container average plus 25 percent. The container average is about 2.73 Mbps. 1.41.0 advertised `BANDWIDTH=2723000`.

The media playlist is a full VOD list: 567 segments, `#EXT-X-TARGETDURATION:10`, `#EXT-X-ENDLIST`. A logged size near 2,000 bytes is that playlist gzip-compressed (the raw list is 93,648 bytes). It is not a short playlist.

## Safari on QA

A local proxy added the household session cookie, because Safari does not send a device bearer. One clean session, with no second play started until after the pause:

| Time | Request | Result |
|--|--|--|
| 20:41:02 | master `index.m3u8` | 200, 225 bytes |
| 20:41:02 | media playlist | 200, gzip size 1,969 bytes |
| 20:41:03 | `00009.ts` | 200, 5,747,912 bytes (about 4.60 Mbps for 10 seconds) |
| 20:41:03 | `00010.ts` | 200, 402,320 bytes (about 0.32 Mbps) |
| 20:41:06 | `00011.ts` | 200, 4,497,900 bytes (about 3.60 Mbps) |
| 20:41:06 | progress | 200 |

Nothing else from Safari for the next 80 seconds. `00009.ts` and `00011.ts` are above the advertised 3.41 Mbps. Playback had resumed near 90 seconds, so the burst started at `00009.ts` rather than `00000.ts`.

The next segment, `00012.ts`, was requested by hand on that same session after the silence. It returned 200 and 3,802,112 bytes. The server had the segment. Safari had not asked for it.

## Chrome on the same QA build

The same proxy, in Chromium, kept requesting past the opening burst (`00000.ts` through at least `00015.ts`, all 200) and the picture advanced (about 30 seconds in, not paused). Chrome does not stop where Safari stops.

## Plex at the moment Safari had stopped

The Purgatory session was still `playing`. Video decision `copy`, audio decision `copy` (direct stream, not a transcode falling behind). Plex's own bitrate field was 2723 kbps, the container average. `throttled` was true and `speed` was 0, which is Plex waiting because the client had stopped pulling. The session had not timed out.

## Prod 1.40.1

Safari opened `http://10.10.1.202:8788/watch/238445`. The page loaded. `POST /api/library/playback/start` returned 401. Safari was not signed in on production, and nothing on that server was changed. Segment behavior on 1.40.1 was not measured.

## Root cause

Safari stops scheduling segment requests when a segment's bitrate exceeds the variant `BANDWIDTH`. Our master sets `BANDWIDTH` and `AVERAGE-BANDWIDTH` to the same number, the container average plus 25 percent, and real segments run higher than that (about 4.6–5.2 Mbps in the opening burst against 3.41 Mbps advertised). The next segment is available. The Plex session is a throttled direct stream, not a dead transcode.

`BANDWIDTH` has to be the measured peak segment bitrate plus a margin. `AVERAGE-BANDWIDTH` stays the container average.

## What a HEAD of the segments shows

After the media playlist exists, `HEAD` of a segment Plex has already written returns `Content-Length` (the opening segment was 5,929,332 bytes). `HEAD` of a segment Plex has not written returns 404. A HEAD of all 567 segments took about 18 seconds: about 42 returned a length and about 520 did not. The largest one that existed was segment 38, 8,252,260 bytes, about 6.60 Mbps. The master request measures the first 48 segments, which covers that segment, and does not wait on the 404s.
