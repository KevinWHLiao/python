#!/usr/bin/env python3
"""Fetch Sacramento Kings advanced stats from NBA.com (stats.nba.com)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
from datetime import date
from typing import Any

KINGS_TEAM_ID = 1610612758
STATS_URL = "https://stats.nba.com/stats/leaguedashplayerstats"
WARMUP_URL = "https://www.nba.com/stats/"
IMPERSONATE_PROFILES = ("chrome", "chrome120")

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/stats/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

# Columns shown in the default table (NBA.com Advanced tab).
DISPLAY_COLUMNS = [
    "PLAYER_NAME",
    "GP",
    "MIN",
    "OFF_RATING",
    "DEF_RATING",
    "NET_RATING",
    "AST_PCT",
    "AST_TO",
    "AST_RATIO",
    "OREB_PCT",
    "DREB_PCT",
    "REB_PCT",
    "TM_TOV_PCT",
    "EFG_PCT",
    "TS_PCT",
    "USG_PCT",
    "PACE",
    "PIE",
]

COLUMN_LABELS = {
    "PLAYER_NAME": "Player",
    "GP": "GP",
    "MIN": "MIN",
    "OFF_RATING": "OFFRTG",
    "DEF_RATING": "DEFRTG",
    "NET_RATING": "NETRTG",
    "AST_PCT": "AST%",
    "AST_TO": "AST/TO",
    "AST_RATIO": "AST RATIO",
    "OREB_PCT": "OREB%",
    "DREB_PCT": "DREB%",
    "REB_PCT": "REB%",
    "TM_TOV_PCT": "TOV%",
    "EFG_PCT": "EFG%",
    "TS_PCT": "TS%",
    "USG_PCT": "USG%",
    "PACE": "PACE",
    "PIE": "PIE",
}

PERCENT_COLUMNS = {
    "AST_PCT",
    "OREB_PCT",
    "DREB_PCT",
    "REB_PCT",
    "TM_TOV_PCT",
    "EFG_PCT",
    "TS_PCT",
    "USG_PCT",
    "PIE",
}


def last_completed_season(today: date | None = None) -> str:
    """NBA season label for the most recently finished campaign (Oct–Jun)."""
    today = today or date.today()
    start = today.year - 1 if today.month >= 7 else today.year - 2
    return f"{start}-{str(start + 1)[-2:]}"


def build_params(season: str, season_type: str) -> dict[str, str]:
    return {
        "College": "",
        "Conference": "",
        "Country": "",
        "DateFrom": "",
        "DateTo": "",
        "Division": "",
        "DraftPick": "",
        "DraftYear": "",
        "GameScope": "",
        "GameSegment": "",
        "Height": "",
        "LastNGames": "0",
        "LeagueID": "00",
        "Location": "",
        "MeasureType": "Advanced",
        "Month": "0",
        "OpponentTeamID": "0",
        "Outcome": "",
        "PORound": "0",
        "PaceAdjust": "N",
        "PerMode": "PerGame",
        "Period": "0",
        "PlayerExperience": "",
        "PlayerPosition": "",
        "PlusMinus": "N",
        "Rank": "N",
        "Season": season,
        "SeasonSegment": "",
        "SeasonType": season_type,
        "ShotClockRange": "",
        "StarterBench": "",
        "TeamID": str(KINGS_TEAM_ID),
        "VsConference": "",
        "VsDivision": "",
        "Weight": "",
    }


def _browser_session(impersonate: str):
    try:
        from curl_cffi import requests as cr
    except ImportError as exc:
        raise RuntimeError(
            "缺少 curl_cffi。請先執行：pip install -r requirements.txt"
        ) from exc
    session = cr.Session(impersonate=impersonate)
    session.headers.update(HEADERS)
    return session


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    last_error: Exception | None = None
    for impersonate in IMPERSONATE_PROFILES:
        try:
            session = _browser_session(impersonate)
            # Akamai 會核對 cookie + 瀏覽器 TLS 指紋；先開官網再打 stats.nba.com。
            session.get(WARMUP_URL, timeout=timeout, allow_redirects=True)
            response = session.get(url, timeout=timeout)
            if response.status_code != 200:
                raise RuntimeError(f"stats API HTTP {response.status_code}")
            payload = response.json()
            if "resultSets" not in payload:
                raise RuntimeError("stats API 回傳不是預期的 JSON")
            return payload
        except Exception as exc:  # noqa: BLE001 — try next Chrome impersonation profile
            last_error = exc
            time.sleep(0.8)
    raise RuntimeError(
        "NBA.com 官網能開，但 stats.nba.com 仍被擋（Akamai 防機器人）。"
        f" 最後錯誤：{last_error}"
    ) from last_error


def rows_from_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload["resultSets"][0]
    headers = result["headers"]
    players = [dict(zip(headers, row)) for row in result["rowSet"]]
    players.sort(key=lambda p: (p.get("MIN") is None, -(p.get("MIN") or 0)))
    return players


def format_cell(key: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if key in PERCENT_COLUMNS:
            return f"{value * 100:.1f}%" if value <= 1 else f"{value:.1f}%"
        if key == "MIN":
            return f"{value:.1f}"
        return f"{value:.1f}"
    return str(value)


def print_table(players: list[dict[str, Any]]) -> None:
    labels = [COLUMN_LABELS[c] for c in DISPLAY_COLUMNS]
    grid = [labels]
    for player in players:
        grid.append([format_cell(c, player.get(c)) for c in DISPLAY_COLUMNS])

    widths = [max(len(row[i]) for row in grid) for i in range(len(labels))]
    def line(row: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    print(line(grid[0]))
    print("  ".join("-" * w for w in widths))
    for row in grid[1:]:
        print(line(row))


def write_csv(path: str, players: list[dict[str, Any]]) -> None:
    if not players:
        fieldnames = DISPLAY_COLUMNS
    else:
        fieldnames = list(players[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(players)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取國王隊 NBA.com 進階數據（OFFRTG / NETRTG / USG% / PIE 等）"
    )
    parser.add_argument(
        "--season",
        default=last_completed_season(),
        help="球季，例如 2025-26（預設：剛結束的上季）",
    )
    parser.add_argument(
        "--playoffs",
        action="store_true",
        help="抓季後賽而不是例行賽",
    )
    parser.add_argument("--csv", metavar="PATH", help="另外存成 CSV")
    parser.add_argument("--json", metavar="PATH", help="另外存成 JSON")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    season_type = "Playoffs" if args.playoffs else "Regular Season"
    params = build_params(args.season, season_type)
    url = f"{STATS_URL}?{urllib.parse.urlencode(params)}"

    print(f"Sacramento Kings  {args.season}  {season_type}  (NBA.com Advanced)", flush=True)
    try:
        payload = fetch_json(url)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    players = rows_from_response(payload)
    if not players:
        print("沒有球員資料。可能該季還沒開打，或國王隊沒打季後賽。")
        return 1

    print_table(players)
    print(f"\n共 {len(players)} 名球員")
    print(
        "說明：NBA.com 進階表沒有 BPM / EPM。"
        "這裡對應官網 Players > Advanced：NETRTG、USG%、TS%、PIE 等。"
    )

    if args.csv:
        write_csv(args.csv, players)
        print(f"已寫入 {args.csv}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(players, handle, ensure_ascii=False, indent=2)
        print(f"已寫入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
