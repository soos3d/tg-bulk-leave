"""Parse a CHANGELOG.md section or GitHub release body into ranked highlights."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Ranked highest-impact first. Breaking changes make the best scenes: they are
# the ones people actually need to hear about.
KIND_ORDER = ["breaking", "feat", "perf", "fix", "other"]

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|feature|fix|perf|refactor|docs|chore|ci|build|style|test|revert)"
    r"(?P<scope>\([^)]*\))?(?P<bang>!)?\s*:\s*(?P<desc>.+)$",
    re.IGNORECASE,
)

KEYWORD_KINDS = [
    ("breaking", re.compile(r"\bbreaking(\s+change)?\b|\bBREAKING\b")),
    ("feat", re.compile(r"\b(add(ed|s)?|new|introduc\w+|support(s|ed)? for|launch\w*)\b", re.I)),
    ("perf", re.compile(r"\b(faster|speed\w*|performance|optimi[sz]\w+|reduc\w+ (latency|memory|time)|\d+(\.\d+)?x)\b", re.I)),
    ("fix", re.compile(r"\b(fix(es|ed)?|resolv\w+|correct(s|ed)?|patch\w*|bug)\b", re.I)),
]

BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# Markdown noise we strip from highlight text before it becomes overlay copy.
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
MD_CODE_RE = re.compile(r"`([^`]*)`")
MD_EMPH_RE = re.compile(r"(\*\*|__|\*|_)(.+?)\1")
ISSUE_REF_RE = re.compile(r"\s*\(?(#\d+|[0-9a-f]{7,40})\)?\s*$")


@dataclass
class Highlight:
    text: str          # cleaned, human-readable summary
    kind: str          # breaking | feat | perf | fix | other
    raw: str = ""      # original line, for debugging / LLM context
    rank: int = field(init=False)

    def __post_init__(self) -> None:
        self.rank = KIND_ORDER.index(self.kind)


def _normalize_tag(tag: str) -> str:
    return tag.lstrip("vV").strip()


def _heading_matches_tag(heading: str, tag: str) -> bool:
    want = _normalize_tag(tag)
    found = re.findall(r"\d+(?:\.\d+)*(?:[-.][0-9A-Za-z.]+)?", heading)
    return any(v == want or v.startswith(want + ".") for v in found)


def extract_section(changelog: str, tag: str | None) -> str:
    """Return the section of a CHANGELOG.md for `tag`.

    Falls back to the first versioned section, and then to the whole text —
    a GitHub release body has no version headings and should pass through as-is.
    """
    lines = changelog.splitlines()
    sections: list[tuple[str, int, int, int]] = []  # (heading, level, start, end)
    current: tuple[str, int, int] | None = None
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not m:
            continue
        level, text = len(m.group(1)), m.group(2)
        if not re.search(r"\d+\.\d+", text):
            continue
        if current is not None:
            sections.append((*current, i))
        current = (text, level, i)
    if current is not None:
        sections.append((*current, len(lines)))

    if not sections:
        return changelog

    if tag:
        for heading, _level, start, end in sections:
            if _heading_matches_tag(heading, tag):
                return "\n".join(lines[start + 1 : end])
    heading, _level, start, end = sections[0]
    return "\n".join(lines[start + 1 : end])


def clean_text(line: str) -> str:
    text = line.strip()
    text = MD_LINK_RE.sub(r"\1", text)
    text = MD_CODE_RE.sub(r"\1", text)
    text = MD_EMPH_RE.sub(r"\2", text)
    text = ISSUE_REF_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text


def classify(line: str) -> tuple[str, str]:
    """Return (kind, cleaned_text) for one changelog line."""
    text = clean_text(line)
    m = CONVENTIONAL_RE.match(text)
    if m:
        ctype = m.group("type").lower()
        desc = m.group("desc").strip()
        if m.group("bang"):
            return "breaking", desc
        if ctype in ("feat", "feature"):
            return "feat", desc
        if ctype == "perf":
            return "perf", desc
        if ctype == "fix":
            return "fix", desc
        return "other", desc
    for kind, pattern in KEYWORD_KINDS:
        if pattern.search(text):
            return kind, text
    return "other", text


def parse_highlights(body: str, tag: str | None = None, max_scenes: int = 3) -> list[Highlight]:
    """Parse a changelog (or release body) into the top `max_scenes` highlights."""
    section = extract_section(body, tag)
    lines = [m.group(1) for m in map(BULLET_RE.match, section.splitlines()) if m]
    if not lines:
        # No bullets: fall back to plain non-heading, non-empty lines.
        lines = [
            ln.strip()
            for ln in section.splitlines()
            if ln.strip() and not HEADING_RE.match(ln)
        ]

    highlights = []
    for line in lines:
        kind, text = classify(line)
        if len(text) < 8:  # skip stubs like "misc" or bare links
            continue
        highlights.append(Highlight(text=text, kind=kind, raw=line))

    # Stable sort: impact rank first, original order within a rank.
    highlights.sort(key=lambda h: h.rank)
    return highlights[:max_scenes]
