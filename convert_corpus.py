"""
convert_corpus.py
-----------------
Converts gcu_modules_cs_with_details.json into a clean plain-text
corpus file for the RAG pipeline.

Strips navigation noise from the scraped detail pages and extracts
the actual module content (summary, aims, assessment methods).

Run from the rag-chatbot project root:
    python3 convert_corpus.py

Author: Emmanuel Ibenwankwo
"""

import json
import re
from pathlib import Path

INPUT_JSON = "gcu_modules_cs_with_details.json"
OUTPUT_TXT = "data/gcu_modules_corpus.txt"

# Navigation boilerplate that appears on every GCU page — strip everything
# before the first occurrence of any of these markers which signal the
# start of actual module content.
CONTENT_START_MARKERS = [
    "Summary of content",
    "Module aims",
    "Module description",
    "Overview",
    "This module",
    "Students will",
    "The module",
    "This course",
]

# Text that signals the end of useful content (footer/nav starts again)
CONTENT_END_MARKERS = [
    "Contact us",
    "Follow us",
    "Privacy policy",
    "Accessibility",
    "Cookie policy",
    "Terms and conditions",
    "© Glasgow Caledonian",
    "GCU London",
    "Online services",
    "Current students",
    "arrow_forward",
]


def find_content_start(text: str) -> int:
    """Return index where actual module content begins."""
    earliest = len(text)
    for marker in CONTENT_START_MARKERS:
        idx = text.find(marker)
        if idx != -1 and idx < earliest:
            earliest = idx
    return earliest if earliest < len(text) else 0


def find_content_end(text: str, start: int) -> int:
    """Return index where footer/nav noise starts again after content."""
    earliest = len(text)
    for marker in CONTENT_END_MARKERS:
        idx = text.find(marker, start + 200)  # skip at least 200 chars of content
        if idx != -1 and idx < earliest:
            earliest = idx
    return earliest


def clean_detail(raw: str) -> str:
    """Extract and clean the actual module content from a scraped page."""
    if not raw:
        return ""

    start = find_content_start(raw)
    end = find_content_end(raw, start)
    content = raw[start:end]

    # Remove lines that are clearly navigation artifacts
    nav_noise = {
        "arrow_forward", "arrow_back", "menu", "search", "close",
        "home", "share", "print", "expand_more", "expand_less",
        "chevron_right", "chevron_left", "GCU Go", "A-Z directory",
        "Student support", "Exchange and study abroad", "Library",
        "Registration", "Graduation", "Timetables", "Current students",
    }

    lines = content.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        # Skip short navigation-looking lines
        if stripped in nav_noise:
            continue
        if len(stripped) < 4 and not stripped[0].isdigit():
            continue
        cleaned.append(stripped)

    # Collapse multiple blank lines
    result = re.sub(r'\n{3,}', '\n\n', "\n".join(cleaned))
    return result.strip()


def convert():
    modules = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    print(f"Loaded {len(modules)} modules from {INPUT_JSON}")

    lines = []
    lines.append("=" * 70)
    lines.append("GCU MODULE CATALOGUE — MSc Computer Science")
    lines.append("Glasgow Caledonian University")
    lines.append("School of Science & Engineering")
    lines.append("SCQF Level 11 Modules")
    lines.append("Source: https://www.gcu.ac.uk/currentstudents/essentials/modules")
    lines.append("=" * 70)
    lines.append("")

    good = 0
    empty = 0

    for mod in modules:
        title   = mod.get("title", "Unknown")
        code    = mod.get("code", "")
        level   = mod.get("level", "")
        credits = mod.get("credits", "")
        subject = mod.get("subject", "")
        url     = mod.get("url", "")
        raw     = mod.get("detail", "")

        content = clean_detail(raw)

        lines.append(f"MODULE: {title}")
        lines.append(f"Code: {code} | SCQF Level: {level} | Credits: {credits} | Subject: {subject}")
        lines.append(f"URL: {url}")
        lines.append("")

        if content:
            lines.append(content)
            good += 1
        else:
            lines.append("(No detailed content available for this module.)")
            empty += 1

        lines.append("")
        lines.append("-" * 70)
        lines.append("")

    corpus = "\n".join(lines)
    Path(OUTPUT_TXT).write_text(corpus, encoding="utf-8")

    print(f"\nDone.")
    print(f"  Modules with content : {good}")
    print(f"  Modules without      : {empty}")
    print(f"  Output file          : {OUTPUT_TXT}")
    print(f"  Total characters     : {len(corpus):,}")
    print(f"  Estimated chunks     : ~{len(corpus) // 450} (at chunk_size=500)")

    # Preview first module
    print("\n--- Preview (first 600 chars of corpus) ---")
    print(corpus[:600])


if __name__ == "__main__":
    convert()