"""
convert_corpus.py
-----------------
Converts gcu_modules_cs_with_details.json into a rich plain-text
corpus for the RAG pipeline. Structured so key facts (credits, level,
subject) appear explicitly at the top of each module entry so the LLM
can answer factual questions directly from retrieved chunks.

Run from the rag-chatbot project root:
    python3 convert_corpus.py

Author: Emmanuel Ibenwankwo
"""

import json
import re
from pathlib import Path

INPUT_JSON  = "gcu_modules_cs_with_details.json"
OUTPUT_TXT  = "data/gcu_modules_corpus.txt"

CONTENT_START_MARKERS = [
    "Summary of content",
    "Module aims",
    "Module description",
    "Overview",
    "This module",
    "Students will",
    "The module",
    "This course",
    "Aims",
]

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
    "Module details",
    "Syllabus",
]

NAV_NOISE = {
    "arrow_forward", "arrow_back", "menu", "search", "close",
    "home", "share", "print", "expand_more", "expand_less",
    "chevron_right", "chevron_left", "GCU Go", "A-Z directory",
    "Student support", "Exchange and study abroad", "Library",
    "Registration", "Graduation", "Timetables", "Current students",
    "Academic essentials", "Modules", "2024/25 Modules",
    "Policies and procedures", "Student records and documents",
    "Learning Development Centres", "Student attendance monitoring",
}


def find_content_start(text: str) -> int:
    earliest = len(text)
    for marker in CONTENT_START_MARKERS:
        idx = text.find(marker)
        if idx != -1 and idx < earliest:
            earliest = idx
    return earliest if earliest < len(text) else 0


def find_content_end(text: str, start: int) -> int:
    earliest = len(text)
    for marker in CONTENT_END_MARKERS:
        idx = text.find(marker, start + 100)
        if idx != -1 and idx < earliest:
            earliest = idx
    return earliest


def clean_detail(raw: str) -> str:
    if not raw:
        return ""
    start = find_content_start(raw)
    end = find_content_end(raw, start)
    content = raw[start:end]
    lines = content.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if stripped in NAV_NOISE:
            continue
        if len(stripped) < 4 and not stripped[0].isdigit():
            continue
        cleaned.append(stripped)
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

        # Rich structured header so LLM can answer factual questions
        lines.append(f"MODULE: {title}")
        lines.append(f"Module Code: {code}")
        lines.append(f"SCQF Level: {level}")
        lines.append(f"Credits: {credits} credits")
        lines.append(f"Subject Area: {subject}")
        lines.append(f"School: School of Science & Engineering, Glasgow Caledonian University")
        lines.append(f"URL: {url}")
        lines.append("")

        # Explicit fact summary so retrieval always finds key facts
        lines.append(f"Key Facts: The {title} module ({code}) is worth {credits} credits "
                     f"at SCQF Level {level} in the {subject} subject area.")
        lines.append("")

        if content:
            lines.append("Module Description:")
            lines.append(content)
            good += 1
        else:
            lines.append("Module Description: Full description available at the URL above.")
            empty += 1

        lines.append("")
        lines.append("-" * 70)
        lines.append("")

    corpus = "\n".join(lines)
    Path(OUTPUT_TXT).write_text(corpus, encoding="utf-8")

    print(f"\nDone.")
    print(f"  Modules with content : {good}")
    print(f"  Modules without      : {empty}")
    print(f"  Output               : {OUTPUT_TXT}")
    print(f"  Total characters     : {len(corpus):,}")
    print(f"  Estimated chunks     : ~{len(corpus) // 450}")

    print("\n--- Preview (first module) ---")
    print(corpus[:600])


if __name__ == "__main__":
    convert()