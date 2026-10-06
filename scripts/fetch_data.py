from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests

API_BASE = "https://api.football-data.org/v4"
PARIS = ZoneInfo("Europe/Paris")
MIN_REQUEST_INTERVAL_SECONDS = 7.0
REQUEST_TIMEOUT_SECONDS = 20
FIXTURE_WINDOW_DAYS = 7
OUTPUT_PATH = Path("data/football.json")

COMPETITIONS = {
    "premier": {"id": 2021, "code": "PL", "name": "Premier League", "flag": "🏴"},
    "laliga": {"id": 2014, "code": "PD", "name": "La Liga", "flag": "🇪🇸"},
    "bundesliga": {"id": 2002, "code": "BL1", "name": "Bundesliga", "flag": "🇩🇪"},
    "seriea": {"id": 2019, "code": "SA", "name": "Serie A", "flag": "🇮🇹"},
    "ligue1": {"id": 2015, "code": "FL1", "name": "Ligue 1", "flag": "🇫🇷"},
}


class FootballDataClient:
    def __init__(
        self,
        token: str,
        *,
        request_get: Callable[..., Any] = requests.get,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not token.strip():
            raise ValueError("FOOTBALL_DATA_TOKEN is required")
        self._token = token
        self._request_get = request_get
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def get(self, endpoint: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = MIN_REQUEST_INTERVAL_SECONDS - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

        response = self._request_get(
            f"{API_BASE}/{endpoint.lstrip('/')}",
            headers={"X-Auth-Token": self._token},
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise RuntimeError(
                f"Football-Data rate limit reached (HTTP 429, Retry-After: {retry_after}); "
                "the previous snapshot was kept."
            )
        response.raise_for_status()
        return response.json()


def season_label(season: dict[str, Any]) -> str:
    start = season.get("startDate", "")
    end = season.get("endDate", "")
    if len(start) >= 4 and len(end) >= 4:
        return f"{start[:4]} / {end[2:4]}"
    return "Saison en cours"


def match_status(api_status: str) -> str:
    if api_status in {"IN_PLAY", "PAUSED"}:
        return "live"
    if api_status in {"FINISHED", "AWARDED"}:
        return "finished"
    return "upcoming"


def local_kickoff(utc_date: str) -> str:
    parsed = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
    return parsed.astimezone(PARIS).strftime("%H:%M")

def local_match_date(utc_date: str) -> str:
    parsed = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
    return parsed.astimezone(PARIS).date().isoformat()


def map_match(match: dict[str, Any]) -> dict[str, Any]:
    status = match_status(match.get("status", "SCHEDULED"))
    score = match.get("score") or {}
    result = score.get("fullTime") or score.get("regularTime") or {}
    minute = match.get("minute")
    time_label = (
        f"{minute}'" if status == "live" and minute is not None
        else "Direct" if status == "live"
        else "Terminé" if status == "finished"
        else local_kickoff(match["utcDate"])
    )
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    return {
        "home": home.get("shortName") or home.get("name") or "Équipe domicile",
        "away": away.get("shortName") or away.get("name") or "Équipe extérieure",
        "hs": result.get("home"),
        "as": result.get("away"),
        "status": status,
        "time": time_label,
        "date": local_match_date(match["utcDate"]),
        "venue": match.get("venue"),
    }


def standings_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    standings = payload.get("standings") or []
    selected = next((item for item in standings if item.get("type") == "TOTAL"), None)
    selected = selected or next(iter(standings), None)
    if not selected or not selected.get("table"):
        raise ValueError("Football-Data returned no standings table")
    return selected["table"]


def map_scorers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for entry in payload.get("scorers") or []:
        player = entry.get("player") or {}
        team = entry.get("team") or {}
        if player.get("name") and team.get("shortName"):
            result.append({
                "name": player["name"],
                "club": team["shortName"],
                "goals": entry.get("goals") or 0,
            })
    return result


def build_competition(
    config: dict[str, Any],
    matches_payload: dict[str, Any],
    standings_payload: dict[str, Any],
    scorers_payload: dict[str, Any],
    today: date | None = None,
) -> dict[str, Any]:
    snapshot_day = today or datetime.now(PARIS).date()
    table = standings_table(standings_payload)
    scorers = map_scorers(scorers_payload)
    top_scorer_by_club = {item["club"]: item for item in scorers}
    teams = []
    for row in table:
        api_team = row.get("team") or {}
        team_name = api_team.get("shortName") or api_team.get("name")
        if not team_name:
            continue
        scorer = top_scorer_by_club.get(team_name, {})
        form = "".join(value for value in (row.get("form") or "") if value in "WDL")
        teams.append([
            team_name,
            api_team.get("tla") or team_name[:3].upper(),
            row.get("points") or 0,
            row.get("playedGames") or 0,
            row.get("won") or 0,
            row.get("draw") or 0,
            row.get("goalsFor") or 0,
            row.get("goalsAgainst") or 0,
            form,
            scorer.get("name", ""),
            scorer.get("goals", 0),
        ])

    matches = [map_match(match) for match in matches_payload.get("matches") or []]
    today_matches = [match for match in matches if match["date"] == snapshot_day.isoformat()]
    competition = standings_payload.get("competition") or {}
    season = standings_payload.get("season") or {}
    goals = sum((match["hs"] or 0) + (match["as"] or 0) for match in today_matches)
    return {
        "name": config["name"],
        "flag": config["flag"],
        "season": season_label(season),
        "round": season.get("currentMatchday") or 0,
        "liveCount": sum(match["status"] == "live" for match in today_matches),
        "goals": goals,
        "teams": teams,
        "matches": matches,
        "scorers": scorers,
        "apiCompetitionName": competition.get("name", config["name"]),
    }


def fetch_snapshot(client: FootballDataClient, today: date | None = None) -> dict[str, Any]:
    target_day = today or datetime.now(PARIS).date()
    date_from = target_day.isoformat()
    date_to = (target_day + timedelta(days=FIXTURE_WINDOW_DAYS)).isoformat()
    competitions = {}

    for key, config in COMPETITIONS.items():
        competition_id = config["id"]
        matches_payload = client.get(
            f"competitions/{competition_id}/matches",
            params={"dateFrom": date_from, "dateTo": date_to},
        )
        standings_payload = client.get(f"competitions/{competition_id}/standings")
        scorers_payload = client.get(
            f"competitions/{competition_id}/scorers",
            params={"limit": "10"},
        )
        competitions[key] = build_competition(
            config, matches_payload, standings_payload, scorers_payload, target_day
        )

    return {
        "schemaVersion": 1,
        "source": "Football-Data.org",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": date_from,
        "competitions": competitions,
    }


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(snapshot, temporary_file, ensure_ascii=False, separators=(",", ":"))
            temporary_file.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the public football data snapshot.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    token = os.environ.get("FOOTBALL_DATA_TOKEN", "")
    if not token.strip():
        parser.error("FOOTBALL_DATA_TOKEN is missing; add it as a GitHub Actions secret")

    try:
        snapshot = fetch_snapshot(FootballDataClient(token))
        write_snapshot(args.output, snapshot)
    except (requests.RequestException, RuntimeError, ValueError, KeyError) as error:
        print(f"Snapshot generation failed: {error}")
        return 1

    print(
        f"Wrote {len(snapshot['competitions'])} competitions for {snapshot['date']} "
        f"to {args.output}; 15 upstream requests, paced at "
        f"{MIN_REQUEST_INTERVAL_SECONDS:g}s minimum."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
