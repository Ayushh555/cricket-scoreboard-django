# Gully Scorer (frontend + backend)

Ball-by-ball cricket scorer. Django REST API + plain HTML/CSS/JS frontend, one project, one command.

    python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py runserver

Open http://127.0.0.1:8000/  ->  New match.   Tests: python manage.py test scoring

    cricket_scorer/
    ├── manage.py
    ├── cricket_project/          settings.py, urls.py (also serves frontend/)
    ├── scoring/                  BACKEND
    │   ├── models.py             Team, Player, Match, Innings, Ball
    │   ├── services.py           cricket rules: overs, extras, wickets, target, result, undo
    │   ├── views.py  urls.py     REST API under /api/
    │   ├── admin.py  tests.py  migrations/
    └── frontend/                 FRONTEND
        ├── index.html            match list + player stats
        ├── new.html              new match setup
        ├── match.html            ?id=1&mode=score (scorer)  |  ?id=1&mode=live (shareable live view)
        ├── css/style.css
        └── js/  config.js  home.js  new.js  match.js


## Accounts, teams and records

- No login: anyone who opens the site can score. Share a read-only view with `match.html?id=1&mode=live`.
- A team can be picked again and again for new matches. Typing the name of a saved team (with no new players) reuses it.
- "Delete team" on the New match page only archives the team: it disappears from the pickers and its name can be reused,
  but every match, scorecard and player stat stays. Teams in an unfinished match can't be deleted.
- There is no way to delete a match from the app. Matches, innings, balls and teams are erased only from `/admin/`
  (create an admin with `python manage.py createsuperuser`; untick "Is active" there to archive/restore a team).

## Run out

Tap **Run out** in the scoring screen, pick who is out, pick the end it happened at (the new batter takes that end,
so strike is right even if the batters crossed), then tap the runs completed. Works off wides, no balls, byes and leg byes.
The wicket counts for the team, not the bowler, and shows as "run out" on the scorecard. Undo restores both batters.
