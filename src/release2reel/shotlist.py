"""Turn highlights into a shot list: one {image_prompt, motion_prompt, overlay_text} per scene.

Two modes:
- Template mode (--no-llm): deterministic prompts from a shared visual grammar.
  Works with only RUNWAYML_API_SECRET set — no second API key required.
- LLM mode (default when ANTHROPIC_API_KEY is set): Claude writes the prompts,
  constrained to a JSON schema. Falls back to templates on any error.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

from .parser import Highlight

# One style descriptor shared by every keyframe keeps the scenes looking like
# frames from the same video instead of three unrelated stock images.
BASE_STYLE = (
    "Minimal isometric 3D illustration, deep indigo background, "
    "soft cyan and magenta neon accents, clean studio lighting, no text, no words"
)

TEMPLATES = {
    "breaking": (
        "large geometric structure splitting cleanly into two parts revealing a glowing new core",
        "slow dramatic dolly-in as the structure separates, particles drifting",
    ),
    "feat": (
        "a glowing translucent module descending and docking into a larger machine assembly",
        "smooth crane shot down as the module clicks into place and lights up",
    ),
    "perf": (
        "streaks of light racing through a translucent pipeline, gauges accelerating",
        "fast lateral tracking shot following the light streaks, subtle motion blur",
    ),
    "fix": (
        "a tangle of glowing cables untangling into one straight clean line",
        "slow orbit around the cables as they resolve, tension releasing",
    ),
    "other": (
        "abstract floating geometric shapes rearranging into an ordered grid",
        "gentle continuous rotation as shapes settle into alignment",
    ),
}

# Keeps drawtext at fontsize 32 safely inside a 1280px frame.
OVERLAY_MAX_CHARS = 48

DEFAULT_LLM_MODEL = os.environ.get("R2R_LLM_MODEL", "claude-opus-5")

SHOTLIST_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "image_prompt": {"type": "string"},
                    "motion_prompt": {"type": "string"},
                    "overlay_text": {"type": "string"},
                },
                "required": ["image_prompt", "motion_prompt", "overlay_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}


@dataclass
class Scene:
    index: int
    highlight: Highlight
    image_prompt: str
    motion_prompt: str
    overlay_text: str


def _overlay(text: str) -> str:
    text = text[0].upper() + text[1:] if text else text
    if len(text) <= OVERLAY_MAX_CHARS:
        return text
    return text[: OVERLAY_MAX_CHARS - 1].rsplit(" ", 1)[0] + "…"


def build_template_shotlist(highlights: list[Highlight]) -> list[Scene]:
    scenes = []
    for i, h in enumerate(highlights):
        subject, motion = TEMPLATES.get(h.kind, TEMPLATES["other"])
        scenes.append(
            Scene(
                index=i,
                highlight=h,
                image_prompt=f"{BASE_STYLE}. Scene: {subject}.",
                motion_prompt=motion,
                overlay_text=_overlay(h.text),
            )
        )
    return scenes


def build_llm_shotlist(highlights: list[Highlight], tag: str, model: str = DEFAULT_LLM_MODEL) -> list[Scene]:
    """Ask Claude for scene prompts; raises on any failure (caller falls back)."""
    import anthropic

    client = anthropic.Anthropic()
    prompt = (
        f"You are writing a shot list for a {len(highlights)}-scene product-update video "
        f"for release {tag}, generated with Runway (gen4_image keyframes animated by gen4.5).\n\n"
        "For each highlight below, write:\n"
        "- image_prompt: a keyframe prompt that visually metaphorizes the highlight. "
        f"Every prompt MUST start with this exact style descriptor so scenes match: \"{BASE_STYLE}\". "
        "No text or lettering in the image.\n"
        "- motion_prompt: one camera/motion direction for a 5-second clip (dolly, orbit, tracking...).\n"
        f"- overlay_text: the highlight rewritten as punchy on-screen copy, max {OVERLAY_MAX_CHARS} chars.\n\n"
        "Highlights (one scene each, same order):\n"
        + "\n".join(f"{i + 1}. [{h.kind}] {h.text}" for i, h in enumerate(highlights))
    )
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        output_config={"format": {"type": "json_schema", "schema": SHOTLIST_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("LLM declined the request")
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    if len(data["scenes"]) != len(highlights):
        raise ValueError(f"LLM returned {len(data['scenes'])} scenes for {len(highlights)} highlights")
    return [
        Scene(
            index=i,
            highlight=h,
            image_prompt=s["image_prompt"],
            motion_prompt=s["motion_prompt"],
            overlay_text=_overlay(s["overlay_text"]),
        )
        for i, (h, s) in enumerate(zip(highlights, data["scenes"]))
    ]


def build_shotlist(highlights: list[Highlight], tag: str, use_llm: bool = True) -> list[Scene]:
    """LLM mode when possible, templates otherwise. Never crashes the pipeline."""
    if use_llm and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return build_llm_shotlist(highlights, tag)
        except Exception as exc:  # any LLM failure degrades to templates
            print(f"warning: LLM shot list failed ({exc}); using template mode", file=sys.stderr)
    return build_template_shotlist(highlights)
