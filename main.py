from pathlib import Path
from datetime import datetime, timezone
import random
import sqlite3
import json

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "vehicle.db"
MODEL_PATH = BASE_DIR / "model.pkl"
SCALER_PATH = BASE_DIR / "Scaler.pkl"

FEATURES = [
    "Vibration_Amplitude",
    "RMS_Vibration",
    "Vibration_Frequency",
    "Surface_Temperature",
    "Exhaust_Temperature",
    "Acoustic_dB",
    "Acoustic_Frequency",
    "Intake_Pressure",
    "Exhaust_Pressure",
    "Frequency_Band_Energy",
    "Amplitude_Mean",
]

app = FastAPI(title="Vehicle Intelligence Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# The app still starts if model files are not present, but ML predictions will be unavailable.
model = None
scaler = None
model_load_error = None

try:
    if MODEL_PATH.exists() and SCALER_PATH.exists():
        model = joblib.load(MODEL_PATH)
        scaler = joblib.load(SCALER_PATH)
    else:
        model_load_error = "model.pkl and/or Scaler.pkl not found."
except Exception as exc:
    model_load_error = str(exc)


def connect_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                data_json TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS maintenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                due_mileage INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Upcoming'
            )
        """)
        count = con.execute("SELECT COUNT(*) FROM maintenance").fetchone()[0]
        if count == 0:
            con.executemany(
                "INSERT INTO maintenance (task, due_mileage, status) VALUES (?, ?, ?)",
                [
                    ("Engine oil and filter", 48500, "Upcoming"),
                    ("General vehicle inspection", 50000, "Upcoming"),
                    ("Air filter inspection", 51000, "Upcoming"),
                ],
            )


init_db()


class SensorInput(BaseModel):
    Vibration_Amplitude: float = Field(ge=0)
    RMS_Vibration: float = Field(ge=0)
    Vibration_Frequency: float = Field(ge=0)
    Surface_Temperature: float
    Exhaust_Temperature: float
    Acoustic_dB: float
    Acoustic_Frequency: float = Field(ge=0)
    Intake_Pressure: float
    Exhaust_Pressure: float
    Frequency_Band_Energy: float = Field(ge=0)
    Amplitude_Mean: float


def make_simulated_reading():
    # Demo values only. These are not real vehicle OBD-II measurements.
    return {
        "Vibration_Amplitude": round(random.uniform(0.5, 4.0), 2),
        "RMS_Vibration": round(random.uniform(0.1, 2.0), 2),
        "Vibration_Frequency": round(random.uniform(30, 600), 1),
        "Surface_Temperature": round(random.uniform(45, 105), 1),
        "Exhaust_Temperature": round(random.uniform(220, 480), 1),
        "Acoustic_dB": round(random.uniform(65, 100), 1),
        "Acoustic_Frequency": round(random.uniform(150, 3000), 1),
        "Intake_Pressure": round(random.uniform(92, 115), 1),
        "Exhaust_Pressure": round(random.uniform(82, 105), 1),
        "Frequency_Band_Energy": round(random.uniform(0.1, 5.0), 3),
        "Amplitude_Mean": round(random.uniform(0.02, 0.4), 3),
        "engine_rpm": random.randint(750, 3200),
        "battery_voltage_v": round(random.uniform(12.1, 14.5), 2),
        "coolant_temperature_c": round(random.uniform(75, 105), 1),
        "vehicle_speed_kmh": random.randint(0, 100),
        "mileage_km": 48000,
        "data_source": "SIMULATED",
    }


def current_engine_prediction(reading):
    if model is None or scaler is None:
        return {
            "available": False,
            "label": "Model unavailable",
            "class_id": None,
            "probabilities": {},
            "note": model_load_error or "Model files not loaded.",
        }

    try:
        row = pd.DataFrame([[reading[name] for name in FEATURES]], columns=FEATURES)
        scaled = scaler.transform(row)
        prediction = model.predict(scaled)[0]
        probabilities = {}
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(scaled)[0]
            probabilities = {
                str(label): round(float(prob), 4)
                for label, prob in zip(model.classes_, probs)
            }

        # This dataset has 0=Normal, 1=Minor Fault, 2=Critical Fault.
        # If the saved model only has classes 0 and 1, label 1 remains Minor Fault.
        label_map = {0: "Normal", 1: "Minor Fault", 2: "Critical Fault"}
        try:
            class_id = int(prediction)
        except (TypeError, ValueError):
            class_id = None
        label = label_map.get(class_id, str(prediction))

        return {
            "available": True,
            "label": label,
            "class_id": class_id,
            "probabilities": probabilities,
            "note": "Prediction from the saved engine-condition model.",
        }
    except Exception as exc:
        return {
            "available": False,
            "label": "Prediction error",
            "class_id": None,
            "probabilities": {},
            "note": str(exc),
        }


def demo_rule_alerts(reading):
    # Demonstration rules only, not validated automotive diagnostic thresholds.
    alerts = []
    if reading["battery_voltage_v"] < 12.2:
        alerts.append({
            "severity": "warning",
            "title": "Battery voltage is low",
            "detail": "Demo rule triggered. Verify voltage using a suitable diagnostic procedure."
        })
    if reading["coolant_temperature_c"] >= 102:
        alerts.append({
            "severity": "warning",
            "title": "Coolant temperature is elevated",
            "detail": "Demo rule triggered. Check the vehicle's specified operating range."
        })
    if reading["RMS_Vibration"] >= 1.7:
        alerts.append({
            "severity": "warning",
            "title": "Elevated vibration reading",
            "detail": "Demo rule triggered. Inspect vibration trends before taking action."
        })
    if not alerts:
        alerts.append({
            "severity": "info",
            "title": "No demo rule alerts",
            "detail": "This does not prove the vehicle is fault-free."
        })
    return alerts


def save_reading(reading):
    timestamp = datetime.now(timezone.utc).isoformat()
    with connect_db() as con:
        con.execute(
            "INSERT INTO telemetry (timestamp, data_json) VALUES (?, ?)",
            (timestamp, json.dumps(reading)),
        )
    return timestamp


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "engine_model_loaded": model is not None,
        "scaler_loaded": scaler is not None,
        "model_load_error": model_load_error,
        "data_source": "SIMULATED",
    }



def get_latest_reading():
    with connect_db() as con:
        row = con.execute(
            "SELECT timestamp, data_json FROM telemetry ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row:
        return row["timestamp"], json.loads(row["data_json"])

    # Create exactly one initial snapshot if the database is empty.
    reading = make_simulated_reading()
    timestamp = save_reading(reading)
    return timestamp, reading


@app.get("/api/dashboard")
def dashboard():
    # GET is read-only: it never generates new random values.
    timestamp, reading = get_latest_reading()
    prediction = current_engine_prediction(reading)
    alerts = demo_rule_alerts(reading)

    # Demo health score only; not a validated vehicle health metric.
    health_score = 100
    if reading["coolant_temperature_c"] >= 100:
        health_score -= 8
    if reading["battery_voltage_v"] < 12.2:
        health_score -= 8
    if reading["RMS_Vibration"] >= 1.7:
        health_score -= 5

    with connect_db() as con:
        maintenance = [
            dict(row) for row in con.execute(
                "SELECT id, task, due_mileage, status FROM maintenance ORDER BY due_mileage"
            ).fetchall()
        ]
        history_rows = con.execute(
            "SELECT timestamp, data_json FROM telemetry ORDER BY id DESC LIMIT 20"
        ).fetchall()

    history = []
    for row in reversed(history_rows):
        item = json.loads(row["data_json"])
        history.append({
            "timestamp": row["timestamp"],
            "coolant_temperature_c": item.get("coolant_temperature_c"),
            "battery_voltage_v": item.get("battery_voltage_v"),
            "rpm": item.get("engine_rpm"),
        })

    return {
        "timestamp": timestamp,
        "data_source": "SIMULATED",
        "vehicle": {
            "make": "Demo vehicle",
            "model": "Prototype",
            "year": 2022,
            "fuel_type": "Petrol",
            "mileage_km": reading.get("mileage_km", 48000),
        },
        "reading": reading,
        "engine_condition": prediction,
        "alerts": alerts,
        "maintenance": maintenance,
        "health_score": health_score,
        "history": history,
    }


@app.post("/api/predict-engine")
def predict_engine(data: SensorInput):
    reading = data.model_dump() if hasattr(data, "model_dump") else data.dict()
    prediction = current_engine_prediction(reading)
    if not prediction["available"]:
        raise HTTPException(status_code=503, detail=prediction["note"])
    return prediction


@app.post("/api/simulate")
def simulate():
    # Only this explicit action generates new random simulated values.
    reading = make_simulated_reading()
    timestamp = save_reading(reading)
    return {"timestamp": timestamp, "reading": reading, "data_source": "SIMULATED"}


@app.get("/api/maintenance")
def get_maintenance():
    with connect_db() as con:
        rows = con.execute(
            "SELECT id, task, due_mileage, status FROM maintenance ORDER BY due_mileage"
        ).fetchall()
    return [dict(row) for row in rows]


class MaintenanceInput(BaseModel):
    task: str = Field(min_length=2, max_length=120)
    due_mileage: int = Field(ge=0, le=2_000_000)


@app.post("/api/maintenance")
def add_maintenance(data: MaintenanceInput):
    task_name = data.task.strip()
    if not task_name:
        raise HTTPException(status_code=422, detail="Task name cannot be empty.")

    with connect_db() as con:
        cur = con.execute(
            "INSERT INTO maintenance (task, due_mileage, status) VALUES (?, ?, 'Upcoming')",
            (task_name, data.due_mileage),
        )
        task_id = cur.lastrowid

    return {
        "id": task_id,
        "task": task_name,
        "due_mileage": data.due_mileage,
        "status": "Upcoming",
    }


def set_maintenance_status(task_id: int, status: str):
    with connect_db() as con:
        row = con.execute(
            "SELECT id FROM maintenance WHERE id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Maintenance task not found.")
        con.execute(
            "UPDATE maintenance SET status=? WHERE id=?",
            (status, task_id),
        )
    return {"status": status, "task_id": task_id}


@app.post("/api/maintenance/{task_id}/complete")
def complete_maintenance(task_id: int):
    return set_maintenance_status(task_id, "Completed")


@app.post("/api/maintenance/{task_id}/undo")
def undo_maintenance(task_id: int):
    return set_maintenance_status(task_id, "Upcoming")


@app.patch("/api/maintenance/{task_id}/status")
@app.post("/api/maintenance/{task_id}/status")
def update_maintenance_status(task_id: int):
    # Backward-compatible toggle route.
    with connect_db() as con:
        row = con.execute(
            "SELECT status FROM maintenance WHERE id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Maintenance task not found.")
        new_status = "Upcoming" if row["status"] == "Completed" else "Completed"
        con.execute("UPDATE maintenance SET status=? WHERE id=?", (new_status, task_id))
    return {"status": new_status, "task_id": task_id}


@app.get("/api/history")
def get_history():
    with connect_db() as con:
        rows = con.execute(
            "SELECT timestamp, data_json FROM telemetry ORDER BY id DESC LIMIT 50"
        ).fetchall()
    result = []
    for row in reversed(rows):
        result.append({
            "timestamp": row["timestamp"],
            "reading": json.loads(row["data_json"]),
        })
    return result
