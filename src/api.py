# src/api.py
import hmac
import html
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src import config, emailer
from src import routines as routine_store
from src import users as user_store
from src.auth import (
    DUMMY_PASSWORD_HASH,
    RateLimiter,
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
    verify_unsubscribe_signature,
)
from src.catalog import MUSCLE_GROUPS
from src.database import (
    delete_last_exercise_sets,
    delete_workout,
    end_active_workout,
    get_active_workout,
    get_distinct_logged_exercises,
    get_exercise_progression,
    get_last_exercise_performance,
    get_recent_workouts,
    get_weekly_muscle_volume,
    get_workout_details,
    get_workout_summary,
    init_db,
    log_sets_batch,
    start_new_workout,
)

FREE_WORKOUT_NAME = "Allenamento libero"
VERIFY_TOKEN_HOURS = 48
RESET_TOKEN_HOURS = 1


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    user_store.purge_expired()
    yield


app = FastAPI(title="Gym Tracker API", lifespan=lifespan)

# Percorso assoluto: non dipende dalla directory da cui viene avviato il processo
WEB_DIR = Path(__file__).resolve().parent / "web"


@app.middleware("http")
async def no_store_for_api(request: Request, call_next):
    """I dati personali non devono finire nelle cache del browser o dei proxy."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# --- Limiti anti abuso -------------------------------------------------------------
login_ip_limiter = RateLimiter(max_attempts=20, window_seconds=900)
login_email_limiter = RateLimiter(max_attempts=5, window_seconds=900)
register_limiter = RateLimiter(max_attempts=10, window_seconds=3600)
forgot_ip_limiter = RateLimiter(max_attempts=5, window_seconds=3600)
forgot_email_limiter = RateLimiter(max_attempts=3, window_seconds=3600)
resend_limiter = RateLimiter(max_attempts=3, window_seconds=3600)
password_check_limiter = RateLimiter(max_attempts=5, window_seconds=900)
ALL_LIMITERS = [
    login_ip_limiter, login_email_limiter, register_limiter, forgot_ip_limiter,
    forgot_email_limiter, resend_limiter, password_check_limiter,
]


def _too_many(wait_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Troppi tentativi. Riprova tra {wait_seconds} secondi.",
        headers={"Retry-After": str(wait_seconds)},
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# --- Autenticazione ----------------------------------------------------------------
def _bearer_token(authorization: str) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def get_current_user(authorization: str = Header(default="")) -> dict:
    token = _bearer_token(authorization)
    user = user_store.get_user_by_session(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Accesso richiesto")
    if config.REQUIRE_EMAIL_VERIFICATION and not user["email_verified"]:
        raise HTTPException(status_code=403, detail="Verifica prima il tuo indirizzo email")
    return user


# --- Modelli per i payload delle API -----------------------------------------------
class RegisterReq(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    marketing_opt_in: bool = False
    invite_code: str = Field(default="", max_length=100)


class LoginReq(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class EmailReq(BaseModel):
    email: str = Field(max_length=254)


class TokenReq(BaseModel):
    token: str = Field(max_length=200)


class ResetPasswordReq(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=256)


class ChangePasswordReq(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class PasswordReq(BaseModel):
    password: str = Field(max_length=256)


class ProfileUpdateReq(BaseModel):
    marketing_opt_in: bool | None = None


class ExerciseIn(BaseModel):
    name: str = Field(max_length=60)
    muscle_group: str | None = Field(default=None, max_length=30)
    note: str = Field(default="", max_length=120)


class RoutineIn(BaseModel):
    name: str = Field(max_length=50)
    notes: str = Field(default="", max_length=300)
    exercises: list[ExerciseIn] = Field(max_length=routine_store.MAX_EXERCISES)


class ImportCsvReq(BaseModel):
    csv: str = Field(max_length=routine_store.MAX_CSV_CHARS)


class StartWorkoutReq(BaseModel):
    routine_id: int | None = None


class SetItem(BaseModel):
    weight: float = Field(default=0.0, ge=0, le=1000)
    reps: int = Field(default=0, ge=0, le=1000)
    duration: int | None = Field(default=None, ge=1, le=86400)


class LogSetsReq(BaseModel):
    exercise: str = Field(min_length=1, max_length=100)
    sets: list[SetItem] = Field(min_length=1, max_length=50)


# --- Configurazione pubblica -------------------------------------------------------
@app.get("/api/public-config")
def api_public_config():
    """Cosa mostrare nella schermata di accesso (campo codice invito, ecc.)."""
    return {
        "invite_required": bool(config.REGISTRATION_INVITE_CODE),
        "verification_required": config.REQUIRE_EMAIL_VERIFICATION,
        "muscle_groups": MUSCLE_GROUPS,
    }


# --- Account -----------------------------------------------------------------------
@app.post("/api/auth/register")
def api_register(req: RegisterReq, request: Request, background: BackgroundTasks):
    ip = _client_ip(request)
    wait = register_limiter.blocked(ip)
    if wait:
        raise _too_many(wait)
    register_limiter.add(ip)  # conta ogni tentativo, anche quelli con codice invito errato

    if config.REGISTRATION_INVITE_CODE and not hmac.compare_digest(
        req.invite_code.strip().encode("utf-8"), config.REGISTRATION_INVITE_CODE.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Codice di invito non valido")

    email = normalize_email(req.email)
    if not email:
        raise HTTPException(status_code=422, detail="Indirizzo email non valido")
    error = validate_password(req.password, email)
    if error:
        raise HTTPException(status_code=422, detail=error)

    try:
        user_id = user_store.create_user(email, hash_password(req.password), req.marketing_opt_in)
    except user_store.EmailTaken:
        raise HTTPException(status_code=409, detail="Questa email è già registrata")

    token = user_store.create_email_token(user_id, "verify", VERIFY_TOKEN_HOURS)
    background.add_task(emailer.send_verification_email, email, token)

    if config.REQUIRE_EMAIL_VERIFICATION:
        return {"verification_required": True}
    return {
        "token": user_store.create_session(user_id),
        "user": user_store.public_user(user_store.get_user(user_id)),
    }


@app.post("/api/auth/login")
def api_login(req: LoginReq, request: Request):
    ip = _client_ip(request)
    email = normalize_email(req.email) or ""
    for limiter, key in ((login_ip_limiter, ip), (login_email_limiter, email)):
        wait = limiter.blocked(key)
        if wait:
            raise _too_many(wait)

    user = user_store.get_user_by_email(email) if email else None
    # Si verifica sempre un hash (anche per email sconosciute): il tempo di risposta non rivela chi è registrato
    valid = verify_password(req.password, user["password_hash"] if user else DUMMY_PASSWORD_HASH)
    if not user or not valid:
        login_ip_limiter.add(ip)
        if email:
            login_email_limiter.add(email)
        raise HTTPException(status_code=401, detail="Email o password non corretti")

    login_email_limiter.clear(email)
    if config.REQUIRE_EMAIL_VERIFICATION and not user["email_verified"]:
        raise HTTPException(status_code=403, detail="Verifica prima il tuo indirizzo email: controlla la posta")
    return {"token": user_store.create_session(user["id"]), "user": user_store.public_user(user)}


@app.post("/api/auth/logout")
def api_logout(authorization: str = Header(default=""), user: dict = Depends(get_current_user)):
    user_store.delete_session(_bearer_token(authorization))
    return {"status": "ok"}


@app.get("/api/auth/me")
def api_me(user: dict = Depends(get_current_user)):
    return user_store.public_user(user)


@app.patch("/api/auth/me")
def api_update_me(req: ProfileUpdateReq, user: dict = Depends(get_current_user)):
    if req.marketing_opt_in is not None:
        user_store.set_marketing_opt_in(user["id"], req.marketing_opt_in)
    return user_store.public_user(user_store.get_user(user["id"]))


@app.post("/api/auth/verify-email")
def api_verify_email(req: TokenReq):
    user_id = user_store.consume_email_token(req.token, "verify")
    if user_id is None:
        raise HTTPException(status_code=400, detail="Link non valido o scaduto")
    user_store.mark_email_verified(user_id)
    return {"status": "verified"}


@app.post("/api/auth/resend-verification")
def api_resend_verification(background: BackgroundTasks, user: dict = Depends(get_current_user)):
    if user["email_verified"]:
        return {"status": "already_verified"}
    key = f"user:{user['id']}"
    wait = resend_limiter.blocked(key)
    if wait:
        raise _too_many(wait)
    resend_limiter.add(key)
    token = user_store.create_email_token(user["id"], "verify", VERIFY_TOKEN_HOURS)
    background.add_task(emailer.send_verification_email, user["email"], token)
    return {"status": "sent"}


@app.post("/api/auth/forgot-password")
def api_forgot_password(req: EmailReq, request: Request, background: BackgroundTasks):
    """Risponde sempre allo stesso modo: non rivela se l'email è registrata."""
    ip = _client_ip(request)
    email = normalize_email(req.email)
    wait = max(forgot_ip_limiter.blocked(ip), forgot_email_limiter.blocked(email) if email else 0)
    if wait:
        raise _too_many(wait)
    forgot_ip_limiter.add(ip)
    if email:
        forgot_email_limiter.add(email)
        user = user_store.get_user_by_email(email)
        if user:
            token = user_store.create_email_token(user["id"], "reset", RESET_TOKEN_HOURS)
            background.add_task(emailer.send_password_reset_email, email, token)
    return {"status": "ok"}


