from pathlib import Path

from release2reel.parser import classify, extract_section, parse_highlights

EXAMPLE = (Path(__file__).parent.parent / "examples" / "CHANGELOG.md").read_text()


def test_extract_section_by_tag():
    section = extract_section(EXAMPLE, "v2.1.0")
    assert "streaming mode" in section
    assert "Apple Silicon" not in section


def test_extract_section_tag_without_v_prefix():
    assert "streaming mode" in extract_section(EXAMPLE, "2.1.0")


def test_extract_section_falls_back_to_first_section():
    assert "streaming mode" in extract_section(EXAMPLE, None)


def test_release_body_without_headings_passes_through():
    body = "- Added dark mode\n- Fixed login crash\n"
    assert extract_section(body, "v1.0.0") == body


def test_classify_conventional_commits():
    assert classify("feat: add dark mode") == ("feat", "add dark mode")
    assert classify("fix(api): handle nulls") == ("fix", "handle nulls")
    assert classify("perf: 2x faster startup") == ("perf", "2x faster startup")
    assert classify("feat!: drop Python 3.8") == ("breaking", "drop Python 3.8")


def test_classify_keywords():
    kind, _ = classify("Added support for webhooks")
    assert kind == "feat"
    kind, _ = classify("Fixed a crash on startup")
    assert kind == "fix"
    kind, _ = classify("Transcoding is now 3.2x faster")
    assert kind == "perf"


def test_classify_strips_markdown():
    kind, text = classify("fix: resolved race condition ([#142](https://github.com/x/y/issues/142))")
    assert kind == "fix"
    assert "http" not in text
    assert "#142" not in text


def test_parse_highlights_ranks_and_caps():
    highlights = parse_highlights(EXAMPLE, tag="v2.1.0", max_scenes=3)
    assert len(highlights) == 3
    # feat outranks fix; order of kinds must be non-decreasing impact rank
    ranks = [h.rank for h in highlights]
    assert ranks == sorted(ranks)
    assert highlights[0].kind == "feat"


def test_parse_highlights_breaking_first():
    highlights = parse_highlights(EXAMPLE, tag="v2.0.0", max_scenes=3)
    assert highlights[0].kind == "breaking"
