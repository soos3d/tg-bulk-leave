"""ffmpeg assembly: title card + per-scene text overlays + concat + GIF export."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .shotlist import Scene

SIZE = "1280x720"
FPS = 24
TITLE_SECONDS = 2.5

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def find_font() -> str | None:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None  # drawtext falls back to fontconfig's default


def _escape(text: str) -> str:
    """Escape text for ffmpeg drawtext (its parser is famously picky)."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "’")  # typographic apostrophe avoids quoting hell
        .replace("%", "\\%")
        .replace(",", "\\,")
    )


def _drawtext(text: str, *, font: str | None, fontsize: int, x: str, y: str,
              alpha: float = 1.0, box: bool = False) -> str:
    parts = [
        f"text='{_escape(text)}'",
        f"fontsize={fontsize}",
        f"fontcolor=white@{alpha}",
        f"x={x}",
        f"y={y}",
    ]
    if font:
        parts.append(f"fontfile={font}")
    if box:
        parts.append("box=1:boxcolor=black@0.45:boxborderw=18")
    return "drawtext=" + ":".join(parts)


def make_title_card(tag: str, project: str, dest: Path, font: str | None) -> Path:
    filters = ",".join(
        [
            _drawtext(project, font=font, fontsize=64, x="(w-text_w)/2", y="(h-text_h)/2-50"),
            _drawtext(tag, font=font, fontsize=44, x="(w-text_w)/2", y="(h-text_h)/2+40", alpha=0.85),
            "fade=t=in:st=0:d=0.4,fade=t=out:st=2.1:d=0.4",
        ]
    )
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c=0x101030:s={SIZE}:d={TITLE_SECONDS}",
        "-vf", filters,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        str(dest),
    )
    return dest


def overlay_scene(scene: Scene, clip: Path, tag: str, dest: Path, font: str | None) -> Path:
    filters = ",".join(
        [
            f"scale={SIZE.replace('x', ':')},fps={FPS}",
            _drawtext(scene.overlay_text, font=font, fontsize=32,
                      x="(w-text_w)/2", y="h-th-64", box=True),
            _drawtext(tag, font=font, fontsize=24, x="w-text_w-28", y="24", alpha=0.7),
            "fade=t=in:st=0:d=0.3",
        ]
    )
    _ffmpeg("-i", str(clip), "-vf", filters,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(dest))
    return dest


def concat(clips: list[Path], dest: Path) -> Path:
    list_file = dest.with_suffix(".txt")
    list_file.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest))
    list_file.unlink()
    return dest


def export_gif(video: Path, dest: Path, width: int = 640, fps: int = 12) -> Path:
    palette = dest.with_suffix(".palette.png")
    _ffmpeg("-i", str(video), "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,palettegen", str(palette))
    _ffmpeg("-i", str(video), "-i", str(palette),
            "-lavfi", f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse", str(dest))
    palette.unlink()
    return dest


def assemble(
    scene_clips: list[tuple[Scene, Path]],
    tag: str,
    project: str,
    out_dir: Path,
    workdir: Path,
    gif: bool = True,
) -> tuple[Path, Path | None]:
    """Overlay, title-card, and stitch scene clips into out_dir/<tag>.mp4 (+ .gif)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH — install it (e.g. `apt install ffmpeg` / `brew install ffmpeg`)")
    out_dir.mkdir(parents=True, exist_ok=True)
    font = find_font()

    pieces = [make_title_card(tag, project, workdir / "title.mp4", font)]
    for scene, clip in scene_clips:
        pieces.append(overlay_scene(scene, clip, tag, workdir / f"overlay_{scene.index + 1}.mp4", font))

    video = concat(pieces, out_dir / f"{tag}.mp4")
    gif_path = export_gif(video, out_dir / f"{tag}.gif") if gif else None
    return video, gif_path
