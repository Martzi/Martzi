#!/usr/bin/env python3
"""
Fetches publications from the MTMT API for author 10081350 (Marcell Balogh)
and updates index.html with the latest data including citation counts.
"""

import html
import json
import re
import urllib.request
import urllib.error
from collections import defaultdict

AUTHOR_MTID = 10081350
MTMT_API = (
    "https://m2.mtmt.hu/api/publication"
    "?cond=authors;eq;{author_id}"
    "&sort=publishedYear,desc"
    "&size=50"
    "&labelLang=eng"
    "&format=json"
)
INDEX_PATH = "index.html"

# Markers in index.html where generated publications go
MARKER_START = "<!-- PUBLICATIONS_START -->"
MARKER_END = "<!-- PUBLICATIONS_END -->"


def fetch_publications():
    """Fetch all publications from the MTMT API (handles pagination)."""
    publications = []
    page = 1

    while True:
        url = MTMT_API.format(author_id=AUTHOR_MTID) + f"&page={page}"
        print(f"Fetching page {page}: {url}")

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            print(f"Error fetching page {page}: {e}")
            break

        content = data.get("content", [])
        if not content:
            break

        publications.extend(content)

        paging = data.get("paging", {})
        if paging.get("last", True):
            break
        page += 1

    print(f"Fetched {len(publications)} publications total.")
    return publications


def extract_doi(pub):
    """Extract DOI URL from a publication's identifiers."""
    for ident in pub.get("identifiers", []):
        source = ident.get("source", {})
        source_type = source.get("type", {})
        if source_type.get("label") == "DOI":
            return ident.get("realUrl", "")
    return ""


def extract_authors(pub):
    """Build formatted author string with the target author bolded."""
    authorships = sorted(
        [a for a in pub.get("authorships", []) if a.get("authorTyped", False)],
        key=lambda a: a.get("listPosition", 999),
    )

    parts = []
    for a in authorships:
        given = a.get("givenName", "")
        family = a.get("familyName", "")
        # Use first initial + family name
        initial = given[0] + "." if given else ""
        name = f"{initial} {family}".strip()

        # Bold if this is the target author
        author_obj = a.get("author", {})
        if author_obj.get("mtid") == AUTHOR_MTID:
            parts.append(f"<strong>{name}</strong>")
        else:
            parts.append(name)

    return ", ".join(parts)


def clean_journal_title(raw_title):
    """Clean up journal titles that contain ISSN numbers or are ALL CAPS."""
    # Remove ISSN-like patterns (e.g., "2061-2079 2061-2125")
    cleaned = re.sub(r"\s+\d{4}-\d{3}[\dXx](\s+\d{4}-\d{3}[\dXx])*", "", raw_title)
    cleaned = cleaned.strip()

    # If the title is ALL CAPS, convert to Title Case
    if cleaned == cleaned.upper() and len(cleaned) > 5:
        cleaned = cleaned.title()

    return cleaned


def extract_venue(pub):
    """Extract venue/journal name from the publication."""
    # For book chapters (conference papers), use the parent book title
    book = pub.get("book", {})
    if book:
        venue = book.get("title", "")
    else:
        venue = ""

    # For journal articles, use the journal info
    journal = pub.get("journal", {})
    if journal:
        raw = journal.get("title", journal.get("label", venue))
        venue = clean_journal_title(raw)

    # Add volume/issue info for journals
    volume = pub.get("volume", "")
    issue = pub.get("issue", "")
    if volume:
        venue += f", vol. {volume}"
    if issue:
        venue += f", no. {issue}"

    # Add page info
    first_page = pub.get("firstPage", "")
    last_page = pub.get("lastPage", "")
    if first_page and last_page and first_page != last_page:
        venue += f", pp. {first_page}\u2013{last_page}"
    elif first_page and last_page:
        venue += f", p. {first_page}"

    return venue


def get_pub_type(pub):
    """Determine if publication is a journal article or conference paper."""
    sub_type = pub.get("subType", {})
    sub_label = sub_type.get("nameEng", "").lower()

    # Check the main type
    main_type = pub.get("type", {})
    main_label = main_type.get("label", "").lower()

    if "journal" in main_label or pub.get("journal"):
        return "journal"
    if "conference" in sub_label or pub.get("conferencePublication", False):
        return "conference"
    if "book" in main_label:
        # Book chapters that are conference papers
        if "conference" in sub_label:
            return "conference"
        return "journal"

    return "conference"


