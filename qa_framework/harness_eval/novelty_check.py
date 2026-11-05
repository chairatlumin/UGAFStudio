"""Cosine similarity novelty check for deduplication against prior briefs."""


from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import List, Tuple


def _text_to_vector(text: str) -> Counter:
    """Convert text to a word frequency vector."""
    # Normalize: lowercase, remove punctuation, split into words
    text = text.lower()
    text = "".join(
        ch if ch.isalnum() or ch.isspace() else " " for ch in text
    )
    return Counter(text.split())


def _cosine_similarity(vec1: Counter, vec2: Counter) -> float:
    """Compute cosine similarity between two word frequency counters."""
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum(vec1[x] * vec2[x] for x in intersection)

    sum1 = sum(vec1[x] ** 2 for x in vec1) ** 0.5
    sum2 = sum(vec2[x] ** 2 for x in vec2) ** 0.5

    if sum1 == 0 or sum2 == 0:
        return 0.0

    return float(numerator / (sum1 * sum2))


def _extract_title_and_findings(path: Path) -> str:
    """Extract title and key findings from a research brief."""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = path.read_text(encoding="cp1252")
    lines = content.split("\n")

    # Find title (first # header)
    title_section = ""
    findings_section = ""
    in_findings = False

    for line in lines:
        if line.startswith("# ") and not title_section:
            title_section = line[2:]
        if "## Key Findings" in line or "## Findings" in line:
            in_findings = True
            continue
        if in_findings and line.startswith("###"):
            findings_section += line + "\n"
        elif in_findings and line.strip() == "":
            # Continue collecting findings
            pass
        elif in_findings and not line.startswith("#"):
            findings_section += line + "\n"
        if in_findings and line.startswith("#") and not line.startswith("##"):
            break

    # Combine title and findings
    combined = f"{title_section} {findings_section}"
    return combined


def check_novelty(
    current_brief: Path,
    prior_briefs_dir: Path,
    threshold: float = 0.7,
) -> Tuple[bool, List[str]]:
    """Check novelty of current brief vs. prior briefs using cosine similarity.

    Returns: (is_novel, list of overlapping brief names)
    Threshold: >0.7 similarity → flag as potential duplicate
    """
    if not prior_briefs_dir.exists():
        return True, []  # No prior briefs → novel by default

    current_vec = _text_to_vector(_extract_title_and_findings(current_brief))

    overlapping: List[str] = []
    max_similarity = 0.0

    for prior_path in prior_briefs_dir.glob("*.md"):
        prior_vec = _text_to_vector(_extract_title_and_findings(prior_path))
        similarity = _cosine_similarity(current_vec, prior_vec)

        if similarity > threshold:
            overlapping.append(prior_path.name)
        if similarity > max_similarity:
            max_similarity = similarity

    is_novel = len(overlapping) == 0
    return is_novel, overlapping
