"""End-to-end test of the full pipeline in --mock mode (needs ffmpeg, no API keys)."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

EXAMPLE = Path(__file__).parent.parent / "examples" / "CHANGELOG.md"


def test_mock_run_produces_video_and_gif(tmp_path):
    subprocess.run(
        [
            "release2reel", str(EXAMPLE),
            "--tag", "v2.1.0", "--project", "example",
            "--mock", "--no-llm", "--seconds", "2",
            "--out", str(tmp_path),
        ],
        check=True,
        capture_output=True,
    )
    video = tmp_path / "v2.1.0.mp4"
    gif = tmp_path / "v2.1.0.gif"
    assert video.exists() and video.stat().st_size > 0
    assert gif.exists() and gif.stat().st_size > 0

    # 3 scenes x 2s + 2.5s title card, and ≤ 30s per the P0 requirement
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        check=True, capture_output=True, text=True,
    )
    duration = float(probe.stdout.strip())
    assert 7.0 <= duration <= 30.0


def test_dry_run_spends_nothing_and_prints_cost(tmp_path):
    result = subprocess.run(
        ["release2reel", str(EXAMPLE), "--tag", "v2.1.0", "--dry-run", "--no-llm"],
        check=True, capture_output=True, text=True,
    )
    assert "estimated cost" in result.stdout
    assert "credits" in result.stdout
    assert not list(tmp_path.iterdir())