def get_publisher(pub):
    """Extract publisher info."""
    book = pub.get("book", {})
    if book:
        published_at = book.get("publishedAt", [])
        if published_at:
            city_label = published_at[0].get("label", "")
            country = published_at[0].get("partOf", {}).get("label", "")
            # Check for IEEE-like publishers
            if "Piscataway" in city_label:
                return "IEEE"

    # Check identifiers for IEEE Xplore links
    for ident in pub.get("identifiers", []):
        url = ident.get("realUrl", "")
        if "ieeexplore" in url:
            return "IEEE"
        if "springer" in url:
            return "Springer"

    # Check DOI prefix
    doi = extract_doi(pub)
    if "10.1109" in doi or "10.23919" in doi:
        return "IEEE"
    if "10.1007" in doi:
        return "Springer"
    if "10.36244" in doi:
        return ""

    return ""


def build_html(publications):
    """Generate the publications HTML grouped by year."""
    # Group by year
    by_year = defaultdict(list)
    for pub in publications:
        year = pub.get("publishedYear", 0)
        if year:
            by_year[year].append(pub)

    html_parts = []

    # Base indentation: 12 spaces (inside .main > section > .container)
    I = "            "  # 12 spaces

    for year in sorted(by_year.keys(), reverse=True):
        html_parts.append(f'{I}<div class="year-group">')
        html_parts.append(f'{I}    <div class="year-label">{year}</div>')
        html_parts.append("")

        for pub in by_year[year]:
            title = html.escape(pub.get("title", "Unknown Title"))
            doi_url = extract_doi(pub)
            authors = extract_authors(pub)
            venue = html.escape(extract_venue(pub))
            pub_type = get_pub_type(pub)
            publisher = get_publisher(pub)
            # Use citingPubCount as the total
            citing_total = pub.get("citingPubCount", 0)

            badge_class = "badge-journal" if pub_type == "journal" else "badge-conference"
            badge_label = "Journal" if pub_type == "journal" else "Conference"

            # Title with or without DOI link
            if doi_url:
                title_html = f'<a href="{doi_url}" target="_blank" rel="noopener">{title}</a>'
            else:
                title_html = title

            html_parts.append(f'{I}    <div class="pub-item">')
            html_parts.append(f'{I}        <div class="pub-title">')
            html_parts.append(f"{I}            {title_html}")
            html_parts.append(f"{I}        </div>")
            html_parts.append(
                f'{I}        <div class="pub-authors">{authors}</div>'
            )
            html_parts.append(
                f'{I}        <div class="pub-venue">{venue}</div>'
            )

            # Meta line
            meta_parts = [
                f'<span class="pub-badge {badge_class}">{badge_label}</span>'
            ]
            if publisher:
                meta_parts.append(f"<span>{publisher}</span>")
            if citing_total > 0:
                meta_parts.append(
                    f'<span class="badge-citations">Cited by {citing_total}</span>'
                )

            html_parts.append(f'{I}        <div class="pub-meta">')
            for mp in meta_parts:
                html_parts.append(f"{I}            {mp}")
            html_parts.append(f"{I}        </div>")
            html_parts.append(f"{I}    </div>")
            html_parts.append("")

        html_parts.append(f"{I}</div>")
        html_parts.append("")

    return "\n".join(html_parts)


def update_index(publications_html):
    """Replace the publications section in index.html."""
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END)
    replacement = (
        MARKER_START + "\n" + publications_html + "\n        " + MARKER_END
    )

    new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

    if count == 0:
        print("ERROR: Could not find publication markers in index.html!")
        print(f"Looking for: {MARKER_START} ... {MARKER_END}")
        return False

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated index.html ({count} replacement(s) made).")
    return True


def main():
    print("Fetching publications from MTMT...")
    publications = fetch_publications()

    if not publications:
        print("No publications found. Exiting without changes.")
        return

    print(f"\nProcessing {len(publications)} publications...")
    publications_html = build_html(publications)

    print("\nUpdating index.html...")
    success = update_index(publications_html)

    if success:
        print("Done! Publications updated successfully.")
    else:
        print("Failed to update index.html.")
        exit(1)


if __name__ == "__main__":
    main()