@app.post("/api/auth/reset-password")
def api_reset_password(req: ResetPasswordReq):
    # Si controlla la password PRIMA di consumare il token, che altrimenti andrebbe sprecato
    error = validate_password(req.password)
    if error:
        raise HTTPException(status_code=422, detail=error)
    user_id = user_store.consume_email_token(req.token, "reset")
    if user_id is None:
        raise HTTPException(status_code=400, detail="Link non valido o scaduto")
    user_store.set_password_hash(user_id, hash_password(req.password))
    user_store.mark_email_verified(user_id)  # ha dimostrato di controllare l'indirizzo
    user_store.delete_user_sessions(user_id)  # chiude tutte le sessioni aperte altrove
    return {"status": "ok"}


@app.post("/api/auth/change-password")
def api_change_password(
    req: ChangePasswordReq,
    authorization: str = Header(default=""),
    user: dict = Depends(get_current_user),
):
    key = f"user:{user['id']}"
    wait = password_check_limiter.blocked(key)
    if wait:
        raise _too_many(wait)
    if not verify_password(req.current_password, user["password_hash"]):
        password_check_limiter.add(key)
        raise HTTPException(status_code=403, detail="La password attuale non è corretta")
    error = validate_password(req.new_password, user["email"])
    if error:
        raise HTTPException(status_code=422, detail=error)
    user_store.set_password_hash(user["id"], hash_password(req.new_password))
    user_store.delete_user_sessions(user["id"], keep_raw_token=_bearer_token(authorization))
    return {"status": "ok"}


