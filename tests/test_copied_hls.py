"""Copied H.264 segments must start on an IDR, or VideoToolbox rejects them.

An open GOP marks a recovery point as a keyframe. The HLS muxer then starts
a segment on a non-IDR slice. Decoding that segment alone reports a missing
reference (``mmco: unref short failure``), which Chrome surfaces as
PIPELINE_ERROR_DECODE / -12909. Grouping fragments onto the previous IDR
removes that break.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from projectionist.engine.audio import audio_transcode_command
from projectionist.engine.copied_hls import fragment_starts_on_idr, pack_copied_hls


def _fragment(nal: int) -> bytes:
    payload = bytes((nal, 0x88))
    body = len(payload).to_bytes(4, "big") + payload
    mdat = (len(body) + 8).to_bytes(4, "big") + b"mdat" + body
    moof = (8).to_bytes(4, "big") + b"moof"
    return moof + mdat


class IdrFragmentTests(unittest.TestCase):
    def test_an_idr_starts_a_segment_and_a_recovery_point_does_not(self) -> None:
        self.assertTrue(fragment_starts_on_idr(_fragment(5), "h264"))
        self.assertFalse(fragment_starts_on_idr(_fragment(1), "h264"))
        sei = (2).to_bytes(4, "big") + bytes((6, 0x01))
        idr = (2).to_bytes(4, "big") + bytes((5, 0x00))
        body = sei + idr
        mdat = (len(body) + 8).to_bytes(4, "big") + b"mdat" + body
        self.assertTrue(fragment_starts_on_idr(b"\x00\x00\x00\x08moof" + mdat, "h264"))
        recovery = (2).to_bytes(4, "big") + bytes((6, 0x01)) + (2).to_bytes(4, "big") + bytes((1, 0x00))
        mdat = (len(recovery) + 8).to_bytes(4, "big") + b"mdat" + recovery
        self.assertFalse(fragment_starts_on_idr(b"\x00\x00\x00\x08moof" + mdat, "h264"))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is required")
class OpenGopSegmentTests(unittest.TestCase):
    def test_open_gop_segments_start_on_idr_and_decode(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        assert ffmpeg and ffprobe
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "open.mkv"
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=duration=24:size=160x90:rate=24",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000:duration=24",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-g",
                    "240",
                    "-keyint_min",
                    "48",
                    "-bf",
                    "2",
                    "-x264-params",
                    "open-gop=1",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(source),
                ],
                check=True,
            )
            broken = root / "broken"
            broken.mkdir()
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-f",
                    "hls",
                    "-hls_time",
                    "6",
                    "-hls_playlist_type",
                    "event",
                    "-hls_segment_type",
                    "fmp4",
                    "-hls_fmp4_init_filename",
                    "init.mp4",
                    "-hls_segment_filename",
                    "seg_%04d.m4s",
                    "stream.m3u8",
                ],
                check=True,
                cwd=broken,
            )
            broken_segments = sorted(broken.glob("seg_*.m4s"))
            self.assertGreaterEqual(len(broken_segments), 2)
            self.assertFalse(fragment_starts_on_idr(broken_segments[1].read_bytes(), "h264"))
            packed = root / "packed"
            packed.mkdir()
            command = audio_transcode_command(ffmpeg, source, "aac", output="frag")
            pack_copied_hls(packed, command, video_codec="h264", ffprobe=ffprobe)
            segments = sorted(packed.glob("seg_*.m4s"))
            self.assertGreaterEqual(len(segments), 1)
            playlist = (packed / "stream.m3u8").read_text(encoding="utf-8")
            self.assertIn("#EXT-X-ENDLIST", playlist)
            previous_end = None
            for segment in segments:
                self.assertTrue(self._starts_with_idr(packed / "init.mp4", segment))
                start, end, err, code = self._decode(packed / "init.mp4", segment)
                self.assertNotIn("unref short failure", err)
                self.assertNotIn("Decoding error", err)
                self.assertEqual(code, 0)
                if previous_end is not None:
                    self.assertGreaterEqual(start + 0.05, previous_end - 0.2)
                    self.assertLess(start - previous_end, 0.5)
                previous_end = end

    def _starts_with_idr(self, init: Path, segment: Path) -> bool:
        return fragment_starts_on_idr(init.read_bytes() + segment.read_bytes(), "h264") or fragment_starts_on_idr(
            segment.read_bytes(), "h264"
        )

    def _decode(self, init: Path, segment: Path) -> tuple[float, float, str, int]:
        combo = segment.with_suffix(".check.mp4")
        combo.write_bytes(init.read_bytes() + segment.read_bytes())
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "packet=pts_time",
                "-of",
                "csv=p=0",
                str(combo),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        times = [float(line) for line in (probe.stdout or "").splitlines() if line.strip()]
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(combo), "-f", "null", "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        start = times[0] if times else 0.0
        end = times[-1] if times else start
        return start, end, decoded.stderr or "", int(decoded.returncode)

if __name__ == "__main__":
    unittest.main()
