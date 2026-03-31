import argparse
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.vlr.gg"
USER_AGENT = (
    "Mozilla/5.0 (compatible; VLRDataScraper/1.0; +https://example.com/bot-contact)"
)


@dataclass
class MatchRow:
    scraped_at_utc: str
    source_section: str
    team_1: str
    team_2: str
    score_1: Optional[int]
    score_2: Optional[int]
    event_name: str
    event_stage: str
    match_datetime_text: str
    match_status: str
    relative_url: str
    absolute_url: str


@dataclass
class EventRow:
    scraped_at_utc: str
    section: str
    event_name: str
    region: str
    time_range: str


@dataclass
class NewsRow:
    scraped_at_utc: str
    date_bucket: str
    title: str
    comments_count: Optional[int]
    relative_url: str
    absolute_url: str


def clean_text(value: str) -> str:
    return " ".join(value.split()) if value else ""


def parse_int(value: str) -> Optional[int]:
    if not value:
        return None
    m = re.search(r"\d+", value)
    return int(m.group(0)) if m else None


def fetch_homepage(session: requests.Session, delay_seconds: float) -> str:
    headers = {"User-Agent": USER_AGENT}
    response = session.get(BASE_URL, headers=headers, timeout=20)
    response.raise_for_status()
    time.sleep(delay_seconds)
    return response.text


def parse_matches(soup: BeautifulSoup, scraped_at_utc: str) -> List[MatchRow]:
    rows: List[MatchRow] = []
    cards = soup.select("a.wf-module-item.mod-match")
    for card in cards:
        card_text = clean_text(card.get_text(" ", strip=True))
        relative_url = card.get("href", "")
        if relative_url.startswith("/"):
            absolute_url = f"{BASE_URL}{relative_url}"
        elif relative_url:
            absolute_url = f"{BASE_URL}/{relative_url}"
        else:
            absolute_url = ""

        team_names = [clean_text(x.get_text(" ", strip=True)) for x in card.select(".h-match-team-name")]
        if len(team_names) < 2:
            # Some cards are not standard match cards; skip to keep clean data.
            continue

        score_nodes = [clean_text(x.get_text(" ", strip=True)) for x in card.select(".h-match-team-score")]
        score_1 = parse_int(score_nodes[0]) if len(score_nodes) > 0 else None
        score_2 = parse_int(score_nodes[1]) if len(score_nodes) > 1 else None

        event_name = clean_text(
            card.select_one(".h-match-preview-event").get_text(" ", strip=True)
        ) if card.select_one(".h-match-preview-event") else ""
        event_stage = clean_text(
            card.select_one(".h-match-preview-series").get_text(" ", strip=True)
        ) if card.select_one(".h-match-preview-series") else ""

        datetime_text = ""
        datetime_node = card.select_one(".h-match-preview-time")
        if datetime_node:
            datetime_text = clean_text(datetime_node.get_text(" ", strip=True))

        status = "unknown"
        lowered = card_text.lower()
        if "live" in lowered:
            status = "live"
        elif score_1 is not None or score_2 is not None:
            status = "completed"
        elif datetime_text:
            status = "upcoming"

        if status == "upcoming":
            source_section = "upcoming"
        elif status == "completed":
            source_section = "completed"
        elif status == "live":
            source_section = "live"
        else:
            source_section = "homepage_card"

        rows.append(
            MatchRow(
                scraped_at_utc=scraped_at_utc,
                source_section=source_section,
                team_1=team_names[0],
                team_2=team_names[1],
                score_1=score_1,
                score_2=score_2,
                event_name=event_name,
                event_stage=event_stage,
                match_datetime_text=datetime_text,
                match_status=status,
                relative_url=relative_url,
                absolute_url=absolute_url,
            )
        )
    return rows


def parse_events(soup: BeautifulSoup, scraped_at_utc: str) -> List[EventRow]:
    rows: List[EventRow] = []
    section_titles = {
        "live Events": "live_events",
        "ongoing Events": "ongoing_events",
        "upcoming Events": "upcoming_events",
        "completed Events": "completed_events",
    }

    for section_title_text, section_key in section_titles.items():
        title = soup.find(string=re.compile(rf"^\s*{re.escape(section_title_text)}\s*$", re.I))
        if not title:
            continue

        container = title.find_parent()
        if not container:
            continue

        sibling = container.find_next_sibling()
        if not sibling:
            continue

        raw = clean_text(sibling.get_text(" ", strip=True))
        if not raw:
            continue

        # Conservative parser: event rows are often "Name REGION DateRange".
        # We split on likely boundaries with 2+ spaces from rendered text.
        chunks = re.split(r"\s{2,}", raw)
        for chunk in chunks:
            chunk = clean_text(chunk)
            if not chunk:
                continue
            rows.append(
                EventRow(
                    scraped_at_utc=scraped_at_utc,
                    section=section_key,
                    event_name=chunk,
                    region="",
                    time_range="",
                )
            )
    return rows


def parse_news(soup: BeautifulSoup, scraped_at_utc: str) -> List[NewsRow]:
    rows: List[NewsRow] = []
    news_links = soup.select("a[href^='/'][href*='news']")
    for a in news_links:
        title = clean_text(a.get_text(" ", strip=True))
        if not title or len(title) < 10:
            continue

        href = a.get("href", "")
        absolute_url = f"{BASE_URL}{href}" if href.startswith("/") else ""

        nearby_text = clean_text(a.parent.get_text(" ", strip=True)) if a.parent else ""
        comments_count = parse_int(nearby_text)

        # Try to detect date labels like "March 28" in surrounding text.
        date_bucket = ""
        prev = a.find_previous(string=True)
        if prev:
            prev_text = clean_text(str(prev))
            if re.search(r"^[A-Za-z]+\s+\d{1,2}$", prev_text):
                date_bucket = prev_text

        rows.append(
            NewsRow(
                scraped_at_utc=scraped_at_utc,
                date_bucket=date_bucket,
                title=title,
                comments_count=comments_count,
                relative_url=href,
                absolute_url=absolute_url,
            )
        )

    # Deduplicate by url + title
    dedup = {}
    for row in rows:
        key = (row.relative_url, row.title)
        dedup[key] = row
    return list(dedup.values())


def write_csv(rows: List[dict], output_path: Path) -> None:
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def run(output_dir: Path, delay_seconds: float) -> None:
    with requests.Session() as session:
        html = fetch_homepage(session, delay_seconds)

    soup = BeautifulSoup(html, "html.parser")
    scraped_at_utc = datetime.now(timezone.utc).isoformat()

    matches = [asdict(x) for x in parse_matches(soup, scraped_at_utc)]
    events = [asdict(x) for x in parse_events(soup, scraped_at_utc)]
    news = [asdict(x) for x in parse_news(soup, scraped_at_utc)]

    write_csv(matches, output_dir / "matches.csv")
    write_csv(events, output_dir / "events.csv")
    write_csv(news, output_dir / "news.csv")

    print(f"Wrote {len(matches)} rows -> {output_dir / 'matches.csv'}")
    print(f"Wrote {len(events)} rows -> {output_dir / 'events.csv'}")
    print(f"Wrote {len(news)} rows -> {output_dir / 'news.csv'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape VLR homepage into CSV files.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory where CSV files will be written.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay after request to keep scraping polite.",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run(output_dir=args.output_dir, delay_seconds=args.delay_seconds)