@app.post("/api/auth/delete-account")
def api_delete_account(req: PasswordReq, user: dict = Depends(get_current_user)):
    """Elimina definitivamente l'account e tutti i dati collegati."""
    key = f"user:{user['id']}"
    wait = password_check_limiter.blocked(key)
    if wait:
        raise _too_many(wait)
    if not verify_password(req.password, user["password_hash"]):
        password_check_limiter.add(key)
        raise HTTPException(status_code=403, detail="Password non corretta")
    user_store.delete_user(user["id"])
    return {"status": "deleted"}


@app.get("/api/auth/export")
def api_export(user: dict = Depends(get_current_user)):
    return user_store.export_user_data(user["id"])


# --- Disiscrizione dalle email di novità (pubblica, senza login) -------------------
_UNSUBSCRIBE_PAGE = """<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gym Tracker - Novità via email</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#000;color:#fff;margin:0;
       min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}}
  main{{max-width:380px;text-align:center}}
  button{{background:#0A84FF;color:#fff;border:0;border-radius:14px;padding:14px 22px;font-size:16px;font-weight:700}}
  p{{color:#a1a1aa;line-height:1.5}}
</style></head><body><main>
<h1>{title}</h1><p id="msg">{text}</p>{button}
</main>{script}</body></html>"""


