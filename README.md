# 🏏 CricketLive

A live, ball-by-ball cricket scoring web application. Score matches from your phone and share a live link so anyone can follow the match in real time.

Built with **Django + Django REST Framework** on the backend and **HTML, CSS & JavaScript** on the frontend.

## Features

* 🏏 Ball-by-ball scoring — 0, 1, 2, 3, 4 and 6
* ➕ Extras — Wides, No Balls, Byes and Leg Byes
* 🏃 Wickets — Bowled, Caught, LBW, Stumped, Hit Wicket and Run Out
* 🔄 Undo the last ball
* 🎯 Automatic overs, target, runs needed and match result
* 🔗 Shareable live match link
* 📊 Batting and bowling scorecards
* 👥 Reusable teams and Playing 11
* 🏆 Top run scorers and wicket takers
* 📱 Mobile-friendly design
* 🔐 No login required for scoring

## Tech Stack

* **Backend:** Python, Django, Django REST Framework
* **Frontend:** HTML, CSS, JavaScript
* **Database:** SQLite

## Quick Start

```bash
git clone YOUR_REPOSITORY_URL
cd CricketLive

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

## How It Works

1. Create or select two teams.
2. Set overs and toss details.
3. Select the bowler and start scoring.
4. Record runs, extras and wickets ball by ball.
5. Share the live match link with spectators.
6. The match result and scorecard are updated automatically.

## API

| Method    | Endpoint                    | Description       |
| --------- | --------------------------- | ----------------- |
| GET, POST | `/api/teams/`               | Manage teams      |
| GET, POST | `/api/matches/`             | Manage matches    |
| GET       | `/api/matches/<id>/`        | Get match state   |
| POST      | `/api/matches/<id>/ball/`   | Record a ball     |
| POST      | `/api/matches/<id>/undo/`   | Undo last ball    |
| POST      | `/api/matches/<id>/select/` | Select player     |
| GET       | `/api/stats/`               | Player statistics |

## Project Structure

```text
manage.py
cricket_project/
scoring/
frontend/
├── index.html
├── new.html
├── match.html
├── css/
└── js/
requirements.txt
README.md
```

## Tests

```bash
python manage.py test scoring
```

## Author

**Ayush Chandel**

Python / Django Developer
