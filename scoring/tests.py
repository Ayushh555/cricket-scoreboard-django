from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient


def scorer_client():
    """An API client signed in as a scorer (writes need a login)."""
    user, _ = User.objects.get_or_create(username="scorer")
    c = APIClient()
    c.force_authenticate(user)
    return c


class MatchFlow(TestCase):
    def setUp(self):
        self.c = scorer_client()
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
        c = scorer_client()
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


class DeletePlayer(TestCase):
    def setUp(self):
        self.c = scorer_client()
        for n, ps in (("P", ["p1", "p2", "p3"]), ("Q", ["q1", "q2", "q3"])):
            self.c.post("/api/teams/", {"name": n, "players": ps}, format="json")
        self.t = {x["name"]: x for x in self.c.get("/api/teams/").json()}

    def test_delete_unplayed_player_and_minimum(self):
        pid = self.t["P"]["roster"][2]["id"]
        self.assertEqual(self.c.delete(f"/api/players/{pid}/").status_code, 200)
        left = [x for x in self.c.get("/api/teams/").json() if x["name"] == "P"][0]["roster"]
        self.assertEqual(len(left), 2)
        r = self.c.delete(f"/api/players/{left[0]['id']}/")        # would leave only one player
        self.assertEqual((r.status_code, r.json()["code"]), (400, "min"))

    def test_blocked_while_live_and_after_playing(self):
        m = self.c.post("/api/matches/", {"team_a": self.t["P"]["id"], "team_b": self.t["Q"]["id"], "overs_limit": 1,
                                           "toss_winner": self.t["P"]["id"], "toss_decision": "bat"}, format="json").json()["id"]
        pid = self.t["P"]["roster"][2]["id"]
        self.assertEqual(self.c.delete(f"/api/players/{pid}/").json()["code"], "live")   # team is in a live match
        self.c.post(f"/api/matches/{m}/end/")
        self.assertEqual(self.c.delete(f"/api/players/{pid}/").status_code, 200)         # finished and unplayed: fine


class RunOutEnds(MatchFlow):
    def test_default_end_even_runs_striker_out(self):
        self.start_over(); s = self.state()["live"]
        self.ball(runs=0, wicket="run_out")                      # striker out going to the non-striker's end
        live = self.state()["live"]
        self.assertEqual((live["striker"]["id"], live["non_striker"], live["need"]),
                         (s["non_striker"]["id"], None, "batter"))   # survivor now faces; new batter at the other end

    def test_explicit_end_gives_strike_to_new_batter(self):
        self.start_over(); s = self.state()["live"]
        self.ball(runs=1, wicket="run_out", dismissed=s["non_striker"]["id"], end="striker")
        live = self.state()["live"]
        self.assertEqual((live["striker"], live["non_striker"]["id"]), (None, s["striker"]["id"]))
        self.assertEqual(self.ball(runs=0, end="sideways").status_code, 400)


class OneMatchAtATime(MatchFlow):
    def new_match(self):
        t = {x["name"]: x["id"] for x in self.c.get("/api/teams/").json()}
        return self.c.post("/api/matches/", {"team_a": t["Kings"], "team_b": t["Strikers"], "overs_limit": 2,
                                              "toss_winner": t["Kings"], "toss_decision": "bat"}, format="json")

    def test_second_match_blocked_until_first_is_ended(self):
        r = self.new_match()                                   # setUp already started one
        self.assertEqual((r.status_code, r.json()["code"], r.json()["match_id"]), (400, "live_match", self.m))
        self.assertEqual(self.c.post(f"/api/matches/{self.m}/end/").status_code, 200)
        self.assertEqual(self.new_match().status_code, 201)    # allowed once the first is ended
        self.assertEqual(self.new_match().status_code, 400)    # and the new one blocks again

    def test_finished_match_does_not_block(self):
        self.c.post(f"/api/matches/{self.m}/end/")
        self.assertEqual(self.new_match().status_code, 201)


class LastBall(MatchFlow):
    def test_last_ball_tracks_latest_delivery_and_undo(self):
        self.assertIsNone(self.state()["last_ball"])
        self.start_over()
        self.ball(runs=4)
        lb = self.state()["last_ball"]
        self.assertEqual((lb["runs"], lb["wicket"]), (4, False))
        self.ball(runs=6)
        self.assertEqual(self.state()["last_ball"]["runs"], 6)
        self.assertGreater(self.state()["last_ball"]["id"], lb["id"])
        self.c.post(f"/api/matches/{self.m}/undo/")
        self.assertEqual(self.state()["last_ball"]["id"], lb["id"])      # undo goes back to the earlier ball


