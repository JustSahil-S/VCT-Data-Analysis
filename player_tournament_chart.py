import argparse
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import parse_qs, urlparse

import matplotlib.pyplot as plt
import pandas as pd
import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (compatible; VLRDataScraper/1.0; +https://example.com/bot-contact)"
)


def clean_text(value: str) -> str:
    return " ".join(value.split()) if value else ""


def absolute_page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    return f"{base_url.rstrip('/')}/?page={page}"


def fetch_html(session: requests.Session, url: str, delay_seconds: float) -> str:
    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    time.sleep(delay_seconds)
    return response.text


def parse_max_page(soup: BeautifulSoup) -> int:
    max_page = 1
    for a in soup.select("a[href*='?page=']"):
        href = a.get("href", "")
        if not href:
            continue
        parsed = urlparse(href)
        page_param = parse_qs(parsed.query).get("page")
        if not page_param:
            continue
        try:
            max_page = max(max_page, int(page_param[0]))
        except ValueError:
            continue
    return max_page


def extract_tournaments(soup: BeautifulSoup) -> List[str]:
    tournaments: List[str] = []
    cards = soup.select("a.wf-card.fc-flex.m-item")
    for card in cards:
        name_node = card.select_one(".m-item-event > div")
        tournament = clean_text(name_node.get_text(" ", strip=True)) if name_node else ""
        if tournament:
            tournaments.append(tournament)
    return tournaments


def scrape_player_tournaments(player_matches_url: str, delay_seconds: float) -> Tuple[pd.DataFrame, int]:
    all_tournaments: List[str] = []
    with requests.Session() as session:
        first_html = fetch_html(session, player_matches_url, delay_seconds)
        first_soup = BeautifulSoup(first_html, "html.parser")
        max_page = parse_max_page(first_soup)
        all_tournaments.extend(extract_tournaments(first_soup))

        for page in range(2, max_page + 1):
            html = fetch_html(session, absolute_page_url(player_matches_url, page), delay_seconds)
            soup = BeautifulSoup(html, "html.parser")
            all_tournaments.extend(extract_tournaments(soup))

    counts = (
        pd.Series(all_tournaments, name="tournament")
        .value_counts()
        .rename_axis("tournament")
        .reset_index(name="match_count")
    )
    return counts, max_page


def plot_counts(df: pd.DataFrame, output_path: Path, top_n: int) -> None:
    to_plot = df.head(top_n).sort_values("match_count")
    if to_plot.empty:
        raise ValueError("No tournament data found to plot.")

    fig, ax = plt.subplots(figsize=(10, max(4, 0.45 * len(to_plot))))
    ax.barh(to_plot["tournament"], to_plot["match_count"])
    ax.set_title(f"Matches per Tournament (Top {len(to_plot)})")
    ax.set_xlabel("Number of Matches")
    ax.set_ylabel("Tournament")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build bar graph of matches-per-tournament for a VLR player."
    )
    parser.add_argument(
        "--player-url",
        default="https://www.vlr.gg/player/matches/17086/something",
        help="Player match-history URL on VLR.",
    )
    parser.add_argument(
        "--output-chart",
        type=Path,
        default=Path("data/charts/player_matches_per_tournament.png"),
        help="Output path for bar chart PNG.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("data/raw/player_tournament_counts.csv"),
        help="Output path for aggregated tournament counts CSV.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Plot top N tournaments by match count.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay between requests to keep scraping polite.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    counts_df, max_page = scrape_player_tournaments(args.player_url, args.delay_seconds)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    counts_df.to_csv(args.output_csv, index=False)
    plot_counts(counts_df, args.output_chart, args.top_n)
    print(f"Scraped pages: 1..{max_page}")
    print(f"Wrote counts CSV: {args.output_csv}")
    print(f"Wrote chart PNG: {args.output_chart}")


if __name__ == "__main__":
    main()
