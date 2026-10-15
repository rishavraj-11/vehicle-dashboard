# Vehicle Intelligence Dashboard (local prototype)

## Features
- FastAPI backend and responsive HTML/CSS/JS dashboard
- Simulated telemetry, stored in SQLite (`vehicle.db`)
- Loads existing `model.pkl` and `Scaler.pkl` if present
- Current engine-condition prediction
- Demo rule-based component alerts (not validated diagnostics)
- Mileage-based maintenance list with "Mark done"
- Recent coolant and battery chart

## Setup
1. Put `main.py`, `requirements.txt`, `templates/`, and `static/` in your Website folder.
2. Put your existing `model.pkl` and `Scaler.pkl` beside `main.py`.
3. Open terminal in that folder:
   ```bash
   python -m venv .venv
   ```
   Windows:
   ```powershell
   .venv\Scripts\activate
   ```
   macOS/Linux:
   ```bash
   source .venv/bin/activate
   ```
4. Install packages:
   ```bash
   pip install -r requirements.txt
   ```
5. Start:
   ```bash
   uvicorn main:app --reload
   ```
6. Open http://127.0.0.1:8000
   API docs: http://127.0.0.1:8000/docs

## Important model compatibility note
This backend assumes `model.pkl` was trained on the 11 vibration/temperature/acoustic/pressure features in `FEATURES`, and `Scaler.pkl` is the fitted scaler for those exact features, in the same order. If the saved model was trained on only two classes (0 and 1), it cannot predict class 2. Verify `model.classes_` and the actual target-label mapping in your notebook.

The vehicle sensor values in this dashboard are simulated and are not actual OBD-II readings. The displayed health score and alert rules are demo-only. Do not use them for real maintenance or safety decisions. The current model classifies engine condition; it does not predict future component failure. Add a separately trained predictive model after collecting suitable future-failure labels.


## Maintenance task controls
- Add tasks with a name and due mileage from the dashboard.
- Mark a task complete, then use Undo to return it to Upcoming.
- Tasks are stored in SQLite (`vehicle.db`) and remain after restarting the server.

## Update frequency
- Dashboard snapshots (other sensor values, engine prediction, alerts, health score, chart history) refresh every 15 seconds.
- Vehicle speed display animates smoothly every 250 milliseconds between snapshots.
- The Refresh data button still requests a fresh snapshot immediately.

## Manual refresh and maintenance toggle
- Dashboard readings no longer refresh automatically. Tap **Update readings** to generate and save a new simulated snapshot.
- Speed animates smoothly between the current and new snapshot, but does not independently generate new data.
- Maintenance completion toggle uses POST and PATCH-compatible routes; tap **Undo** to revert a completed task.
- If the browser still runs old JavaScript, use Ctrl+F5 after restarting the server.

## Important behavior fixes (v4)
- `GET /api/dashboard` is read-only and returns the latest saved snapshot.
- Only tapping **Update readings** calls `POST /api/simulate` to create new values.
- Mark done and Undo use explicit `/complete` and `/undo` routes.
- HTML uses cache-busted JS/CSS URLs; hard refresh browser after replacing files.