class Login(TestCase):
    def setUp(self):
        cache.clear()                      # the login throttle lives in the cache
        self.c = APIClient()

    def test_first_run_register_then_closed(self):
        self.assertTrue(self.c.get("/api/auth/me/").json()["can_register"])
        r = self.c.post("/api/auth/register/", {"username": "ayush", "password": "short"}, format="json")
        self.assertEqual(r.status_code, 400)                                     # password too weak
        r = self.c.post("/api/auth/register/", {"username": "ayush", "password": "cricket-2026-ok"}, format="json")
        self.assertEqual((r.status_code, r.json()["authenticated"]), (201, True))
        self.assertTrue(User.objects.get(username="ayush").is_superuser)
        r = APIClient().post("/api/auth/register/", {"username": "intruder", "password": "cricket-2026-ok"}, format="json")
        self.assertEqual(r.status_code, 403)                                     # no second sign-up
        self.assertFalse(APIClient().get("/api/auth/me/").json()["can_register"])

    def test_signup_can_be_switched_off(self):
        from django.test import override_settings
        with override_settings(ALLOW_FIRST_RUN_SIGNUP=False):
            self.assertFalse(self.c.get("/api/auth/me/").json()["can_register"])
            r = self.c.post("/api/auth/register/", {"username": "ayush", "password": "cricket-2026-ok"}, format="json")
            self.assertEqual(r.status_code, 403)
            self.assertFalse(User.objects.exists())

    def test_only_the_live_view_is_public(self):
        owner = scorer_client()
        owner.post("/api/teams/", {"name": "P", "players": ["p1", "p2"]}, format="json")
        owner.post("/api/teams/", {"name": "Q", "players": ["q1", "q2"]}, format="json")
        t = {x["name"]: x["id"] for x in owner.get("/api/teams/").json()}
        m = owner.post("/api/matches/", {"team_a": t["P"], "team_b": t["Q"], "overs_limit": 1,
                                         "toss_winner": t["P"], "toss_decision": "bat"}, format="json").json()["id"]
        self.assertEqual(self.c.get(f"/api/matches/{m}/").status_code, 200)       # share link works for anyone
        for url in ("/api/matches/", "/api/teams/", "/api/stats/"):
            self.assertEqual(self.c.get(url).status_code, 403)                    # everything else needs a login
        self.assertEqual(self.c.post("/api/teams/", {"name": "X", "players": ["a", "b"]}, format="json").status_code, 403)
        self.assertEqual(self.c.delete(f"/api/matches/{m}/").status_code, 403)
        self.assertEqual(self.c.post(f"/api/matches/{m}/end/").status_code, 403)
        self.assertEqual(self.c.get("/api/auth/me/").status_code, 200)            # the sign-in page can always ask who you are

    def test_login_logout_and_csrf(self):
        User.objects.create_user("owner", password="cricket-2026-ok")
        c = APIClient(enforce_csrf_checks=True)
        c.get("/api/auth/me/")                                                   # sets the csrf cookie
        self.assertEqual(c.post("/api/auth/login/", {"username": "owner", "password": "nope"}, format="json").status_code, 400)
        r = c.post("/api/auth/login/", {"username": "owner", "password": "cricket-2026-ok"}, format="json")
        self.assertEqual((r.status_code, r.json()["username"]), (200, "owner"))
        body = {"name": "Kings", "players": ["a", "b"]}
        self.assertEqual(c.post("/api/teams/", body, format="json").status_code, 403)      # signed in but no csrf header
        token = c.cookies["csrftoken"].value
        self.assertEqual(c.post("/api/teams/", body, format="json", HTTP_X_CSRFTOKEN=token).status_code, 200)
        c.post("/api/auth/logout/", format="json", HTTP_X_CSRFTOKEN=token)
        self.assertFalse(c.get("/api/auth/me/").json()["authenticated"])

    def test_login_is_throttled(self):
        User.objects.create_user("owner", password="cricket-2026-ok")
        codes = [self.c.post("/api/auth/login/", {"username": "owner", "password": "bad"}, format="json").status_code
                 for _ in range(12)]
        self.assertEqual(codes[-1], 429)
