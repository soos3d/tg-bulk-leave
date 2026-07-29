"""--mock mode: locally generated placeholder clips instead of Runway API calls.

Runs the entire pipeline (parse -> shot list -> overlays -> stitch -> gif)
with zero credits and zero API keys. Useful for trying the tool, testing the
assembly step, and CI.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .shotlist import Scene

# One dark gradient pair per scene index so mock scenes are visually distinct.
SCENE_COLORS = [
    ("0x1a1a4e", "0x0d2137"),
    ("0x2d1b4e", "0x1a0d37"),
    ("0x0d3a3a", "0x122a4e"),
    ("0x3a1d2d", "0x1a1a4e"),
]


def generate_mock_clip(scene: Scene, dest: Path, duration: int, size: str = "1280x720") -> Path:
    c0, c1 = SCENE_COLORS[scene.index % len(SCENE_COLORS)]
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"gradients=s={size}:d={duration}:c0={c0}:c1={c1}:speed=0.02",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24",
            str(dest),
        ],
        check=True,
    )
    return dest


def generate_scene_clips(scenes: list[Scene], duration: int, workdir: Path) -> list[tuple[Scene, Path]]:
    clips = []
    for scene in scenes:
        print(f"scene {scene.index + 1}/{len(scenes)}: generating mock clip (no API call)...")
        clips.append((scene, generate_mock_clip(scene, workdir / f"scene_{scene.index + 1}.mp4", duration)))
    return clips
