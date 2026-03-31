import argparse
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple
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


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "player"


def infer_player_label(player_matches_url: str, player_name: str) -> str:
    if player_name:
        return clean_text(player_name)
    parsed = urlparse(player_matches_url)
    parts = [p for p in parsed.path.split("/") if p]
    return clean_text(parts[-1]) if parts else "player"


def absolute_page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    return f"{base_url.rstrip('/')}/?page={page}"


def fetch_html(session: requests.Session, url: str, delay_seconds: float) -> str:
    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    time.sleep(delay_seconds)
    return response.text


def resolve_player_matches_url(
    session: requests.Session, player_name: str, delay_seconds: float
) -> str:
    search_url = f"https://www.vlr.gg/search/?q={player_name}"
    html = fetch_html(session, search_url, delay_seconds)
    soup = BeautifulSoup(html, "html.parser")

    candidates: List[Tuple[str, str]] = []
    for a in soup.select("a[href^='/search/r/player/']"):
        href = a.get("href", "")
        name = clean_text(a.get_text(" ", strip=True))
        if href and name:
            candidates.append((name, href))

    if not candidates:
        raise ValueError(f"No player search results found for '{player_name}'.")

    selected_href: Optional[str] = None
    target = player_name.casefold()
    for candidate_name, href in candidates:
        if candidate_name.casefold() == target:
            selected_href = href
            break
    if selected_href is None:
        selected_href = candidates[0][1]

    redirect_url = f"https://www.vlr.gg{selected_href}"
    resolved = session.get(
        redirect_url,
        headers={"User-Agent": USER_AGENT},
        timeout=20,
        allow_redirects=True,
    )
    resolved.raise_for_status()
    time.sleep(delay_seconds)

    player_url = resolved.url.rstrip("/")
    parsed = urlparse(player_url)
    if "/player/" not in parsed.path:
        raise ValueError(f"Resolved URL is not a player page: {player_url}")
    matches_path = parsed.path.replace("/player/", "/player/matches/", 1)
    return f"{parsed.scheme}://{parsed.netloc}{matches_path}"


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


def plot_counts(
    df: pd.DataFrame, output_path: Path, top_n: int, player_label: str, pages_scraped: int
) -> None:
    to_plot = df.head(top_n).sort_values("match_count")
    if to_plot.empty:
        raise ValueError("No tournament data found to plot.")

    fig, ax = plt.subplots(figsize=(10, max(4, 0.45 * len(to_plot))))
    bars = ax.barh(to_plot["tournament"], to_plot["match_count"], color="#4C78A8")
    ax.set_title(f"{player_label} - Matches per Tournament (Top {len(to_plot)})")
    ax.set_xlabel("Number of Matches")
    ax.set_ylabel("Tournament Name")
    ax.bar_label(bars, fmt="%d", padding=3)
    total_matches = int(df["match_count"].sum())
    ax.text(
        0.0,
        -0.12,
        f"Data: VLR match history pages 1..{pages_scraped} | Total matches counted: {total_matches}",
        transform=ax.transAxes,
        fontsize=9,
        color="#444444",
    )
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
        default="",
        help="Player match-history URL on VLR.",
    )
    parser.add_argument(
        "--player-name",
        default="",
        help="Player name to resolve via VLR search (example: something).",
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
    if not args.player_url and not args.player_name:
        entered_name = input("Enter player name (as shown on VLR): ").strip()
        if entered_name:
            args.player_name = entered_name
        else:
            raise ValueError("Player name is required in prompt mode.")

    player_matches_url = args.player_url
    if args.player_name:
        with requests.Session() as session:
            player_matches_url = resolve_player_matches_url(
                session=session,
                player_name=args.player_name,
                delay_seconds=args.delay_seconds,
            )
        print(f"Resolved player name '{args.player_name}' -> {player_matches_url}")

    player_label = infer_player_label(player_matches_url, args.player_name)
    player_slug = slugify(player_label)

    if args.output_chart == Path("data/charts/player_matches_per_tournament.png"):
        args.output_chart = Path(f"data/charts/matches_per_tournament_{player_slug}.png")
    if args.output_csv == Path("data/raw/player_tournament_counts.csv"):
        args.output_csv = Path(f"data/raw/player_tournament_counts_{player_slug}.csv")

    counts_df, max_page = scrape_player_tournaments(player_matches_url, args.delay_seconds)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    counts_df.to_csv(args.output_csv, index=False)
    plot_counts(counts_df, args.output_chart, args.top_n, player_label, max_page)
    print(f"Scraped pages: 1..{max_page}")
    print(f"Player: {player_label}")
    print(f"Wrote counts CSV: {args.output_csv}")
    print(f"Wrote chart PNG: {args.output_chart}")


if __name__ == "__main__":
    main()
