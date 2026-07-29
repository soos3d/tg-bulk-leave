"""release2reel CLI: one command from changelog to video."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .cost import estimate
from .parser import parse_highlights
from .shotlist import build_shotlist


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="release2reel",
        description="Turn release notes into a product-update video with the Runway API.",
    )
    p.add_argument("changelog", nargs="?", default="CHANGELOG.md",
                   help="Path to CHANGELOG.md or a release-body text file; '-' reads stdin (default: CHANGELOG.md)")
    p.add_argument("--tag", required=True, help="Release tag, e.g. v2.1.0 — used to select the changelog section and name outputs")
    p.add_argument("--project", default=None, help="Project name for the title card (default: current directory name)")
    p.add_argument("--scenes", type=int, default=3, help="Max scenes / highlights (default: 3)")
    p.add_argument("--seconds", type=int, default=5, choices=range(2, 11), metavar="2-10",
                   help="Seconds per scene (default: 5)")
    p.add_argument("--out", type=Path, default=Path("out"), help="Output directory (default: out/)")
    p.add_argument("--style-ref", default=None,
                   help="URL of a brand image passed to gen4_image as a style reference for every keyframe")
    p.add_argument("--no-llm", action="store_true",
                   help="Use deterministic prompt templates instead of an LLM for the shot list")
    p.add_argument("--no-gif", action="store_true", help="Skip the README-embeddable GIF export")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the shot list and estimated credit cost, spend nothing")
    p.add_argument("--mock", action="store_true",
                   help="Generate placeholder clips locally with ffmpeg — full pipeline, zero API calls")
    p.add_argument("--version", action="version", version=f"release2reel {__version__}")
    return p


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    if not p.exists():
        sys.exit(f"error: input file not found: {p}")
    return p.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    body = read_input(args.changelog)
    project = args.project or Path.cwd().resolve().name

    highlights = parse_highlights(body, tag=args.tag, max_scenes=args.scenes)
    if not highlights:
        sys.exit(f"error: no highlights found for {args.tag} — check the tag matches a changelog section")

    scenes = build_shotlist(highlights, tag=args.tag, use_llm=not args.no_llm)
    cost = estimate(len(scenes), args.seconds)

    print(f"\nrelease2reel — {project} {args.tag}")
    print(f"shot list ({len(scenes)} scenes):")
    for s in scenes:
        print(f"\n  scene {s.index + 1} [{s.highlight.kind}] — {s.overlay_text}")
        print(f"    image : {s.image_prompt}")
        print(f"    motion: {s.motion_prompt}")
    print(f"\nestimated cost: {cost.summary()}\n")

    if args.dry_run:
        print("dry run: nothing generated, nothing spent.")
        return

    with tempfile.TemporaryDirectory(prefix="release2reel-") as tmp:
        workdir = Path(tmp)
        if args.mock:
            from .mock import generate_scene_clips

            scene_clips = generate_scene_clips(scenes, args.seconds, workdir)
        else:
            if not os.environ.get("RUNWAYML_API_SECRET"):
                sys.exit(
                    "error: RUNWAYML_API_SECRET is not set.\n"
                    "Get a key at https://dev.runwayml.com — or try --mock / --dry-run first."
                )
            from .runway import generate_scene_clips

            scene_clips = generate_scene_clips(scenes, args.seconds, workdir, style_ref=args.style_ref)

        if not scene_clips:
            sys.exit("error: every scene failed to generate — nothing to assemble")
        if len(scene_clips) < len(scenes):
            print(f"warning: assembling partial video with {len(scene_clips)}/{len(scenes)} scenes",
                  file=sys.stderr)

        from .assemble import assemble

        video, gif = assemble(scene_clips, args.tag, project, args.out, workdir, gif=not args.no_gif)

    print(f"\ndone: {video}")
    if gif:
        print(f"      {gif}")


if __name__ == "__main__":
    main()
