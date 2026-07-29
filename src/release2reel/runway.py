"""Runway API calls: gen4_image keyframes + gen4.5 motion, with graceful per-scene failure.

Uses the official `runwayml` SDK. Every task uses `.wait_for_task_output()` —
the SDK polls the async task API until the output is ready. A scene that fails
(after one retry) returns None so the pipeline can skip it and still assemble
a partial video, which is a P0 requirement: one bad generation should never
cost you the whole run.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from .shotlist import Scene

IMAGE_MODEL = "gen4_image"
VIDEO_MODEL = "gen4.5"
RATIO = "1280:720"


def make_client():
    """Create a RunwayML client (reads RUNWAYML_API_SECRET from the environment)."""
    from runwayml import RunwayML

    return RunwayML()


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    return dest


def generate_keyframe(client, scene: Scene, style_ref: str | None = None) -> str | None:
    """Generate one keyframe with gen4_image; returns the output URL or None."""
    from runwayml import TaskFailedError

    kwargs: dict = {
        "model": IMAGE_MODEL,
        "prompt_text": scene.image_prompt,
        "ratio": RATIO,
    }
    if style_ref:
        # A shared reference image keeps the palette consistent across scenes.
        kwargs["reference_images"] = [{"uri": style_ref, "tag": "style"}]
        kwargs["prompt_text"] += " In the style of @style."

    for attempt in (1, 2):
        try:
            task = client.text_to_image.create(**kwargs).wait_for_task_output()
            return task.output[0]
        except TaskFailedError as exc:
            print(
                f"warning: keyframe for scene {scene.index + 1} failed "
                f"(attempt {attempt}/2): {getattr(exc, 'task_details', exc)}",
                file=sys.stderr,
            )
    return None


def animate(client, scene: Scene, image_url: str, duration: int) -> str | None:
    """Animate a keyframe with gen4.5 image_to_video; returns the output URL or None."""
    from runwayml import TaskFailedError

    for attempt in (1, 2):
        try:
            task = client.image_to_video.create(
                model=VIDEO_MODEL,
                prompt_image=image_url,
                prompt_text=scene.motion_prompt,
                ratio=RATIO,
                duration=duration,
            ).wait_for_task_output()
            return task.output[0]
        except TaskFailedError as exc:
            print(
                f"warning: motion for scene {scene.index + 1} failed "
                f"(attempt {attempt}/2): {getattr(exc, 'task_details', exc)}",
                file=sys.stderr,
            )
    return None


def generate_scene_clips(
    scenes: list[Scene],
    duration: int,
    workdir: Path,
    style_ref: str | None = None,
) -> list[tuple[Scene, Path]]:
    """Run the keyframe -> motion pipeline for every scene; skip failures with a warning."""
    client = make_client()
    clips: list[tuple[Scene, Path]] = []
    for scene in scenes:
        print(f"scene {scene.index + 1}/{len(scenes)}: generating keyframe ({IMAGE_MODEL})...")
        image_url = generate_keyframe(client, scene, style_ref)
        if image_url is None:
            print(f"warning: skipping scene {scene.index + 1} entirely", file=sys.stderr)
            continue
        print(f"scene {scene.index + 1}/{len(scenes)}: animating {duration}s ({VIDEO_MODEL})...")
        video_url = animate(client, scene, image_url, duration)
        if video_url is None:
            print(f"warning: skipping scene {scene.index + 1} entirely", file=sys.stderr)
            continue
        clip_path = _download(video_url, workdir / f"scene_{scene.index + 1}.mp4")
        clips.append((scene, clip_path))
    return clips