def _unsubscribe_page(title: str, text: str, user_id: int | None = None, signature: str = "") -> str:
    button, script = "", ""
    if user_id is not None:
        button = '<button id="go">Annulla l\'iscrizione</button>'
        url = json.dumps(f"/unsubscribe?u={int(user_id)}&t={signature}")
        script = (
            "<script>document.getElementById('go').onclick=function(){"
            f"fetch({url},{{method:'POST'}}).then(function(r){{"
            "document.getElementById('msg').textContent=r.ok?"
            "'Fatto: non riceverai più email di novità.':'Qualcosa è andato storto, riprova più tardi.';"
            "document.getElementById('go').style.display='none';});};</script>"
        )
    return _UNSUBSCRIBE_PAGE.format(title=html.escape(title), text=html.escape(text), button=button, script=script)


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(u: int = Query(default=0), t: str = Query(default="")):
    # La GET non modifica nulla: gli antivirus e i client di posta aprono i link in anteprima.
    if not verify_unsubscribe_signature(u, t):
        return HTMLResponse(_unsubscribe_page("Link non valido", "Questo link di disiscrizione non è valido."), 400)
    return HTMLResponse(_unsubscribe_page(
        "Email di novità",
        "Vuoi smettere di ricevere le email di novità su Gym Tracker? Le email di servizio "
        "(verifica account, reimpostazione password) continueranno ad arrivare solo quando le richiedi.",
        user_id=u, signature=t,
    ))


@app.post("/unsubscribe")
def unsubscribe(u: int = Query(default=0), t: str = Query(default="")):
    """Usata dal pulsante della pagina e dal "one-click unsubscribe" dei client di posta (RFC 8058)."""
    if not verify_unsubscribe_signature(u, t):
        raise HTTPException(status_code=400, detail="Link non valido")
    user_store.set_marketing_opt_in(u, False)
    return {"status": "unsubscribed"}


# --- Schede di allenamento ---------------------------------------------------------
def _routine_error(e: routine_store.RoutineError) -> HTTPException:
    status = 409 if isinstance(e, routine_store.DuplicateRoutine) else 422
    return HTTPException(status_code=status, detail=str(e))


@app.get("/api/routines")
def api_list_routines(user: dict = Depends(get_current_user)):
    return routine_store.list_routines(user["id"])


@app.post("/api/routines")
def api_create_routine(req: RoutineIn, user: dict = Depends(get_current_user)):
    try:
        return routine_store.create_routine(user["id"], req.name, req.notes, [e.model_dump() for e in req.exercises])
    except routine_store.RoutineError as e:
        raise _routine_error(e)


@app.post("/api/routines/import")
def api_import_routines(req: ImportCsvReq, user: dict = Depends(get_current_user)):
    try:
        return routine_store.import_routines_csv(user["id"], req.csv)
    except routine_store.RoutineError as e:
        raise _routine_error(e)


@app.post("/api/routines/template")
def api_add_template_routines(user: dict = Depends(get_current_user)):
    try:
        return {"created": routine_store.seed_template(user["id"])}
    except routine_store.RoutineError as e:
        raise _routine_error(e)


@app.put("/api/routines/{routine_id}")
def api_update_routine(routine_id: int, req: RoutineIn, user: dict = Depends(get_current_user)):
    try:
        routine = routine_store.update_routine(
            user["id"], routine_id, req.name, req.notes, [e.model_dump() for e in req.exercises]
        )
    except routine_store.RoutineError as e:
        raise _routine_error(e)
    if routine is None:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    return routine


@app.delete("/api/routines/{routine_id}")
def api_delete_routine(routine_id: int, user: dict = Depends(get_current_user)):
    if not routine_store.delete_routine(user["id"], routine_id):
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    return {"status": "deleted"}


# --- Allenamenti -------------------------------------------------------------------
@app.get("/api/workout/active")
def api_get_active(user: dict = Depends(get_current_user)):
    active = get_active_workout(user["id"])
    if not active:
        return {"active": False}
    w_id, split_name, start_time, routine_id = active
    _, sets = get_workout_details(user["id"], w_id)
    return {
        "active": True,
        "id": w_id,
        "split": split_name,
        "start_time": start_time,
        "routine": routine_store.get_routine(user["id"], routine_id) if routine_id else None,
        "sets": [{"exercise": s[0], "order": s[1], "weight": s[2], "reps": s[3], "duration": s[4]} for s in sets]
    }


