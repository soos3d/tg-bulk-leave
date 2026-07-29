from release2reel.parser import Highlight
from release2reel.shotlist import BASE_STYLE, OVERLAY_MAX_CHARS, build_shotlist, build_template_shotlist


def _highlights():
    return [
        Highlight(text="streaming mode for video chunks", kind="feat"),
        Highlight(text="transcoding is now 3.2x faster", kind="perf"),
        Highlight(text="resolved a race condition dropping the final frame", kind="fix"),
    ]


def test_template_shotlist_shares_style():
    scenes = build_template_shotlist(_highlights())
    assert len(scenes) == 3
    for s in scenes:
        assert s.image_prompt.startswith(BASE_STYLE)
        assert s.motion_prompt
        assert s.overlay_text


def test_overlay_text_truncated():
    long = Highlight(text="a" * 200, kind="feat")
    scene = build_template_shotlist([long])[0]
    assert len(scene.overlay_text) <= OVERLAY_MAX_CHARS


def test_overlay_capitalized():
    scene = build_template_shotlist([Highlight(text="streaming mode", kind="feat")])[0]
    assert scene.overlay_text[0].isupper()


def test_build_shotlist_without_llm_key_uses_templates(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    scenes = build_shotlist(_highlights(), tag="v1.0.0", use_llm=True)
    assert scenes[0].image_prompt.startswith(BASE_STYLE)
