import unittest
from datetime import date

from scripts.fetch_data import (
    COMPETITIONS,
    FootballDataClient,
    build_competition,
    fetch_snapshot,
    map_match,
)


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/matches"):
            return {"matches": []}
        if endpoint.endswith("/standings"):
            return {
                "competition": {"name": "Premier League"},
                "season": {"startDate": "2026-08-01", "endDate": "2027-05-31", "currentMatchday": 8},
                "standings": [{"type": "TOTAL", "table": [{
                    "team": {"name": "Arsenal FC", "shortName": "Arsenal", "tla": "ARS"},
                    "position": 1, "playedGames": 8, "won": 6, "draw": 1, "lost": 1,
                    "points": 19, "goalsFor": 20, "goalsAgainst": 8, "form": "W, W, D, L, W",
                }]}],
            }
        return {"scorers": [{
            "player": {"name": "Example Striker"},
            "team": {"shortName": "Arsenal"},
            "goals": 7,
        }]}


class FetchDataTests(unittest.TestCase):
    def test_live_match_is_mapped_without_losing_current_score(self):
        mapped = map_match({
            "status": "IN_PLAY", "minute": 78, "utcDate": "2026-10-05T18:00:00Z",
            "homeTeam": {"shortName": "Arsenal"}, "awayTeam": {"shortName": "Liverpool"},
            "score": {"fullTime": {"home": 2, "away": 1}}, "venue": "Emirates Stadium",
        })
        self.assertEqual(mapped["status"], "live")
        self.assertEqual(mapped["time"], "78'")
        self.assertEqual((mapped["hs"], mapped["as"]), (2, 1))

    def test_competition_maps_table_and_top_scorer(self):
        result = build_competition(
            COMPETITIONS["premier"],
            {"matches": []},
            {
                "competition": {"name": "Premier League"},
                "season": {"startDate": "2026-08-01", "endDate": "2027-05-31", "currentMatchday": 8},
                "standings": [{"type": "TOTAL", "table": [{
                    "team": {"shortName": "Arsenal", "tla": "ARS"}, "points": 19,
                    "playedGames": 8, "won": 6, "draw": 1, "lost": 1,
                    "goalsFor": 20, "goalsAgainst": 8, "form": "W, W, D, L, W",
                }]}],
            },
            {"scorers": [{"player": {"name": "Example Striker"}, "team": {"shortName": "Arsenal"}, "goals": 7}]},
        )
        self.assertEqual(result["season"], "2026 / 27")
        self.assertEqual(result["teams"][0][:9], ["Arsenal", "ARS", 19, 8, 6, 1, 20, 8, "WWDLW"])
        self.assertEqual(result["scorers"][0]["name"], "Example Striker")

    def test_snapshot_uses_three_requests_per_competition(self):
        client = FakeClient()
        snapshot = fetch_snapshot(client, today=date(2026, 10, 5))
        self.assertEqual(len(client.calls), 15)
        self.assertEqual(snapshot["date"], "2026-10-05")
        self.assertEqual(set(snapshot["competitions"]), set(COMPETITIONS))
        self.assertEqual(client.calls[0][1], {"dateFrom": "2026-10-05", "dateTo": "2026-10-06"})

    def test_client_spaces_requests_at_seven_seconds(self):
        now = [0.0]
        starts = []

        def fake_sleep(seconds):
            now[0] += seconds

        def fake_get(*args, **kwargs):
            starts.append(now[0])
            return FakeResponse({"ok": True})

        client = FootballDataClient("test-token", request_get=fake_get, sleep=fake_sleep, monotonic=lambda: now[0])
        client.get("competitions/2021/standings")
        client.get("competitions/2021/scorers")
        self.assertEqual(starts, [0.0, 7.0])


if __name__ == "__main__":
    unittest.main()
