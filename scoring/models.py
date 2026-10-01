from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.db.models.functions import Lower


class Team(models.Model):
    # Not globally unique: deleting a team in the app only archives it (is_active=False), so old matches keep
    # their team. An archived team's name can be used again; active teams still need distinct names.
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, help_text="Untick to hide the team from new matches (old matches keep it).")

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("name"), condition=Q(is_active=True), name="unique_active_team_name"),
        ]

    def __str__(self):
        return self.name


class Player(models.Model):
    class Role(models.TextChoices):
        BATTER = "batter", "Batter"
        BOWLER = "bowler", "Bowler"
        ALL_ROUNDER = "allrounder", "All-rounder"

    name = models.CharField(max_length=100)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.ALL_ROUNDER)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="players")

    class Meta:
        unique_together = ("name", "team")

    def __str__(self):
        return f"{self.name} ({self.team.name})"


class Match(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        LIVE = "live", "Live"
        COMPLETED = "completed", "Completed"

    class TossDecision(models.TextChoices):
        BAT = "bat", "Bat"
        BOWL = "bowl", "Bowl"

    team_a = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="matches_as_a")
    team_b = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="matches_as_b")
    overs_limit = models.PositiveSmallIntegerField(default=6)
    toss_winner = models.ForeignKey(
        Team, on_delete=models.PROTECT, null=True, blank=True, related_name="tosses_won"
    )
    toss_decision = models.CharField(max_length=4, choices=TossDecision.choices, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UPCOMING)
    result = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "matches"
        ordering = ["-created_at"]

    def clean(self):
        if self.team_a_id and self.team_a_id == self.team_b_id:
            raise ValidationError("A team cannot play against itself.")
        if self.toss_winner_id and self.toss_winner_id not in (self.team_a_id, self.team_b_id):
            raise ValidationError("Toss winner must be one of the two teams.")

    def __str__(self):
        return f"{self.team_a} vs {self.team_b}"


class Innings(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="innings")
    number = models.PositiveSmallIntegerField(default=1)  # 1 or 2
    batting_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="+")
    bowling_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="+")
    is_complete = models.BooleanField(default=False)
    # Who is at the crease right now. A null slot means "waiting for a selection":
    # a null striker/non_striker needs a new batter, a null bowler needs the next over's bowler.
    striker = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    non_striker = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    bowler = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = ("match", "number")
        ordering = ["match", "number"]
        verbose_name_plural = "innings"

    # Everything below is derived from Ball rows: single source of truth.
    @property
    def total_runs(self):
        agg = self.balls.aggregate(bat=Sum("runs_off_bat"), extra=Sum("extra_runs"))
        return (agg["bat"] or 0) + (agg["extra"] or 0)

    @property
    def wickets(self):
        return self.balls.exclude(wicket_type="").count()

    @property
    def legal_balls(self):
        return self.balls.exclude(
            extra_type__in=[Ball.Extra.WIDE, Ball.Extra.NO_BALL]
        ).count()

    @property
    def overs_display(self):
        return f"{self.legal_balls // 6}.{self.legal_balls % 6}"

    @property
    def run_rate(self):
        if not self.legal_balls:
            return 0.0
        return round(self.total_runs * 6 / self.legal_balls, 2)

    def __str__(self):
        return f"{self.batting_team} innings {self.number} ({self.match})"


class Ball(models.Model):
    class Extra(models.TextChoices):
        NONE = "", "None"
        WIDE = "wd", "Wide"
        NO_BALL = "nb", "No ball"
        BYE = "b", "Bye"
        LEG_BYE = "lb", "Leg bye"

    class Wicket(models.TextChoices):
        NONE = "", "None"
        BOWLED = "bowled", "Bowled"
        CAUGHT = "caught", "Caught"
        LBW = "lbw", "LBW"
        RUN_OUT = "run_out", "Run out"
        STUMPED = "stumped", "Stumped"
        HIT_WICKET = "hit_wicket", "Hit wicket"

    innings = models.ForeignKey(Innings, on_delete=models.CASCADE, related_name="balls")
    over_number = models.PositiveSmallIntegerField()  # 0-based: first over is 0
    ball_in_over = models.PositiveSmallIntegerField()  # legal balls so far in the over (1-6); an illegal ball stores the count before it
    batter = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="balls_faced")
    non_striker = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="+")
    bowler = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="balls_bowled")
    runs_off_bat = models.PositiveSmallIntegerField(default=0)
    extra_type = models.CharField(max_length=2, choices=Extra.choices, blank=True, default="")
    extra_runs = models.PositiveSmallIntegerField(default=0)
    wicket_type = models.CharField(max_length=12, choices=Wicket.choices, blank=True, default="")
    dismissed_player = models.ForeignKey(
        Player, on_delete=models.PROTECT, null=True, blank=True, related_name="dismissals"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]  # delivery order; undo = delete the last row

    @property
    def is_legal(self):
        return self.extra_type not in (self.Extra.WIDE, self.Extra.NO_BALL)

    @property
    def total_runs(self):
        return self.runs_off_bat + self.extra_runs

    def save(self, *args, **kwargs):
        # Wides and no-balls carry an automatic 1-run penalty if none was given.
        if self.extra_type in (self.Extra.WIDE, self.Extra.NO_BALL) and self.extra_runs == 0:
            self.extra_runs = 1
        # Wicket with no explicit dismissed player: the striker is out.
        if self.wicket_type and not self.dismissed_player_id:
            self.dismissed_player = self.batter
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.over_number}.{self.ball_in_over} {self.batter} - {self.total_runs}"
