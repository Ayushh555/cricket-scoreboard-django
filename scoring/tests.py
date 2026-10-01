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
        assert s["need"] == "bowler"
        return self.pick("bowler", s["options"][i]["id"])

    def test_second_match_blocked_while_live(self):
        t = {x["name"]: x["id"] for x in self.c.get("/api/teams/").json()}
        body = {"team_a": t["Kings"], "team_b": t["Strikers"], "overs_limit": 2,
                "toss_winner": t["Kings"], "toss_decision": "bat"}
        r = self.c.post("/api/matches/", body, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "match_live")

    def test_end_match_then_new_one_allowed(self):
        r = self.c.post(f"/api/matches/{self.m}/end/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "completed")
        self.assertIsNone(r.json()["live"])
        self.assertEqual(self.c.post(f"/api/matches/{self.m}/end/").status_code, 400)
        t = {x["name"]: x["id"] for x in self.c.get("/api/teams/").json()}
        r = self.c.post("/api/matches/", {"team_a": t["Kings"], "team_b": t["Strikers"], "overs_limit": 2,
                                           "toss_winner": t["Kings"], "toss_decision": "bat"}, format="json")
        self.assertEqual(r.status_code, 201)

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

    def test_run_out_end_decides_who_faces_next(self):
        self.start_over()
        live = self.state()["live"]
        bat, non = live["striker"]["id"], live["non_striker"]["id"]
        # non-striker run out at the STRIKER's end: the new batter goes there and faces; the survivor is non-striker
        self.ball(runs=0, wicket="run_out", dismissed=non, end="striker")
        self.pick("batter", self.state()["live"]["options"][0]["id"])
        live = self.state()["live"]
        self.assertNotIn(live["striker"]["id"], (bat, non))
        self.assertEqual(live["non_striker"]["id"], bat)

    def test_run_out_defaults_to_the_dismissed_batters_own_end(self):
        self.start_over()
        live = self.state()["live"]
        bat, non = live["striker"]["id"], live["non_striker"]["id"]
        self.ball(runs=1, wicket="run_out", dismissed=bat)      # striker out, no end given -> new batter on strike
        self.pick("batter", self.state()["live"]["options"][0]["id"])
        live = self.state()["live"]
        self.assertEqual(live["non_striker"]["id"], non)
        self.assertNotEqual(live["striker"]["id"], bat)

    def test_run_out_rules_scoring_undo_and_credit(self):
        self.start_over()
        live = self.state()["live"]
        bat, non = live["striker"]["id"], live["non_striker"]["id"]
        self.assertEqual(self.ball(runs=0, wicket="run_out", dismissed=bat, end="sideways").status_code, 400)
        self.assertEqual(self.ball(extra="nb", wicket="bowled").status_code, 400)           # still not allowed off a no ball
        self.assertEqual(self.ball(runs=1, extra="wd", wicket="run_out", dismissed=non).status_code, 200)  # wide + run out is fine
        inn = self.state()["innings"][0]
        self.assertEqual((inn["runs"], inn["wickets"]), (2, 1))                              # wide 1 + 1 run
        self.assertEqual(inn["bowling"][0]["wickets"], 0)                                   # a run out is not the bowler's wicket
        self.c.post(f"/api/matches/{self.m}/undo/")
        live = self.state()["live"]
        self.assertEqual((live["striker"]["id"], live["non_striker"]["id"]), (bat, non))   # undo brings both batters back
        self.assertEqual(self.state()["innings"][0]["wickets"], 0)

    def test_stats_and_history(self):
        self.start_over()
        self.ball(runs=4)
        self.assertEqual(self.c.get("/api/stats/").json()["batting"][0]["runs"], 4)
        self.assertEqual(len(self.c.get("/api/matches/").json()), 1)


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
        self.assertEqual({live["striker"]["name"], live["non_striker"]["name"]}, {"Bat1", "Bat2"})  # batters open
        names = [o["name"] for o in live["options"]]
        self.assertEqual(names, ["Bow2", "All2"])   # bowlers first, pure batters excluded


class TeamDelete(TestCase):
    def setUp(self):
        self.c = APIClient()
        for n in ("Kings", "Strikers"):
            self.c.post("/api/teams/", {"name": n, "players": ["a", "b", "c"]}, format="json")
        self.t = {x["name"]: x["id"] for x in self.c.get("/api/teams/").json()}

    def match(self):
        return self.c.post("/api/matches/", {"team_a": self.t["Kings"], "team_b": self.t["Strikers"], "overs_limit": 2,
                                             "toss_winner": self.t["Kings"], "toss_decision": "bat"}, format="json")

    def test_duplicate_active_name_rejected(self):
        r = self.c.post("/api/teams/", {"name": "kings", "players": ["x", "y"]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cannot_delete_team_in_unfinished_match(self):
        self.match()
        self.assertEqual(self.c.delete(f"/api/teams/{self.t['Kings']}/").status_code, 400)

    def test_delete_hides_team_but_keeps_matches_and_frees_the_name(self):
        from .models import Match
        m = self.match().json()["id"]
        Match.objects.filter(pk=m).update(status="completed", result="Kings won")   # pretend it finished
        r = self.c.delete(f"/api/teams/{self.t['Kings']}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["name"] for x in r.json()], ["Strikers"])                 # hidden from the picker
        self.assertEqual(len(self.c.get("/api/matches/").json()), 1)                   # record is still there
        self.assertEqual(self.c.get(f"/api/matches/{m}/").status_code, 200)
        self.assertEqual(self.c.post("/api/teams/", {"name": "Kings", "players": ["n1", "n2"]}, format="json").status_code, 200)  # name reusable
        self.assertEqual(self.c.delete(f"/api/teams/{self.t['Kings']}/").status_code, 400)  # already archived

    def test_matches_cannot_be_deleted_through_the_api(self):
        m = self.match().json()["id"]
        self.assertEqual(self.c.delete(f"/api/matches/{m}/").status_code, 405)
