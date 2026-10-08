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
    │   ├── admin.py  tests.py  migrations/
    └── frontend/                 FRONTEND
        ├── index.html            match list + player stats
        ├── new.html              new match setup
        ├── match.html            ?id=1&mode=score (scorer)  |  ?id=1&mode=live (shareable live view)
        ├── css/style.css
        └── js/  config.js  home.js  new.js  match.js

    🚧 **Project Status:**  This Project is Under Development


## Sign in

Opening the site shows the sign-in page first. Only a match's live link (`/match.html?id=1&mode=live`) is public, so you can
share it with anyone. Everything else needs the scorer's login.

- First run: open the site, go to **New match**, and it asks you to create the scorer account.
- On a public site set the environment variable `ALLOW_FIRST_RUN_SIGNUP=0` and create the account yourself
  with `python manage.py createsuperuser`. More scorers can be added in `/admin/`.
- Login attempts are limited to 10 per minute.
