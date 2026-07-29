from release2reel.cost import estimate


def test_spec_cost_math():
    # The README's headline number: 3 scenes x 5s of gen4.5 + 3 keyframes ≈ $1.95
    cost = estimate(3, 5)
    assert cost.keyframe_credits == 15
    assert cost.motion_credits == 180
    assert cost.total_credits == 195
    assert round(cost.usd, 2) == 1.95


def test_single_short_scene_for_prompt_iteration():
    # The cheap iteration loop: one 2s clip
    cost = estimate(1, 2)
    assert cost.total_credits == 5 + 24


def test_summary_mentions_credits_and_dollars():
    s = estimate(3, 5).summary()
    assert "195 credits" in s
    assert "$1.95" in s
