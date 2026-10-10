# The Crease (frontend + backend)

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
    │   ├── admin.py  admin_api.py  tests.py  migrations/
    └── frontend/                 FRONTEND
        ├── index.html            match list + player stats
        ├── new.html              new match setup
        ├── match.html            ?id=1&mode=score (scorer)  |  ?id=1&mode=live (shareable live view)
        ├── css/style.css
        └── js/  config.js  home.js  new.js  match.js


## Accounts

Opening the site shows the sign-in page first. New visitors land on **Create an account**: they register, then sign in.
Every account keeps its own teams, matches and stats, and can run one live match at a time. Only a match's live link
(`/match.html?id=1&mode=live`) is public, so you can share it with anyone.

- First run: the first account created becomes the owner (admin).
- The owner manages accounts and matches in Django's `/admin/` (the site has no admin button).
- Set `ALLOW_OPEN_SIGNUP=0` to close registration. Set `ALLOW_FIRST_RUN_SIGNUP=0` and run
  `python manage.py createsuperuser` to make the owner yourself on a public site.
- Teams and matches made before accounts had their own data are given to the first owner when you run `migrate`.
- Login attempts are limited to 10 per minute.

## Match rules, sharing and offline scoring

- **Rules** (optional, on the New match page): last man batting, free hit after a no-ball, max overs per bowler.
- **Share** a match from its page: WhatsApp, copy link, a QR code for the live link, or a scorecard image (PNG).
- **Overs tab**: run-progress chart, runs per over, ball-by-ball chips, fall of wickets and partnerships.
  Finished matches also show a player of the match and a short summary.
- **Passwords**: signed-in users can change their password on `account.html`. If someone forgets theirs, the owner sets a new one in `/admin/` (Users, pick the user, change password).
- **Offline scoring**: if the signal drops, the scorer keeps going. Scores are saved on the phone and sent when the
  connection returns. Pages are cached by `sw.js`, so a reload offline still opens the match. Offline, you can score
  balls, pick batters and bowlers, and undo scores taken since you went offline. When an innings ends offline, reconnect
  to start the next one. Ending or deleting a match needs a connection. The rules are mirrored in `frontend/js/engine.js`.
  `tools/engine_parity.js` (run by the test suite, needs Node) checks the offline engine against the server on random matches.
