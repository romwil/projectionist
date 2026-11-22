# Playback fixtures

Automated playback uses generated clips and Google Chrome. It does not use a household server, and it does not use Plex.

Run it from the repo root:

```bash
npm run test:e2e:playback
```

Playwright starts `node scripts/start-playback-fixture-e2e.mjs` on **port 8799**. That script generates the clips with ffmpeg, then starts the app with `PROJECTIONIST_FIXTURE_MEDIA_DIR` set. The fixture media source reads those files. Pull requests that touch playback run this on GitHub and install Google Chrome in that job when the runner does not already have it.

Each clip is **48 seconds** of real picture and sound (320×240, generated, not committed). That is long enough to seek and long enough for the playhead to pass 30 seconds. After the first frame, the H.264/AAC test sets `playbackRate` to 4 so the playhead covers those 30 seconds in less wall-clock time. The assertion is `video.currentTime`, on a file whose duration is actually over 30 seconds.

## What each fixture asserts

The planned tier is the session `plan` for the profile this Chrome sent.

| Clip | Planned tier on Chrome |
|------|------------------------|
| MP4 H.264/AAC | `direct` |
| MKV H.264/AAC | `remux` |
| MKV H.264 + FLAC + SRT | `remux` when this Chrome reports FLAC, otherwise `audio` |
| H.264 + TrueHD | `audio` |
| H.264 + DTS 5.1 | `audio` |
| H.264 + E-AC-3 | `remux` when this Chrome reports E-AC-3, otherwise `audio` |
| MPEG-2 | `source-transcode` from the fixture source (`playable` false) |

The H.264/AAC MP4 play in Chrome also asserts: a first frame within 10 seconds, the playhead past 30 seconds, and a seek near the end that keeps playing. No library playback start runs during that play.

The FLAC clip's SRT cue is the sentence `FIXTURE CUE NORTH WINDOW`, from half a second to eight seconds. The test asserts that cue is showing on the video's text track. The title language is Japanese and the cached caption is English, so the engine selects that track.

TrueHD is requested as 7.1. ffmpeg's TrueHD encoder only writes layouts through 5.1(side). When 7.1 is refused, the file is 6-channel TrueHD and `catalog.json` says so. DTS is 6 channels; ffprobe often labels that layout `5.1(side)`. Neither difference changes the tier: those codecs are not in the browser profile, so the plan is `audio`.

## Manual checklist: HEVC and Safari

HEVC and Safari are not part of the automated run. The GitHub job has Google Chrome, not Safari, and a Linux Chrome HEVC answer is not the household Safari check.

On a Mac, with Play through Projectionist on, before a playback change is treated as done:

1. **Safari, H.264/AAC.** A picture appears within 10 seconds, playback passes 30 seconds, and a seek near the end shows a new picture.
2. **Safari, HEVC** that this Safari reports it can play. The session plan is `remux` or `try`, a picture appears, and a seek works. A `source-transcode` plan means this Safari did not report that HEVC file. Leave it on the media source. Do not score that as a Chrome failure.
3. **Chrome, HEVC.** Read the session plan and compare it to the profile Chrome sent. Assert nothing about HEVC in the fixture job.
4. **Safari captions.** A known text cue is visible in fullscreen, not only in the windowed page.
