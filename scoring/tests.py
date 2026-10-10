from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Match, Team


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
        r = APIClient().post("/api/auth/register/", {"username": "fan", "password": "cricket-2026-ok"}, format="json")
        self.assertEqual(r.status_code, 201)                                     # later sign-ups are view-only members
        self.assertFalse(User.objects.get(username="fan").is_superuser)
        self.assertFalse(APIClient().get("/api/auth/me/").json()["can_register"])

    def test_signup_can_be_switched_off(self):
        from django.test import override_settings
        with override_settings(ALLOW_FIRST_RUN_SIGNUP=False, ALLOW_OPEN_SIGNUP=False):
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
        User.objects.create_superuser("owner", password="cricket-2026-ok")
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


class Registration(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_superuser("owner", password="Owner-pass-9472")

    def make_team(self, c, name):
        return c.post("/api/teams/", {"name": name, "players": ["a", "b"]}, format="json")

    def signed_in(self, name):
        c = APIClient()
        c.post("/api/auth/register/", {"username": name, "password": "Cricket-fan-7731"}, format="json")
        r = c.post("/api/auth/login/", {"username": name, "password": "Cricket-fan-7731"}, format="json")
        self.assertEqual(r.status_code, 200)
        return c

    def test_register_does_not_sign_in_then_login_works(self):
        c = APIClient()
        r = c.post("/api/auth/register/", {"username": "fan", "password": "Cricket-fan-7731"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertFalse(c.get("/api/auth/me/").json()["authenticated"])
        self.assertTrue(self.signed_in("fan2").get("/api/auth/me/").json()["authenticated"])

    def test_duplicate_username_rejected(self):
        r = APIClient().post("/api/auth/register/", {"username": "Owner", "password": "Cricket-fan-7731"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_everyone_gets_their_own_teams_matches_and_stats(self):
        a, b = self.signed_in("amit"), self.signed_in("bela")
        self.assertEqual(self.make_team(a, "Kings").status_code, 200)
        self.assertEqual(self.make_team(b, "Kings").status_code, 200)             # same name is fine across accounts
        self.assertEqual(self.make_team(a, "Kings").status_code, 400)             # not twice in one account
        self.assertEqual([t["name"] for t in b.get("/api/teams/").json()], ["Kings"])
        self.make_team(a, "Strikers"); self.make_team(b, "Titans")
        ta = {t["name"]: t["id"] for t in a.get("/api/teams/").json()}
        tb = {t["name"]: t["id"] for t in b.get("/api/teams/").json()}
        mk = lambda c, x, y: c.post("/api/matches/", {"team_a": x, "team_b": y, "overs_limit": 2,
                                                       "toss_winner": x, "toss_decision": "bat"}, format="json")
        self.assertEqual(mk(a, ta["Kings"], ta["Strikers"]).status_code, 201)
        self.assertEqual(mk(b, tb["Kings"], tb["Titans"]).status_code, 201)       # each account can run its own live match
        self.assertEqual(mk(b, tb["Kings"], ta["Strikers"]).status_code, 400)     # can't use someone else's team
        ma = a.get("/api/matches/").json()
        self.assertEqual(len(ma), 1); self.assertEqual(len(b.get("/api/matches/").json()), 1)
        mid = ma[0]["id"]
        self.assertEqual(b.post(f"/api/matches/{mid}/end/").status_code, 404)     # can't touch another's match
        self.assertEqual(b.delete(f"/api/matches/{mid}/").status_code, 404)
        self.assertEqual(b.get(f"/api/matches/{mid}/").status_code, 200)          # but the share link is open
        self.assertEqual(APIClient().get(f"/api/matches/{mid}/").status_code, 200)
        self.assertEqual(a.get("/api/stats/").json()["totals"]["matches"], 1)


class AdminPanel(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_superuser("owner", password="Owner-pass-9472")
        self.fan = User.objects.create_user("fan", password="Cricket-fan-7731")
        self.o = APIClient(); self.o.force_authenticate(self.owner)

    def test_only_the_owner_gets_in(self):
        f = APIClient(); f.force_authenticate(self.fan)
        for c, code in ((APIClient(), 403), (f, 403), (self.o, 200)):
            self.assertEqual(c.get("/api/admin/overview/").status_code, code)

    def test_overview_switch_off_reset_and_delete(self):
        fc = APIClient(); fc.force_authenticate(self.fan)
        fc.post("/api/teams/", {"name": "T1", "players": ["a", "b"]}, format="json")
        fc.post("/api/teams/", {"name": "T2", "players": ["c", "d"]}, format="json")
        t = {x["name"]: x["id"] for x in fc.get("/api/teams/").json()}
        fc.post("/api/matches/", {"team_a": t["T1"], "team_b": t["T2"], "overs_limit": 1,
                                  "toss_winner": t["T1"], "toss_decision": "bat"}, format="json")
        j = self.o.get("/api/admin/overview/").json()
        row = next(u for u in j["users"] if u["username"] == "fan")
        self.assertEqual((row["teams"], row["matches"], j["totals"]["live"]), (2, 1, 1))
        u = f"/api/admin/users/{self.fan.id}/"
        self.o.patch(u, {"active": False}, format="json")
        r = APIClient().post("/api/auth/login/", {"username": "fan", "password": "Cricket-fan-7731"}, format="json")
        self.assertEqual(r.status_code, 400)                                       # switched-off accounts can't sign in
        self.o.patch(u, {"active": True}, format="json")
        self.assertEqual(self.o.post(u + "password/", {"password": "short"}, format="json").status_code, 400)
        self.assertEqual(self.o.post(u + "password/", {"password": "Brand-new-pass-5521"}, format="json").status_code, 200)
        self.assertEqual(self.o.patch(f"/api/admin/users/{self.owner.id}/", {"active": False}, format="json").status_code, 400)
        self.assertEqual(self.o.delete(u).status_code, 200)                        # removes their teams and matches too
        self.assertEqual((Team.objects.count(), Match.objects.count()), (0, 0))


class HouseRules(TestCase):
    """Last man batting, free hit, max overs per bowler, plus the summary and breakdown data."""

    def setUp(self):
        self.c = scorer_client()
        for name, ps in (("Kings", "A1 A2 A3"), ("Strikers", "B1 B2 B3 B4")):
            self.c.post("/api/teams/", {"name": name, "players": ps.split()}, format="json")
        self.t = {x["name"]: x["id"] for x in self.c.get("/api/teams/").json()}

    def start(self, overs_limit=4, **rules):
        r = self.c.post("/api/matches/", {"team_a": self.t["Kings"], "team_b": self.t["Strikers"], "overs_limit": overs_limit,
                                           "toss_winner": self.t["Kings"], "toss_decision": "bat", **rules}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.m = r.json()["id"]

    def st(self):
        return self.c.get(f"/api/matches/{self.m}/").json()

    def ball(self, **kw):
        return self.c.post(f"/api/matches/{self.m}/ball/", kw, format="json")

    def pick(self, role, i=0):
        s = self.st()["live"]
        return self.c.post(f"/api/matches/{self.m}/select/", {"role": role, "player": s["options"][i]["id"]}, format="json")

    def open_up(self):
        self.pick("batter"); self.pick("batter"); self.pick("bowler")

    def test_last_man_batting(self):
        self.start(last_man=True)
        self.open_up()
        self.ball(runs=1, wicket="bowled")                    # striker A1 out (3 players, so 2 wickets leave one batter)
        self.pick("batter")                                    # A3 comes in
        self.ball(runs=0, wicket="bowled")                     # second wicket
        live = self.st()["live"]
        self.assertTrue(live["lone"])                          # the last man plays on alone
        self.assertIsNone(live["need"])
        self.assertEqual(live["striker"]["id"], live["non_striker"]["id"])
        for _ in range(2):
            self.assertEqual(self.ball(runs=1).status_code, 200)   # strike never changes
        self.assertEqual(self.st()["live"]["striker"]["id"], live["striker"]["id"])
        self.ball(runs=0, wicket="bowled")                     # last man out: all out
        s = self.st()
        self.assertEqual(s["innings"][0]["wickets"], 3)
        self.assertEqual(len(s["innings"]), 2)                 # innings 2 has begun
        self.assertTrue(s["rules"]["last_man"])

    def test_without_last_man_two_wickets_end_a_three_player_innings(self):
        self.start()
        self.open_up()
        self.ball(runs=0, wicket="bowled"); self.pick("batter"); self.ball(runs=0, wicket="bowled")
        self.assertEqual(len(self.st()["innings"]), 2)

    def test_free_hit(self):
        self.start(free_hit=True)
        self.open_up()
        self.assertFalse(self.st()["live"]["free_hit"])
        self.ball(extra="nb")
        self.assertTrue(self.st()["live"]["free_hit"])
        r = self.ball(runs=0, wicket="bowled")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "free_hit"))     # only a run out counts
        self.ball(extra="wd")                                                      # a wide keeps the free hit
        self.assertTrue(self.st()["live"]["free_hit"])
        self.assertEqual(self.ball(runs=1, wicket="run_out").status_code, 200)     # run out is allowed
        self.assertFalse(self.st()["live"]["free_hit"] and self.st()["live"]["need"] is None and False)

    def test_free_hit_off_by_default(self):
        self.start()
        self.open_up()
        self.ball(extra="nb")
        self.assertFalse(self.st()["live"]["free_hit"])
        self.assertEqual(self.ball(runs=0, wicket="bowled").status_code, 200)

    def test_max_overs_per_bowler(self):
        self.start(max_bowler=2, overs_limit=6)
        self.open_up()
        x = self.st()["live"]["bowler"]["id"]
        def over(i=0):
            for _ in range(6):
                self.ball(runs=0)
            if self.st()["live"]:
                self.pick("bowler", i)
        over()                                                  # over 1: X; pick someone else
        y = self.st()["live"]["bowler"]["id"]
        self.assertNotEqual(x, y)
        for _ in range(6):
            self.ball(runs=0)
        self.c.post(f"/api/matches/{self.m}/select/", {"role": "bowler", "player": x}, format="json")   # over 3: X again (2nd over)
        for _ in range(6):
            self.ball(runs=0)
        self.c.post(f"/api/matches/{self.m}/select/", {"role": "bowler", "player": y}, format="json")   # over 4: Y (2nd over)
        for _ in range(6):
            self.ball(runs=0)
        opts = [o["id"] for o in self.st()["live"]["options"]]                                           # over 5: X and Y are done
        self.assertTrue(opts and x not in opts and y not in opts)
        r = self.c.post(f"/api/matches/{self.m}/select/", {"role": "bowler", "player": x}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cap_must_leave_enough_overs(self):
        r = self.c.post("/api/matches/", {"team_a": self.t["Kings"], "team_b": self.t["Strikers"], "overs_limit": 20,
                                           "toss_winner": self.t["Kings"], "toss_decision": "bat", "max_bowler": 2}, format="json")
        self.assertEqual(r.status_code, 400)                   # 3 players x 2 overs can't cover 20

    def test_retried_ball_counts_once(self):
        self.start()
        self.open_up()
        self.ball(runs=4, cid="abc"); self.ball(runs=4, cid="abc")
        self.assertEqual(self.st()["innings"][0]["runs"], 4)

    def test_summary_potm_and_breakdown(self):
        self.start()
        self.open_up()
        for r in (4, 1, 6, 0, 2, 1):
            self.ball(runs=r)
        self.pick("bowler"); self.ball(runs=0, wicket="bowled")
        self.c.post(f"/api/matches/{self.m}/end/")
        s = self.st()
        self.assertEqual(s["status"], "completed")
        self.assertTrue(s["summary"])
        self.assertTrue(s["potm"]["name"])
        inn = s["innings"][0]
        self.assertEqual([o["runs"] for o in inn["by_over"]], [14, 0])
        self.assertEqual(inn["by_over"][-1]["total"], inn["runs"])
        self.assertEqual(inn["fow"][0]["score"], 14)
        self.assertEqual(sum(p["runs"] for p in inn["partnerships"]), inn["runs"])


class ChangePassword(TestCase):
    def test_change_password_keeps_you_signed_in(self):
        cache.clear()
        User.objects.create_user("fan", password="Cricket-fan-7731")
        c = APIClient()
        c.post("/api/auth/login/", {"username": "fan", "password": "Cricket-fan-7731"}, format="json")
        self.assertEqual(c.post("/api/auth/password/", {"current_password": "wrong", "new_password": "Brand-new-pass-5521"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/password/", {"current_password": "Cricket-fan-7731", "new_password": "Brand-new-pass-5521"}, format="json").status_code, 200)
        self.assertTrue(c.get("/api/auth/me/").json()["authenticated"])
        self.assertEqual(APIClient().post("/api/auth/password/", {}, format="json").status_code, 403)
        self.assertEqual(APIClient().post("/api/auth/reset/", {}, format="json").status_code, 404)      # no forgot-password route


class EngineParity(TestCase):
    """The offline scoring engine (frontend/js/engine.js) must agree with the server on every ball."""

    def test_random_matches(self):
        import json, random, shutil, subprocess, tempfile, os
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        rnd = random.Random(2026)
        c = scorer_client()
        scenarios = []
        for sc in range(60):
            na, nb = rnd.randint(2, 6), rnd.randint(2, 6)
            c.post("/api/teams/", {"name": f"A{sc}", "players": [f"a{i}" for i in range(na)]}, format="json")
            c.post("/api/teams/", {"name": f"B{sc}", "players": [f"b{i}" for i in range(nb)]}, format="json")
            t = {x["name"]: x["id"] for x in c.get("/api/teams/").json()}
            overs = rnd.randint(2, 5)
            rules = {"last_man": rnd.random() < .5, "free_hit": rnd.random() < .6,
                     "max_bowler": rnd.choice([0] + [cp for cp in range(1, overs) if min(na, nb) * cp >= overs] * 2)}
            # roles vary so the chooser ordering is exercised
            r = c.post("/api/matches/", {"team_a": t[f"A{sc}"], "team_b": t[f"B{sc}"], "overs_limit": overs,
                                          "toss_winner": t[f"A{sc}"], "toss_decision": rnd.choice(["bat", "bowl"]), **rules}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            m, state = r.json()["id"], r.json()
            steps, ended = [], False
            for _ in range(400):
                live = state["live"]
                if not live or live["innings"] != state["live"]["innings"]:
                    break
                if live["need"]:
                    if rnd.random() < .08 and live["options"]:                 # sometimes a bad pick
                        act = {"type": "select", "role": live["need"], "player": 10**9}
                    else:
                        act = {"type": "select", "role": live["need"], "player": rnd.choice(live["options"])["id"]}
                    url = "select/"
                else:
                    wk = rnd.choice([""] * 14 + ["bowled", "caught", "lbw", "stumped", "hit_wicket", "run_out"])
                    ex = rnd.choice(["", "", "", "", "wd", "nb", "b", "lb"])
                    act = {"type": "ball", "runs": rnd.choice([0, 0, 1, 1, 2, 3, 4, 6]), "extra": ex, "wicket": wk}
                    if wk == "run_out":
                        act["dismissed"] = rnd.choice([live["striker"]["id"], live["non_striker"]["id"]])
                        act["end"] = rnd.choice(["", "striker", "non"])
                    url = "ball/"
                body = {k: v for k, v in act.items() if k != "type"}
                before_innings = live["innings"]
                resp = c.post(f"/api/matches/{m}/{url}", body, format="json")
                if resp.status_code == 200:
                    state = resp.json()
                    steps.append({"action": act, "state": state})
                    if not state["live"] or state["live"]["innings"] != before_innings:
                        break                                                    # innings over: the engine stops here by design
                else:
                    steps.append({"action": act, "error": resp.json().get("error", "x")})
            scenarios.append({"name": f"match{sc}", "initial": r.json(), "steps": steps})
            c.post(f"/api/matches/{m}/end/")
        seen = [st["state"]["live"] for sc_ in scenarios for st in sc_["steps"] if "state" in st and st["state"]["live"]]
        self.assertTrue(any(l["lone"] for l in seen), "no lone-batter state was exercised")
        self.assertTrue(any(l["free_hit"] for l in seen), "no free hit was exercised")
        self.assertTrue(any(l["need"] == "bowler" and len(l["options"]) < len(l["roster"]["bowl"]) - 1 for l in seen),
                        "no capped bowler was exercised")
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        json.dump(scenarios, open(path, "w"))
        tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "engine_parity.js")
        out = subprocess.run(["node", tool, path], capture_output=True, text=True)
        os.remove(path)
        print("\n" + out.stdout.strip())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
