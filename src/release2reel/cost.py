"""Credit and dollar cost estimation for a run — drives --dry-run.

Pricing verified against https://docs.dev.runwayml.com/guides/pricing/ (2026-07):
credits cost $0.01 each; gen4_image is 5 credits at 720p; gen4.5 image_to_video
is 12 credits per second of output.
"""

from __future__ import annotations

from dataclasses import dataclass

CREDIT_USD = 0.01
GEN4_IMAGE_720P_CREDITS = 5
GEN45_CREDITS_PER_SECOND = 12


@dataclass
class CostEstimate:
    scenes: int
    seconds_per_scene: int
    keyframe_credits: int
    motion_credits: int

    @property
    def total_credits(self) -> int:
        return self.keyframe_credits + self.motion_credits

    @property
    def usd(self) -> float:
        return self.total_credits * CREDIT_USD

    def summary(self) -> str:
        return (
            f"{self.scenes} scenes x {self.seconds_per_scene}s: "
            f"{self.keyframe_credits} credits (keyframes) + {self.motion_credits} credits (motion) "
            f"= {self.total_credits} credits ≈ ${self.usd:.2f}"
        )


def estimate(n_scenes: int, seconds_per_scene: int) -> CostEstimate:
    return CostEstimate(
        scenes=n_scenes,
        seconds_per_scene=seconds_per_scene,
        keyframe_credits=n_scenes * GEN4_IMAGE_720P_CREDITS,
        motion_credits=n_scenes * seconds_per_scene * GEN45_CREDITS_PER_SECOND,
    )
