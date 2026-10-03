from django.test import TestCase
from rest_framework.test import APIClient


class MatchFlow(TestCase):
    def setUp(self):
        self.c = APIClient()
        ids = []
        for name, ps in (("Kings", "A1 A2 A3 A4"), ("Strikers", "B1 B2 B3 B4")):
            self.c.post("/api/teams/", {"name": name, "players": ps.split()}, format="json")
        t = {x["name"]: x["id"] for x in self.c.get("/api/teams/").json()}
        r = self.c.post("/api/matches/", {"team_a": t["Kings"], "team_b": t["Strikers"], "overs_limit": 2,
                                           "toss_winner": t["Kings"], "toss_decision": "bat"}, format="json")
        self.m = r.json()["id"]

    def ball(self, **kw):
        return self.c.post(f"/api/matches/{self.m}/ball/", kw, format="json")

    def pick(self, role, pid):
        return self.c.post(f"/api/matches/{self.m}/select/", {"role": role, "player": pid}, format="json")

    def state(self):
        return self.c.get(f"/api/matches/{self.m}/").json()

    def start_over(self, i=0):
        s = self.state()["live"]
        while s["need"] == "batter":              # openers are chosen by the scorer
            self.pick("batter", s["options"][0]["id"])
            s = self.state()["live"]
        assert s["need"] == "bowler"
        return self.pick("bowler", s["options"][i]["id"])

    def test_full_match(self):
        self.assertEqual(self.ball(runs=1).status_code, 400)  # no bowler yet
        self.start_over()
        for _ in range(6):
            self.assertEqual(self.ball(runs=1).status_code, 200)  # 6 singles, strike swaps each ball
        s = self.state()
        self.assertEqual(s["innings"][0]["runs"], 6)
        self.assertEqual(s["live"]["need"], "bowler")
        bowler = s["live"]["options"]
        self.assertEqual(len(bowler), 3)  # last over's bowler excluded
        self.start_over()
        self.ball(extra="wd")                      # wide: not a legal ball
        self.ball(runs=0, wicket="bowled")
        self.assertEqual(self.state()["live"]["need"], "batter")
        nxt = self.state()["live"]["options"][0]["id"]
        self.assertEqual(self.pick("batter", nxt).status_code, 200)
        for _ in range(5):
            self.ball(runs=4)
        s = self.state()
        self.assertEqual(s["innings"][0]["runs"], 6 + 1 + 20)
        self.assertEqual(s["innings"][0]["wickets"], 1)
        self.assertEqual(s["innings"][0]["overs"], "2.0")
        self.assertEqual(len(s["innings"]), 2)      # innings 2 created
        self.assertEqual(s["live"]["target"], 28)
        # chase
        self.start_over()
        self.ball(runs=6)
        self.ball(runs=6)
        self.ball(runs=6)
        self.ball(runs=6)
        self.ball(runs=6)
        s = self.state()
        self.assertEqual(s["status"], "completed")
        self.assertIn("Strikers won by", s["result"])

    def test_undo_restores_state(self):
        self.start_over()
        self.ball(runs=1)
        before = self.state()
        self.ball(runs=2)
        self.c.post(f"/api/matches/{self.m}/undo/")
        after = self.state()
        self.assertEqual(before["live"]["striker"], after["live"]["striker"])
        self.assertEqual(before["innings"][0]["runs"], after["innings"][0]["runs"])

    def test_run_out_non_striker(self):
        self.start_over()
        s = self.state()["live"]
        self.ball(runs=1, wicket="run_out", dismissed=s["non_striker"]["id"])
        live = self.state()["live"]
        self.assertEqual(live["need"], "batter")
        self.assertEqual(live["striker"]["id"], s["striker"]["id"])
        self.assertEqual(self.ball(runs=0).status_code, 400)

    def test_stats_and_history(self):
        self.start_over()
        self.ball(runs=4)
        self.assertEqual(self.c.get("/api/stats/").json()["batting"][0]["runs"], 4)
        self.assertEqual(len(self.c.get("/api/matches/").json()), 1)
        tot = self.c.get("/api/stats/").json()["totals"]
        self.assertEqual((tot["matches"], tot["teams"], tot["runs"], tot["sixes"]), (1, 2, 4, 0))