@app.post("/api/workout/start")
def api_start_workout(req: StartWorkoutReq, user: dict = Depends(get_current_user)):
    if get_active_workout(user["id"]):
        raise HTTPException(status_code=400, detail="Sessione già attiva")
    name = FREE_WORKOUT_NAME
    if req.routine_id is not None:
        routine = routine_store.get_routine(user["id"], req.routine_id)
        if routine is None:
            raise HTTPException(status_code=404, detail="Scheda non trovata")
        name = routine["name"]
    w_id = start_new_workout(user["id"], name, req.routine_id)
    return {"id": w_id, "split": name}


@app.post("/api/workout/sets")
def api_log_sets(req: LogSetsReq, user: dict = Depends(get_current_user)):
    active = get_active_workout(user["id"])
    if not active:
        raise HTTPException(status_code=400, detail="Nessuna sessione attiva")
    entries = [s.model_dump() for s in req.sets]
    log_sets_batch(user["id"], active[0], req.exercise, entries)
    return {"status": "ok"}


@app.delete("/api/workout/sets/last")
def api_undo_last(user: dict = Depends(get_current_user)):
    active = get_active_workout(user["id"])
    if not active:
        raise HTTPException(status_code=400, detail="Nessuna sessione attiva")
    res = delete_last_exercise_sets(user["id"], active[0])
    if not res:
        raise HTTPException(status_code=404, detail="Nessuna serie da annullare")
    return {"deleted_exercise": res[0], "count": res[1]}


@app.post("/api/workout/end")
def api_end_workout(user: dict = Depends(get_current_user)):
    active = get_active_workout(user["id"])
    if not active:
        raise HTTPException(status_code=400, detail="Nessuna sessione attiva")
    summary = get_workout_summary(user["id"], active[0])
    end_active_workout(user["id"], active[0])
    return {
        "split": active[1],
        "summary": [{"exercise": r[0], "sets": r[1], "volume": r[2], "max_weight": r[3]} for r in summary]
    }


@app.get("/api/workouts/history")
def api_history(user: dict = Depends(get_current_user)):
    rows = get_recent_workouts(user["id"], limit=10)
    res = []
    for r in rows:
        _, sets = get_workout_details(user["id"], r[0])
        res.append({
            "id": r[0],
            "date": r[1][:10],
            "split": r[2],
            "exercises_count": r[3],
            "sets_count": r[4],
            "volume": r[5],
            "sets": [{"exercise": s[0], "weight": s[2], "reps": s[3], "duration": s[4]} for s in sets]
        })
    return res


@app.delete("/api/workouts/{workout_id}")
def api_delete_workout(workout_id: int, user: dict = Depends(get_current_user)):
    if not delete_workout(user["id"], workout_id):
        raise HTTPException(status_code=404, detail="Workout non trovato")
    return {"status": "deleted"}


# 1. ROTTE STATICHE: devono precedere tassativamente quella con {exercise}
@app.get("/api/analytics/exercises")
def api_distinct_exercises(user: dict = Depends(get_current_user)):
    return get_distinct_logged_exercises(user["id"])


# Volume settimanale per distretto muscolare
@app.get("/api/analytics/weekly-volume")
def api_weekly_volume(user: dict = Depends(get_current_user)):
    return get_weekly_muscle_volume(user["id"])


# Dati completi per il grafico (1RM, Volume, Max Weight)
@app.get("/api/analytics/{exercise}")
def api_progression(exercise: str, user: dict = Depends(get_current_user)):
    data = get_exercise_progression(user["id"], exercise)
    return [{
        "date": d[0][:10],
        "1rm": round(d[1], 1) if d[1] is not None else 0,
        "volume": round(d[2], 1) if d[2] is not None else 0,
        "max_weight": round(d[3], 1) if d[3] is not None else 0
    } for d in data]


@app.get("/api/exercises/{exercise}/last")
def api_last_exercise_performance(exercise: str, user: dict = Depends(get_current_user)):
    data = get_last_exercise_performance(user["id"], exercise)
    return data or {"found": False}


# --- File statici e pagine pubbliche ----------------------------------------------
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def serve_pwa():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/privacy")
def serve_privacy():
    return FileResponse(WEB_DIR / "privacy.html")


@app.get("/sw.js")
def serve_service_worker():
    # Servito dalla radice: uno Service Worker può controllare solo le pagine
    # dentro il proprio percorso, e da /static/ non avrebbe mai coperto "/".
    return FileResponse(
        WEB_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"}
    )
