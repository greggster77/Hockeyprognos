# Hockeyprognos – iPhone PWA

A mobile-first Swedish PWA and FastAPI backend for 1X2 probabilities **after 60 minutes**. Leagues: SHL, HockeyAllsvenskan, NHL.

## Important current limitations

- **No public URL has been deployed.** Deploy to your own Render account to obtain a link.
- NHL data is retrieved from the NHL public API; data availability and schema may change. Finished games are only imported when period-by-period scoring is available, so overtime/shootout cannot corrupt 1X2 training.
- SHL and HockeyAllsvenskan require a separately configured, permitted data feed. Until configured, the UI explicitly displays a data-source error. No fictitious matches are generated.
- Initial Elo/form predictions need at least 20 completed matches in a league and at least 3 home and away appearances respectively. No predictions appear before that threshold.
- SQLite on a persistent Render disk is used for a one-instance evaluation build; PostgreSQL and Alembic migration are recommended for production. This is a change from the original PostgreSQL specification, not a production-ready replacement.
- The backend syncs every 3 hours. Predictions are stored once for each future match; results are scored with Brier after the 60-minute outcome is available.

## Deploy entirely from iPhone

1. Create a GitHub repository from these project files (upload the unzipped files; GitHub's web UI may be cumbersome on mobile).
2. Sign in to Render.com and connect your GitHub repository.
3. Select **New > Blueprint** and choose the repository. `render.yaml` provisions a web service and a persistent disk. This is a paid configuration.
4. Add licensed SHL/HA provider URLs and bearer tokens as private environment variables when available. Leave them blank to show explicit errors rather than fake matches.
5. After deployment, open the `https://...onrender.com` URL in Safari, tap **Share > Add to Home Screen**.

## Local run

```bash
cd Hockeyprognos
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn main:app --app-dir backend --reload
```

Open http://localhost:8000 . API: `/api/leagues`, `/api/matches?day=YYYY-MM-DD&league=NHL`, `/api/matches/{id}`, `/api/performance`.

## Swedish feed contract

A private `SHL_FEED_URL` or `HA_FEED_URL` returns an array of objects:

```
[{"id":"provider-game-id","date":"2026-11-18T18:00:00Z","home_id":"club-a","away_id":"club-b","home_name":"Club A","away_name":"Club B","status":"FINISHED","home_goals":2,"away_goals":2}]
```

For `FINISHED`, `home_goals` and `away_goals` **must be the score after 60 minutes**, not the final score after OT/SO. Use `SCHEDULED` with null goals for future fixtures. Never put bearer tokens in `web/`.

## Statistical model

Elo updates and separate home/away goal form; league home/away scoring rates; Poisson scores 0–8; 1X2 percentages allocated in hundredths by largest remainder, guaranteeing exact 100.00%. See `backend/model.py`.
