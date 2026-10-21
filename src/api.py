# src/api.py
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.config import API_KEY
from src.catalog import WORKOUT_ROUTINES
from src.database import (
    get_active_workout,
    start_new_workout,
    end_active_workout,
    log_sets_batch,
    get_workout_summary,
    get_recent_workouts,
    get_workout_details,
    delete_last_exercise_sets,
    delete_workout,
    get_exercise_progression
)

app = FastAPI(title="Gym Tracker API")

# Protezione tramite PIN/API Key nell'header
def verify_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="PIN/API Key non valida")

class StartWorkoutReq(BaseModel):
    split_name: str

class LogSetsReq(BaseModel):
    exercise: str
    sets: list[tuple[float, int]]  # Lista di [peso, ripetizioni]

@app.get("/api/catalog", dependencies=[Depends(verify_key)])
def api_get_catalog():
    return WORKOUT_ROUTINES

@app.get("/api/workout/active", dependencies=[Depends(verify_key)])
def api_get_active():
    active = get_active_workout()
    if not active:
        return {"active": False}
    w_id, split_name, start_time = active
    _, sets = get_workout_details(w_id)
    return {
        "active": True,
        "id": w_id,
        "split": split_name,
        "start_time": start_time,
        "routine": WORKOUT_ROUTINES.get(split_name, {}),
        "sets": [{"exercise": s[0], "order": s[1], "weight": s[2], "reps": s[3]} for s in sets]
    }

@app.post("/api/workout/start", dependencies=[Depends(verify_key)])
def api_start_workout(req: StartWorkoutReq):
    if get_active_workout():
        raise HTTPException(status_code=400, detail="Sessione già attiva")
    w_id = start_new_workout(req.split_name)
    return {"id": w_id, "split": req.split_name}

@app.post("/api/workout/sets", dependencies=[Depends(verify_key)])
def api_log_sets(req: LogSetsReq):
    active = get_active_workout()
    if not active:
        raise HTTPException(status_code=400, detail="Nessuna sessione attiva")
    log_sets_batch(active[0], req.exercise, req.sets)
    return {"status": "ok"}

@app.delete("/api/workout/sets/last", dependencies=[Depends(verify_key)])
def api_undo_last():
    active = get_active_workout()
    if not active:
        raise HTTPException(status_code=400, detail="Nessuna sessione attiva")
    res = delete_last_exercise_sets(active[0])
    if not res:
        raise HTTPException(status_code=404, detail="Nessuna serie da annullare")
    return {"deleted_exercise": res[0], "count": res[1]}

@app.post("/api/workout/end", dependencies=[Depends(verify_key)])
def api_end_workout():
    active = get_active_workout()
    if not active:
        raise HTTPException(status_code=400, detail="Nessuna sessione attiva")
    summary = get_workout_summary(active[0])
    end_active_workout(active[0])
    return {
        "split": active[1],
        "summary": [{"exercise": r[0], "sets": r[1], "volume": r[2], "max_weight": r[3]} for r in summary]
    }

@app.get("/api/workouts/history", dependencies=[Depends(verify_key)])
def api_history():
    rows = get_recent_workouts(limit=10)
    res = []
    for r in rows:
        _, sets = get_workout_details(r[0])
        res.append({
            "id": r[0],
            "date": r[1][:10],
            "split": r[2],
            "exercises_count": r[3],
            "sets_count": r[4],
            "volume": r[5],
            "sets": [{"exercise": s[0], "weight": s[2], "reps": s[3]} for s in sets]
        })
    return res

@app.delete("/api/workouts/{workout_id}", dependencies=[Depends(verify_key)])
def api_delete_workout(workout_id: int):
    if not delete_workout(workout_id):
        raise HTTPException(status_code=404, detail="Workout non trovato")
    return {"status": "deleted"}

@app.get("/api/analytics/{exercise}", dependencies=[Depends(verify_key)])
def api_progression(exercise: str):
    data = get_exercise_progression(exercise)
    return [{"date": d[0][:10], "1rm": round(d[1], 1)} for d in data]

# Servire i file statici della PWA
app.mount("/static", StaticFiles(directory="src/web"), name="static")

@app.get("/")
def serve_pwa():
    return FileResponse("src/web/index.html")