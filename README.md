# VLR Data Scraper (for trend analysis)

This project scrapes public homepage data from [vlr.gg](https://www.vlr.gg) into CSV files that are easy to use for data analysis and charting.

## What it collects

- Match cards (team names, score snapshot, event, stage, status)
- Event section entries (live/ongoing/upcoming/completed blocks)
- News links and metadata snippets

## Quick start

1. Create environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Scrape data:

```bash
python vlr_scrape.py --output-dir data/raw
```

3. Generate starter charts:

```bash
python analyze_vlr.py --data-dir data/raw --charts-dir data/charts
```

4. Build a player tournament bar graph (across all paginated history pages):

```bash
python player_tournament_chart.py \
  --player-url "https://www.vlr.gg/player/matches/17086/something" \
  --output-csv data/raw/player_tournament_counts.csv \
  --output-chart data/charts/player_matches_per_tournament.png \
  --top-n 20
```

Or resolve by player name:

```bash
python player_tournament_chart.py \
  --player-name "something" \
  --output-csv data/raw/player_tournament_counts_something.csv \
  --output-chart data/charts/matches_per_tournament_something.png \
  --top-n 20
```

Prompt mode (no args):

```bash
python player_tournament_chart.py
```

The script will ask for the player name and then generate the CSV + chart.
Default output names now include the player slug so each run is easier to identify.

## Output files

- `data/raw/matches.csv`
- `data/raw/events.csv`
- `data/raw/news.csv`
- `data/charts/match_status_distribution.png`
- `data/charts/top_events.png`
- `data/raw/player_tournament_counts.csv`
- `data/charts/player_matches_per_tournament.png`

## Notes for reliable trend analysis

- Run the scraper on a schedule (hourly/daily) and append snapshots over time.
- Keep `scraped_at_utc` for longitudinal trends.
- Start with homepage scraping, then extend to event/match detail pages for richer metrics.
- Respect site terms and use low request rates.

## Next recommended upgrade

Add a historical append mode that writes to partitioned files like `data/history/date=YYYY-MM-DD/*.csv`, then build trend charts (moving averages, rolling match volume, team activity over time).