class Roles(TestCase):
    def test_roles_shape_openers_and_choices(self):
        c = APIClient()
        mk = lambda n, ps: c.post("/api/teams/", {"name": n, "players": ps}, format="json")
        mk("X", [{"name": "Bow1", "role": "bowler"}, {"name": "Bat1", "role": "batter"},
                 {"name": "Bat2", "role": "batter"}, {"name": "All1", "role": "allrounder"}])
        mk("Y", [{"name": "Bow2", "role": "bowler"}, {"name": "Bat3", "role": "batter"}, {"name": "All2", "role": "allrounder"}])
        t = {x["name"]: x["id"] for x in c.get("/api/teams/").json()}
        m = c.post("/api/matches/", {"team_a": t["X"], "team_b": t["Y"], "overs_limit": 2,
                                      "toss_winner": t["X"], "toss_decision": "bat"}, format="json").json()
        live = m["live"]
        self.assertEqual((live["need"], live["opening"], live["striker"]), ("batter", True, None))
        self.assertEqual([o["name"] for o in live["options"]], ["Bat1", "Bat2", "All1", "Bow1"])  # batters first
        c.post(f"/api/matches/{m['id']}/select/", {"role": "batter", "player": live["options"][2]["id"]}, format="json")
        live = c.get(f"/api/matches/{m['id']}/").json()["live"]
        self.assertEqual(live["striker"]["name"], "All1")                 # first pick faces the first ball
        self.assertNotIn("All1", [o["name"] for o in live["options"]])
        c.post(f"/api/matches/{m['id']}/select/", {"role": "batter", "player": live["options"][0]["id"]}, format="json")
        live = c.get(f"/api/matches/{m['id']}/").json()["live"]
        self.assertEqual((live["need"], live["non_striker"]["name"]), ("bowler", "Bat1"))
        self.assertEqual([o["name"] for o in live["options"]], ["Bow2", "All2"])   # bowlers first, batters excluded


class EndAndDelete(MatchFlow):
    def test_end_match_mid_chase_and_undo(self):
        self.start_over()
        for _ in range(12):
            if self.state()["live"]["need"]:
                self.start_over()
            if self.state()["status"] != "live" or len(self.state()["innings"]) > 1:
                break
            self.ball(runs=1)
        self.start_over()
        self.ball(runs=6)
        r = self.c.post(f"/api/matches/{self.m}/end/")
        s = r.json()
        self.assertEqual(s["status"], "completed")
        self.assertIn("ended early", s["result"])
        self.assertIsNone(s["live"])
        self.assertEqual(self.c.post(f"/api/matches/{self.m}/end/").status_code, 400)
        s = self.c.post(f"/api/matches/{self.m}/undo/").json()      # undo reopens the match
        self.assertEqual(s["status"], "live")

    def test_end_before_any_ball(self):
        s = self.c.post(f"/api/matches/{self.m}/end/").json()
        self.assertEqual(s["result"], "Match ended early")

    def test_delete_match_and_team(self):
        self.start_over()
        self.ball(runs=4)
        teams = self.c.get("/api/teams/").json()
        tid = teams[0]["id"]
        self.assertEqual(teams[0]["matches"], 1)
        r = self.c.delete(f"/api/teams/{tid}/")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "in_use"))      # needs confirmation
        self.assertEqual(len(self.c.get("/api/teams/").json()), 2)
        self.assertEqual(self.c.delete(f"/api/teams/{tid}/?force=1").status_code, 200)
        self.assertEqual(len(self.c.get("/api/teams/").json()), 1)
        self.assertEqual(self.c.get("/api/matches/").json(), [])                  # its match went too
        self.assertEqual(self.c.get("/api/stats/").json()["batting"], [])

    def test_delete_match_only(self):
        self.assertEqual(self.c.delete(f"/api/matches/{self.m}/").status_code, 200)
        self.assertEqual(self.c.get(f"/api/matches/{self.m}/").status_code, 404)
        self.assertEqual(len(self.c.get("/api/teams/").json()), 2)                # teams stay
