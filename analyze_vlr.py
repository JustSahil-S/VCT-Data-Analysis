import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from pandas.errors import EmptyDataError


def safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()


def build_match_status_chart(matches: pd.DataFrame, output_dir: Path) -> None:
    if matches.empty or "match_status" not in matches.columns:
        return
    counts = matches["match_status"].fillna("unknown").value_counts()
    if counts.empty:
        return
    ax = counts.plot(kind="bar", figsize=(8, 4), title="Match Status Distribution")
    ax.set_xlabel("Status")
    ax.set_ylabel("Count")
    plt.tight_layout()
    plt.savefig(output_dir / "match_status_distribution.png", dpi=150)
    plt.close()


def build_top_events_chart(matches: pd.DataFrame, output_dir: Path, top_n: int = 10) -> None:
    if matches.empty or "event_name" not in matches.columns:
        return
    event_counts = (
        matches["event_name"]
        .fillna("")
        .loc[lambda s: s.str.strip() != ""]
        .value_counts()
        .head(top_n)
        .sort_values()
    )
    if event_counts.empty:
        return
    ax = event_counts.plot(kind="barh", figsize=(9, 5), title=f"Top {top_n} Events by Match Cards")
    ax.set_xlabel("Match Count")
    ax.set_ylabel("Event")
    plt.tight_layout()
    plt.savefig(output_dir / "top_events.png", dpi=150)
    plt.close()


def run(data_dir: Path, charts_dir: Path) -> None:
    charts_dir.mkdir(parents=True, exist_ok=True)
    matches = safe_read_csv(data_dir / "matches.csv")
    build_match_status_chart(matches, charts_dir)
    build_top_events_chart(matches, charts_dir)
    print(f"Charts written to: {charts_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate starter VLR charts from scraped CSV data.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--charts-dir", type=Path, default=Path("data/charts"))
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run(args.data_dir, args.charts_dir)
