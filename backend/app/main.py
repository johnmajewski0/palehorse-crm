"""Pale Horse CRM MVP API. Local development starter; not production hardened."""
import os
import secrets
import urllib.parse
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta, timezone, time, date
from typing import Literal
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Text, Integer, Time, Boolean, select, text, or_
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.exc import IntegrityError
from pwdlib import PasswordHash

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./crm.db")
SECRET_KEY = os.environ.get("SESSION_SECRET", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError("SESSION_SECRET must be set to a random string of at least 32 characters")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)
passwords = PasswordHash.recommended()

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    role = Column(String(20), nullable=False)
    password_hash = Column(String(255), nullable=False)

class Lead(Base):
    __tablename__ = "leads"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False, default="")
    phone = Column(String(50), nullable=False, default="")
    interest = Column(String(255), nullable=False, default="Personal training")
    stage = Column(String(30), nullable=False, default="new")
    assigned_trainer_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class InterestType(Base):
    """Gym-wide prospect interest catalog, with a stable, case-insensitive key."""
    __tablename__ = "crm_interest_types"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(80), nullable=False)
    name_key = Column(String(80), nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

DEFAULT_INTEREST_TYPES = (
    "Personal training", "Powerlifting coaching", "Strength & conditioning",
    "General fitness", "Assessment / consultation", "Nutrition coaching",
    "Group training", "Online coaching",
)

def interest_key(label: str) -> str:
    return " ".join(label.split()).casefold()

class Activity(Base):
    __tablename__ = "activities"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class AvailabilityRule(Base):
    __tablename__ = "trainer_availability_rules"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)  # Monday=0
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    timezone = Column(String(64), nullable=False, default="America/New_York")
    active = Column(Boolean, nullable=False, default=True)

class AvailabilityException(Base):
    __tablename__ = "trainer_availability_exceptions"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    kind = Column(String(16), nullable=False)  # unavailable / available
    reason = Column(String(255), nullable=False, default="")
    active = Column(Boolean, nullable=False, default=True)

class Assignment(Base):
    __tablename__ = "trainer_assignments"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class AssignmentEvent(Base):
    __tablename__ = "trainer_assignment_events"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    assignment_id = Column(String, ForeignKey("trainer_assignments.id"), nullable=False, index=True)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String(40), nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class Notification(Base):
    __tablename__ = "crm_notifications"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    recipient_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    assignment_id = Column(String, ForeignKey("trainer_assignments.id"), nullable=False)
    message = Column(Text, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class CalendarSubscription(Base):
    __tablename__ = "trainer_calendar_subscriptions"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class ClientOnboarding(Base):
    __tablename__ = "crm_client_onboarding"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="pending")
    reviewed_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class SessionSeries(Base):
    __tablename__ = "crm_session_series"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)
    local_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    interval_weeks = Column(Integer, nullable=False, default=1)
    start_date = Column(DateTime(timezone=False), nullable=False)
    until_date = Column(DateTime(timezone=False), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    materialized_through = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class ClientSession(Base):
    __tablename__ = "crm_client_sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    series_id = Column(String, ForeignKey("crm_session_series.id"), nullable=True, index=True)
    occurrence_date = Column(DateTime(timezone=False), nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(24), nullable=False, default="confirmed")
    session_type = Column(String(80), nullable=False, default="Personal training")
    note = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class SessionAudit(Base):
    __tablename__ = "crm_session_audit"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String, ForeignKey("crm_client_sessions.id"), nullable=False, index=True)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String(32), nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# Owner-only business follow-ups. Crucible Wellness is a separate business, not a gym client category.
class OwnerTask(Base):
    __tablename__ = "crm_owner_tasks"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    business = Column(String(30), nullable=False)
    kind = Column(String(30), nullable=False, default="callback")
    title = Column(String(180), nullable=False)
    contact_name = Column(String(150), nullable=False, default="")
    contact_email = Column(String(255), nullable=False, default="")
    contact_phone = Column(String(50), nullable=False, default="")
    due_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=False, default="")
    status = Column(String(16), nullable=False, default="open")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class OwnerGmailConnection(Base):
    __tablename__ = "crm_owner_gmail_connections"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    account_email = Column(String(255), nullable=False)
    encrypted_refresh_token = Column(Text, nullable=False)
    connected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class OwnerTaskEvent(Base):
    __tablename__ = "crm_owner_task_events"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String, ForeignKey("crm_owner_tasks.id"), nullable=False)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String(24), nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# v0.2.8: one class with multiple coaches and a changeable current roster.
class GymEvent(Base):
    __tablename__ = "crm_gym_events"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(150), nullable=False)
    kind = Column(String(16), nullable=False)  # class or block
    created_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    active = Column(Boolean, nullable=False, default=True)

class GymEventPattern(Base):
    __tablename__ = "crm_gym_event_patterns"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    event_id = Column(String, ForeignKey("crm_gym_events.id"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    materialized_through = Column(DateTime(timezone=False), nullable=False)
    end_date = Column(DateTime(timezone=False), nullable=True)

class GymEventCoach(Base):
    __tablename__ = "crm_gym_event_coaches"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    event_id = Column(String, ForeignKey("crm_gym_events.id"), nullable=False, index=True)
    coach_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)

class GymEventMember(Base):
    __tablename__ = "crm_gym_event_members"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    event_id = Column(String, ForeignKey("crm_gym_events.id"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    left_at = Column(DateTime(timezone=True), nullable=True)

class GymEventOccurrence(Base):
    __tablename__ = "crm_gym_event_occurrences"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    event_id = Column(String, ForeignKey("crm_gym_events.id"), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, default="confirmed")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class GymEventLog(Base):
    __tablename__ = "crm_gym_event_log"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    event_id = Column(String, ForeignKey("crm_gym_events.id"), nullable=False, index=True)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String(40), nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

Base.metadata.create_all(engine)
# Safe additive migration for v0.2.7; no existing tasks are deleted.
with engine.begin() as conn:
    if engine.dialect.name == "postgresql":
        conn.execute(text("ALTER TABLE crm_owner_tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"))
        conn.execute(text("UPDATE crm_owner_tasks SET completed_at = updated_at WHERE status = 'done' AND completed_at IS NULL"))
    elif engine.dialect.name == "sqlite":
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(crm_owner_tasks)")}
        if "completed_at" not in columns:
            conn.exec_driver_sql("ALTER TABLE crm_owner_tasks ADD COLUMN completed_at DATETIME")
        conn.execute(text("UPDATE crm_owner_tasks SET completed_at = updated_at WHERE status = 'done' AND completed_at IS NULL"))

# PostgreSQL exclusion constraint is the final arbiter of concurrent confirmed bookings.
# It also covers overlapping bookings for the same client on different trainers.
if engine.dialect.name == "postgresql":
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        conn.execute(text("""DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='crm_trainer_session_overlap') THEN
            ALTER TABLE crm_client_sessions ADD CONSTRAINT crm_trainer_session_overlap
            EXCLUDE USING gist (trainer_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
            WHERE (status='confirmed');
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='crm_client_session_overlap') THEN
            ALTER TABLE crm_client_sessions ADD CONSTRAINT crm_client_session_overlap
            EXCLUDE USING gist (lead_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
            WHERE (status='confirmed');
          END IF;
        END $$;"""))
        conn.execute(text("""DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='no_trainer_confirmed_overlap') THEN
            ALTER TABLE trainer_assignments ADD CONSTRAINT no_trainer_confirmed_overlap
            EXCLUDE USING gist (trainer_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
            WHERE (status='confirmed');
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='no_client_confirmed_overlap') THEN
            ALTER TABLE trainer_assignments ADD CONSTRAINT no_client_confirmed_overlap
            EXCLUDE USING gist (lead_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
            WHERE (status='confirmed');
          END IF;
        END $$;"""))
with SessionLocal() as db:
    if not db.scalar(select(User.id).limit(1)):
        email = os.environ.get("BOOTSTRAP_OWNER_EMAIL", "").strip().lower()
        password = os.environ.get("BOOTSTRAP_OWNER_PASSWORD", "")
        if not email or len(password) < 12:
            raise RuntimeError("Set BOOTSTRAP_OWNER_EMAIL and BOOTSTRAP_OWNER_PASSWORD (12+ characters) for first launch")
        db.add(User(email=email, name="Gym Owner", role="owner", password_hash=passwords.hash(password)))
        db.commit()

# Add options without rewriting or deleting any existing lead interest values.
# Legacy free-text interests are included so they remain selectable and reportable.
with SessionLocal() as db:
    labels = list(DEFAULT_INTEREST_TYPES)
    labels += [v for v in db.scalars(select(Lead.interest).distinct()).all() if v]
    for raw in labels:
        name = " ".join(raw.strip().split())
        key = interest_key(name)
        if not name or len(name) > 80 or key in ("other", "select an interest"):
            continue
        if engine.dialect.name == "postgresql":
            db.execute(text("INSERT INTO crm_interest_types (id,name,name_key,active,created_at) "
                            "VALUES (:id,:name,:key,true,:now) ON CONFLICT (name_key) DO NOTHING"),
                       {"id": str(uuid4()), "name": name, "key": key, "now": datetime.now(timezone.utc)})
        elif not db.scalar(select(InterestType.id).where(InterestType.name_key == key)):
            db.add(InterestType(name=name, name_key=key))
    db.commit()

app = FastAPI(title="Pale Horse CRM", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")], allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "X-CSRF-Token"])

def db_session():
    with SessionLocal() as db: yield db

class LoginIn(BaseModel):
    email: str
    password: str

class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=50)
    interest: str = Field(default="Personal training", max_length=255)

class LeadUpdate(BaseModel):
    interest: str | None = Field(default=None, max_length=80)
    stage: Literal["new", "contacted", "consultation", "trial", "converted", "follow_up", "lost"] | None = None
    assigned_trainer_id: str | None = None

class InterestTypeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)

class ActivityCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

class TrainerCreate(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=12)


def current_user(request: Request, db: Session = Depends(db_session)):
    try:
        token = request.cookies.get("phcrm_session", "")
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user = db.get(User, data["sub"])
    except (jwt.InvalidTokenError, KeyError):
        user = None
    if user is None:
        raise HTTPException(401, "Sign in required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.cookies.get("phcrm_csrf") != request.headers.get("X-CSRF-Token") or not request.headers.get("X-CSRF-Token"):
            raise HTTPException(403, "CSRF verification failed")
    return user


def owner_only(user: User):
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Owner access required")


def serialize_lead(lead, db):
    trainer = db.get(User, lead.assigned_trainer_id) if lead.assigned_trainer_id else None
    return {"id": lead.id, "name": lead.name, "email": lead.email, "phone": lead.phone, "interest": lead.interest, "stage": lead.stage, "assigned_trainer_id": lead.assigned_trainer_id, "trainer_name": trainer.name if trainer else None, "created_at": lead.created_at.isoformat()}

@app.get("/api/health")
def health(): return {"status":"ok"}

@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(db_session)):
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not passwords.verify(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = jwt.encode({"sub": user.id, "exp": datetime.now(timezone.utc) + timedelta(hours=8)}, SECRET_KEY, algorithm="HS256")
    csrf = uuid4().hex
    secure = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie("phcrm_session", token, httponly=True, secure=secure, samesite="lax", max_age=28800)
    response.set_cookie("phcrm_csrf", csrf, httponly=False, secure=secure, samesite="lax", max_age=28800)
    return {"id":user.id,"name":user.name,"email":user.email,"role":user.role,"csrf":csrf}

@app.post("/api/auth/logout")
def logout(response: Response, user: User = Depends(current_user)):
    response.delete_cookie("phcrm_session")
    response.delete_cookie("phcrm_csrf")
    return {"ok":True}

@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id":user.id,"name":user.name,"email":user.email,"role":user.role}

@app.get("/api/trainers")
def trainers(user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    return [{"id":u.id,"name":u.name,"email":u.email} for u in db.scalars(select(User).where(User.role == "trainer").order_by(User.name)).all()]

@app.post("/api/trainers")
def add_trainer(payload: TrainerCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    email = payload.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Account exists")
    u = User(email=email, name=payload.name.strip(), role="trainer", password_hash=passwords.hash(payload.password))
    db.add(u); db.commit()
    return {"id":u.id,"name":u.name,"email":u.email}

def canonical_interest(db: Session, raw: str) -> str:
    label = " ".join(raw.strip().split())
    item = db.scalar(select(InterestType).where(InterestType.name_key == interest_key(label), InterestType.active == True))
    if not item:
        raise HTTPException(422, "Select a listed interest or add a new type using Other")
    return item.name

@app.get("/api/interest-types")
def list_interest_types(user: User = Depends(current_user), db: Session = Depends(db_session)):
    return [x.name for x in db.scalars(select(InterestType).where(InterestType.active == True).order_by(InterestType.name)).all()]

@app.post("/api/interest-types", status_code=201)
def create_interest_type(payload: InterestTypeCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    name = " ".join(payload.name.strip().split())
    key = interest_key(name)
    if len(name) < 2 or key in ("other", "select an interest"):
        raise HTTPException(422, "Enter a meaningful interest type")
    existing = db.scalar(select(InterestType).where(InterestType.name_key == key))
    if existing:
        if not existing.active:
            existing.active = True
            db.commit()
        return {"name": existing.name, "created": False}
    obj = InterestType(name=name, name_key=key)
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        obj = db.scalar(select(InterestType).where(InterestType.name_key == key))
        if not obj:
            raise HTTPException(409, "Could not save interest type; retry")
        return {"name": obj.name, "created": False}
    return {"name": name, "created": True}

@app.get("/api/leads")
def leads(user: User = Depends(current_user), db: Session = Depends(db_session)):
    stmt = select(Lead).order_by(Lead.created_at.desc())
    if user.role == "trainer": stmt = stmt.where(Lead.assigned_trainer_id == user.id)
    return [serialize_lead(l, db) for l in db.scalars(stmt).all()]

@app.post("/api/leads")
def add_lead(payload: LeadCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    data = payload.model_dump()
    data["interest"] = canonical_interest(db, data["interest"])
    lead = Lead(**data); db.add(lead); db.commit(); db.refresh(lead)
    return serialize_lead(lead, db)

@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: str, payload: LeadUpdate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    lead = db.get(Lead, lead_id)
    if not lead: raise HTTPException(404, "Lead not found")
    if user.role == "trainer" and lead.assigned_trainer_id != user.id: raise HTTPException(403)
    fields = payload.model_fields_set
    if "assigned_trainer_id" in fields:
        raise HTTPException(409, "Use trainer scheduling to assign or return clients with an audit trail")
    if "stage" in fields and payload.stage:
        lead.stage = payload.stage
    if "interest" in fields and payload.interest is not None:
        owner_only(user)
        lead.interest = canonical_interest(db, payload.interest)
    db.commit(); db.refresh(lead)
    return serialize_lead(lead, db)

@app.get("/api/leads/{lead_id}/activities")
def activities(lead_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)):
    lead = db.get(Lead, lead_id)
    if not lead: raise HTTPException(404)
    if user.role == "trainer" and lead.assigned_trainer_id != user.id: raise HTTPException(403)
    rows = db.scalars(select(Activity).where(Activity.lead_id == lead_id).order_by(Activity.created_at.desc())).all()
    return [{"id":a.id,"message":a.message,"created_at":a.created_at.isoformat(),"actor_id":a.actor_id} for a in rows]

@app.post("/api/leads/{lead_id}/activities")
def add_activity(lead_id: str, payload: ActivityCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    lead = db.get(Lead, lead_id)
    if not lead: raise HTTPException(404)
    if user.role == "trainer" and lead.assigned_trainer_id != user.id: raise HTTPException(403)
    a = Activity(lead_id=lead_id, actor_id=user.id, message=payload.message.strip()); db.add(a); db.commit()
    return {"id":a.id}

@app.get("/api/integrations/gmail/status")
def gmail_status(user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    allowed = os.environ.get("GOOGLE_ALLOWED_EMAIL", "noah@palehorsebarbell.com").lower()
    connected = bool(db.get(OwnerGmailConnection, user.id)) if user.email.lower() == allowed else False
    return {"connected": connected, "account": allowed,
            "message": ("Google Workspace connected for Owner Operations." if connected else
                        "Google Workspace OAuth has not been connected. No Gmail data is accessed.")}


# ---- v0.2.0 trainer scheduling ----
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/New_York")

def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise HTTPException(422, "Times must include UTC offset")
    return dt.astimezone(timezone.utc)

def interval(start: datetime, end: datetime):
    start, end = utc(start), utc(end)
    if start >= end or end - start > timedelta(hours=12):
        raise HTTPException(422, "Invalid interval (maximum 12 hours)")
    return start, end

def iso(dt):
    return dt.isoformat() if dt else None

def trainer_self_or_owner(actor: User, trainer_id: str):
    if actor.role not in ("owner", "admin") and not (actor.role == "trainer" and actor.id == trainer_id):
        raise HTTPException(403, "Not authorized for this trainer")

def require_trainer(db, tid):
    trainer = db.get(User, tid)
    if not trainer or trainer.role != "trainer":
        raise HTTPException(404, "Trainer not found")
    return trainer

def available(db, tid, start, end):
    start, end = interval(start, end)
    # Explicit unavailable exceptions always veto the slot. Explicit available exceptions
    # can add hours outside the normal recurring schedule.
    exceptions = db.scalars(select(AvailabilityException).where(
        AvailabilityException.trainer_id == tid, AvailabilityException.active == True,
        AvailabilityException.starts_at < end, AvailabilityException.ends_at > start)).all()
    if any(x.kind == "unavailable" for x in exceptions): return False
    if any(x.kind == "available" and utc(x.starts_at) <= start and utc(x.ends_at) >= end for x in exceptions): return True
    rules = db.scalars(select(AvailabilityRule).where(AvailabilityRule.trainer_id == tid, AvailabilityRule.active == True)).all()
    # Test every local day crossed by the requested interval, including DST boundaries.
    local_start, local_end = start.astimezone(LOCAL_TZ), end.astimezone(LOCAL_TZ)
    day = local_start.date()
    while day <= local_end.date():
        day_start = datetime.combine(day, time.min, LOCAL_TZ).astimezone(timezone.utc)
        day_end = datetime.combine(day + timedelta(days=1), time.min, LOCAL_TZ).astimezone(timezone.utc)
        piece_start, piece_end = max(start, day_start), min(end, day_end)
        if piece_start < piece_end:
            matching = [r for r in rules if r.weekday == day.weekday() and
                        datetime.combine(day, r.start_time, LOCAL_TZ).astimezone(timezone.utc) <= piece_start and
                        datetime.combine(day, r.end_time, LOCAL_TZ).astimezone(timezone.utc) >= piece_end]
            if not matching: return False
        day += timedelta(days=1)
    return True

def gym_busy(db, trainer_id, start, end, exclude_occurrence_id=None):
    stmt = (select(GymEventOccurrence.id).join(GymEventCoach, GymEventCoach.event_id == GymEventOccurrence.event_id)
            .where(GymEventCoach.coach_id == trainer_id, GymEventCoach.active == True,
                   GymEventOccurrence.status == "confirmed", GymEventOccurrence.starts_at < end,
                   GymEventOccurrence.ends_at > start))
    if exclude_occurrence_id:
        stmt = stmt.where(GymEventOccurrence.id != exclude_occurrence_id)
    return db.scalar(stmt) is not None

def conflicts(db, trainer_id, lead_id, start, end, exclude_id=None):
    if gym_busy(db, trainer_id, start, end): return True
    query = select(Assignment).where(Assignment.status == "confirmed", Assignment.starts_at < end,
                                      Assignment.ends_at > start,
                                      or_(Assignment.trainer_id == trainer_id, Assignment.lead_id == lead_id))
    if exclude_id: query = query.where(Assignment.id != exclude_id)
    if db.scalar(query) is not None: return True
    new=select(ClientSession.id).where(ClientSession.status=="confirmed",ClientSession.starts_at<end,
        ClientSession.ends_at>start,or_(ClientSession.trainer_id==trainer_id,ClientSession.lead_id==lead_id))
    return db.scalar(new) is not None

def event(db, a, actor, action, detail=""):
    db.add(AssignmentEvent(assignment_id=a.id, actor_id=actor.id, action=action, detail=detail))

def notify_owners(db, assignment, message):
    for u in db.scalars(select(User).where(User.role.in_(["owner", "admin"]))).all():
        db.add(Notification(recipient_id=u.id, assignment_id=assignment.id, message=message))

def serialize_assignment(a, db):
    lead, trainer = db.get(Lead, a.lead_id), db.get(User, a.trainer_id)
    return {"id":a.id,"lead_id":a.lead_id,"lead_name":lead.name if lead else "(unknown)",
            "trainer_id":a.trainer_id,"trainer_name":trainer.name if trainer else "(unknown)",
            "status":a.status,"starts_at":iso(a.starts_at),"ends_at":iso(a.ends_at),
            "note":a.note,"created_at":iso(a.created_at),"updated_at":iso(a.updated_at)}

class RuleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

class ExceptionIn(BaseModel):
    starts_at: datetime
    ends_at: datetime
    kind: Literal["available", "unavailable"]
    reason: str = Field(default="", max_length=255)

class AssignmentIn(BaseModel):
    lead_id: str
    trainer_id: str
    starts_at: datetime
    ends_at: datetime
    note: str = Field(default="", max_length=2000)

class ActionIn(BaseModel):
    action: Literal["accept", "decline", "propose", "return", "cancel", "approve_proposal"]
    note: str = Field(default="", max_length=2000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

@app.get("/api/scheduling/availability/{trainer_id}")
def list_availability(trainer_id: str, user: User=Depends(current_user), db: Session=Depends(db_session)):
    trainer_self_or_owner(user, trainer_id)
    require_trainer(db, trainer_id)
    rules = db.scalars(select(AvailabilityRule).where(AvailabilityRule.trainer_id==trainer_id, AvailabilityRule.active==True).order_by(AvailabilityRule.weekday,AvailabilityRule.start_time)).all()
    exceptions = db.scalars(select(AvailabilityException).where(AvailabilityException.trainer_id==trainer_id, AvailabilityException.active==True).order_by(AvailabilityException.starts_at)).all()
    return {"timezone":"America/New_York", "rules":[{"id":r.id,"weekday":r.weekday,"start_time":str(r.start_time),"end_time":str(r.end_time)} for r in rules],
            "exceptions":[{"id":e.id,"starts_at":iso(e.starts_at),"ends_at":iso(e.ends_at),"kind":e.kind,"reason":e.reason} for e in exceptions]}

@app.post("/api/scheduling/availability/{trainer_id}/rules")
def add_rule(trainer_id: str, payload: RuleIn, user: User=Depends(current_user), db: Session=Depends(db_session)):
    trainer_self_or_owner(user, trainer_id); require_trainer(db, trainer_id)
    if payload.start_time >= payload.end_time: raise HTTPException(422,"End must follow start")
    r=AvailabilityRule(trainer_id=trainer_id, **payload.model_dump()); db.add(r); db.commit()
    return {"id":r.id}

@app.post("/api/scheduling/availability/{trainer_id}/exceptions")
def add_exception(trainer_id: str, payload: ExceptionIn, user: User=Depends(current_user), db: Session=Depends(db_session)):
    trainer_self_or_owner(user, trainer_id); require_trainer(db, trainer_id)
    start,end=interval(payload.starts_at,payload.ends_at)
    e=AvailabilityException(trainer_id=trainer_id,starts_at=start,ends_at=end,kind=payload.kind,reason=payload.reason)
    db.add(e); db.commit(); return {"id":e.id}

@app.post("/api/scheduling/availability/{trainer_id}/archive/{item_id}")
def archive_availability(trainer_id: str, item_id: str, user: User=Depends(current_user), db: Session=Depends(db_session)):
    trainer_self_or_owner(user, trainer_id)
    obj=db.get(AvailabilityRule,item_id) or db.get(AvailabilityException,item_id)
    if not obj or obj.trainer_id != trainer_id: raise HTTPException(404)
    obj.active=False; db.commit(); return {"ok":True}

@app.get("/api/scheduling/slots/{trainer_id}")
def check_slot(trainer_id: str, starts_at: datetime, ends_at: datetime, lead_id: str, user: User=Depends(current_user), db: Session=Depends(db_session)):
    owner_only(user); require_trainer(db,trainer_id)
    if not db.get(Lead,lead_id): raise HTTPException(404,"Client not found")
    start,end=interval(starts_at,ends_at)
    return {"available":available(db,trainer_id,start,end) and not conflicts(db,trainer_id,lead_id,start,end)}

@app.get("/api/scheduling/assignments")
def list_assignments(user: User=Depends(current_user), db: Session=Depends(db_session)):
    stmt=select(Assignment).order_by(Assignment.created_at.desc())
    if user.role=="trainer": stmt=stmt.where(Assignment.trainer_id==user.id)
    return [serialize_assignment(a,db) for a in db.scalars(stmt).all()]

@app.post("/api/scheduling/assignments")
def create_assignment(payload: AssignmentIn, user: User=Depends(current_user), db: Session=Depends(db_session)):
    owner_only(user)
    if not db.get(Lead,payload.lead_id): raise HTTPException(404,"Client not found")
    require_trainer(db,payload.trainer_id)
    start,end=interval(payload.starts_at,payload.ends_at)
    if not available(db,payload.trainer_id,start,end) or conflicts(db,payload.trainer_id,payload.lead_id,start,end):
        raise HTTPException(409,"Trainer unavailable or slot conflicts")
    a=Assignment(lead_id=payload.lead_id,trainer_id=payload.trainer_id,created_by_id=user.id,starts_at=start,ends_at=end,note=payload.note)
    db.add(a);db.flush();event(db,a,user,"requested",payload.note)
    db.add(Notification(recipient_id=a.trainer_id,assignment_id=a.id,message=f"New training assignment for {db.get(Lead,a.lead_id).name}"))
    db.commit();return serialize_assignment(a,db)

@app.get("/api/scheduling/assignments/{assignment_id}/history")
def assignment_history(assignment_id: str, user: User=Depends(current_user), db: Session=Depends(db_session)):
    a=db.get(Assignment,assignment_id)
    if not a: raise HTTPException(404)
    trainer_self_or_owner(user,a.trainer_id)
    events=db.scalars(select(AssignmentEvent).where(AssignmentEvent.assignment_id==a.id).order_by(AssignmentEvent.created_at)).all()
    return [{"id":e.id,"action":e.action,"detail":e.detail,"actor_id":e.actor_id,"created_at":iso(e.created_at)} for e in events]

@app.post("/api/scheduling/assignments/{assignment_id}/action")
def assignment_action(assignment_id: str, payload: ActionIn, user: User=Depends(current_user), db: Session=Depends(db_session)):
    a=db.get(Assignment,assignment_id)
    if not a: raise HTTPException(404)
    owner=user.role in ("owner","admin")
    if not owner and (user.role!="trainer" or a.trainer_id!=user.id): raise HTTPException(403)
    action=payload.action
    allowed={"accept":("pending",),"decline":("pending",),"propose":("pending",),
             "return":("confirmed",),"cancel":("pending","proposed","confirmed"),"approve_proposal":("proposed",)}
    if a.status not in allowed[action]: raise HTTPException(409,"Invalid state transition")
    if action in ("accept","decline","propose","return") and (owner or a.trainer_id!=user.id): raise HTTPException(403,"Trainer action required")
    if action in ("cancel","approve_proposal") and not owner: raise HTTPException(403,"Owner action required")
    if action=="propose":
        if payload.starts_at is None or payload.ends_at is None: raise HTTPException(422,"New times required")
        start,end=interval(payload.starts_at,payload.ends_at)
        if not available(db,a.trainer_id,start,end) or conflicts(db,a.trainer_id,a.lead_id,start,end,a.id):
            raise HTTPException(409,"Proposed time unavailable")
        a.starts_at=start; a.ends_at=end; a.status="proposed"
    elif action in ("accept","approve_proposal"):
        if not available(db,a.trainer_id,a.starts_at,a.ends_at) or conflicts(db,a.trainer_id,a.lead_id,a.starts_at,a.ends_at,a.id):
            raise HTTPException(409,"Slot no longer available")
        # Prevent a lead from silently retaining multiple current trainer assignments.
        active=db.scalar(select(Assignment).where(Assignment.lead_id==a.lead_id, Assignment.status=="confirmed",Assignment.id!=a.id))
        if active: raise HTTPException(409,"Client has an existing confirmed assignment; return or cancel it first")
        a.status="confirmed"
        db.get(Lead,a.lead_id).assigned_trainer_id=a.trainer_id
    elif action=="decline": a.status="declined"
    elif action=="return":
        a.status="returned"
        lead=db.get(Lead,a.lead_id)
        if lead.assigned_trainer_id==a.trainer_id:lead.assigned_trainer_id=None
    else:
        a.status="cancelled"
        lead=db.get(Lead,a.lead_id)
        if lead.assigned_trainer_id==a.trainer_id:lead.assigned_trainer_id=None
    a.updated_at=datetime.now(timezone.utc)
    event(db,a,user,action,payload.note)
    if action in ("decline","return","propose"):
        notify_owners(db,a,f"{db.get(User,a.trainer_id).name} { {'decline':'declined','return':'returned','propose':'proposed a new time for'}[action] } assignment for {db.get(Lead,a.lead_id).name}: {payload.note}")
    elif action in ("approve_proposal","cancel"):
        db.add(Notification(recipient_id=a.trainer_id,assignment_id=a.id,message=f"Assignment {action.replace('_',' ')}: {db.get(Lead,a.lead_id).name}"))
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,"A confirmed booking conflicts with this time slot")
    return serialize_assignment(a,db)

@app.get("/api/scheduling/notifications")
def list_notifications(user: User=Depends(current_user), db: Session=Depends(db_session)):
    rows=db.scalars(select(Notification).where(Notification.recipient_id==user.id).order_by(Notification.created_at.desc()).limit(100)).all()
    return [{"id":n.id,"message":n.message,"assignment_id":n.assignment_id,"read_at":iso(n.read_at),"created_at":iso(n.created_at)} for n in rows]

@app.post("/api/scheduling/notifications/{notification_id}/read")
def read_notification(notification_id: str, user: User=Depends(current_user), db: Session=Depends(db_session)):
    n=db.get(Notification,notification_id)
    if not n or n.recipient_id!=user.id: raise HTTPException(404)
    n.read_at=datetime.now(timezone.utc);db.commit();return {"ok":True}


# ---- v0.2.1 visual calendars / read-only export ----
import hashlib
import secrets
from fastapi.responses import Response as RawResponse

class CalendarSubscriptionIn(BaseModel):
    # Caller controls the public URL; it must be the actual HTTPS CRM origin in production.
    pass

def calendar_window(start: datetime, end: datetime):
    start, end = utc(start), utc(end)
    if start >= end or end-start > timedelta(days=62):
        raise HTTPException(422, "Calendar range must be between 1 minute and 62 days")
    return start, end

def merge_intervals(intervals):
    merged = []
    for a, b in sorted(intervals):
        if a >= b: continue
        if merged and a <= merged[-1][1]: merged[-1]=(merged[-1][0], max(b,merged[-1][1]))
        else: merged.append((a,b))
    return merged

def subtract_intervals(base, blocked):
    output=[]
    for a,b in base:
        pieces=[(a,b)]
        for x,y in blocked:
            updated=[]
            for l,r in pieces:
                if y <= l or x >= r: updated.append((l,r))
                else:
                    if l<x: updated.append((l,x))
                    if y<r: updated.append((y,r))
            pieces=updated
        output.extend(pieces)
    return output

def build_calendar(db, trainer_id, start, end, include_details):
    rules=db.scalars(select(AvailabilityRule).where(AvailabilityRule.trainer_id==trainer_id, AvailabilityRule.active==True)).all()
    exceptions=db.scalars(select(AvailabilityException).where(AvailabilityException.trainer_id==trainer_id, AvailabilityException.active==True,
        AvailabilityException.starts_at<end, AvailabilityException.ends_at>start)).all()
    assignments=db.scalars(select(Assignment).where(Assignment.trainer_id==trainer_id,
        Assignment.starts_at<end, Assignment.ends_at>start, Assignment.status.in_(["confirmed","pending","proposed"]))).all()
    base=[]
    day=start.astimezone(LOCAL_TZ).date()-timedelta(days=1)
    last=end.astimezone(LOCAL_TZ).date()+timedelta(days=1)
    while day<=last:
        for r in rules:
            if r.weekday==day.weekday():
                a=datetime.combine(day,r.start_time,LOCAL_TZ).astimezone(timezone.utc)
                b=datetime.combine(day,r.end_time,LOCAL_TZ).astimezone(timezone.utc)
                if a<b: base.append((max(a,start),min(b,end)))
        day+=timedelta(days=1)
    base += [(max(utc(e.starts_at),start),min(utc(e.ends_at),end)) for e in exceptions if e.kind=="available"]
    blocked=[(max(utc(e.starts_at),start),min(utc(e.ends_at),end)) for e in exceptions if e.kind=="unavailable"]
    # Blocked periods override additions; subtract confirmed sessions from free time.
    working=subtract_intervals(merge_intervals(base),merge_intervals(blocked))
    client_sessions=db.scalars(select(ClientSession).where(ClientSession.trainer_id==trainer_id,
        ClientSession.starts_at<end,ClientSession.ends_at>start,ClientSession.status=="confirmed")).all()
    sessions=[(max(utc(a.starts_at),start),min(utc(a.ends_at),end)) for a in assignments if a.status=="confirmed"]
    sessions += [(max(utc(a.starts_at),start),min(utc(a.ends_at),end)) for a in client_sessions]
    free=subtract_intervals(working,merge_intervals(sessions))
    items=[]
    for i,(a,b) in enumerate(free):
        items.append({"id":f"free-{trainer_id}-{i}","kind":"free","trainer_id":trainer_id,"starts_at":iso(a),"ends_at":iso(b),"title":"Available"})
    for i,(a,b) in enumerate(blocked):
        if a<b: items.append({"id":f"off-{trainer_id}-{i}","kind":"unavailable","trainer_id":trainer_id,"starts_at":iso(a),"ends_at":iso(b),"title":"Unavailable"})
    for a in assignments:
        title=(db.get(Lead,a.lead_id).name if include_details and db.get(Lead,a.lead_id) else "Training session") if a.status=="confirmed" else "Awaiting response"
        items.append({"id":a.id,"kind":a.status,"trainer_id":trainer_id,"starts_at":iso(a.starts_at),"ends_at":iso(a.ends_at),"title":title})
    for a in client_sessions:
        lead=db.get(Lead,a.lead_id)
        items.append({"id":a.id,"kind":"confirmed","trainer_id":trainer_id,"starts_at":iso(a.starts_at),
                      "ends_at":iso(a.ends_at),"title":lead.name if include_details and lead else "Training session"})
    for occ, evt in db.execute(select(GymEventOccurrence, GymEvent).join(GymEvent, GymEvent.id == GymEventOccurrence.event_id)
            .join(GymEventCoach, GymEventCoach.event_id == GymEvent.id)
            .where(GymEventCoach.coach_id == trainer_id, GymEventCoach.active == True,
                   GymEventOccurrence.status == "confirmed", GymEvent.active == True,
                   GymEventOccurrence.starts_at < end, GymEventOccurrence.ends_at > start)).all():
        items.append({"id": occ.id, "kind": "confirmed", "trainer_id": trainer_id,
                      "starts_at": iso(occ.starts_at), "ends_at": iso(occ.ends_at),
                      "title": evt.name if evt.kind == "class" else "Blocked: " + evt.name,
                      "group_event_id": evt.id})
    # Do not advertise free time occupied by a class or non-client block.
    busy = [(utc(o.starts_at), utc(o.ends_at)) for o in db.scalars(
        select(GymEventOccurrence).join(GymEventCoach, GymEventCoach.event_id == GymEventOccurrence.event_id)
        .where(GymEventCoach.coach_id == trainer_id, GymEventCoach.active == True,
               GymEventOccurrence.status == "confirmed", GymEventOccurrence.starts_at < end,
               GymEventOccurrence.ends_at > start)).all()]
    if busy:
        free_items = [i for i in items if i["kind"] == "free"]
        items = [i for i in items if i["kind"] != "free"]
        for i in free_items:
            for j,(a,b) in enumerate(subtract_intervals([(datetime.fromisoformat(i["starts_at"]),
                datetime.fromisoformat(i["ends_at"]))], merge_intervals(busy))):
                items.append({**i,"id":i["id"]+"-"+str(j),"starts_at":iso(a),"ends_at":iso(b)})
    return sorted(items,key=lambda x:x["starts_at"])

@app.get("/api/calendar/events")
def calendar_events(starts_at: datetime, ends_at: datetime, trainer_id: str | None=None,
                    user: User=Depends(current_user), db: Session=Depends(db_session)):
    start,end=calendar_window(starts_at,ends_at)
    if user.role=="trainer":
        if trainer_id and trainer_id!=user.id: raise HTTPException(403)
        ids=[user.id]
    else:
        owner_only(user)
        ids=[trainer_id] if trainer_id else list(db.scalars(select(User.id).where(User.role.in_(["trainer", "owner", "admin"]))))
    results=[]
    for tid in ids:
        t=db.get(User,tid)
        if not t or t.role not in ("trainer","owner","admin"): raise HTTPException(404)
        for item in build_calendar(db,tid,start,end,True):
            item["trainer_name"]=t.name
            results.append(item)
    if user.role != "trainer" and not trainer_id:
        combined=[]; known=set()
        for r in sorted(results,key=lambda x:x["starts_at"]):
            if r.get("group_event_id"):
                if r["id"] in known: continue
                known.add(r["id"])
                ev=db.get(GymEvent,r["group_event_id"])
                co=db.scalars(select(GymEventCoach).where(GymEventCoach.event_id==ev.id,
                                                         GymEventCoach.active==True)).all()
                r["trainer_name"]=" + ".join(db.get(User,c.coach_id).name for c in co)
            combined.append(r)
        return combined
    return sorted(results,key=lambda x:x["starts_at"])

@app.post("/api/calendar/subscription")
def create_calendar_subscription(user: User=Depends(current_user), db: Session=Depends(db_session)):
    # Only self: an owner cannot silently mint a trainer's private calendar feed.
    token=secrets.token_urlsafe(36)
    record=CalendarSubscription(trainer_id=user.id,token_hash=hashlib.sha256(token.encode()).hexdigest())
    db.add(record);db.commit()
    return {"id":record.id,"path":f"/api/calendar/feed/{token}.ics","warning":"Treat this URL like a password. It gives read-only calendar access to anyone holding it."}

@app.get("/api/calendar/subscriptions")
def list_calendar_subscriptions(user: User=Depends(current_user), db: Session=Depends(db_session)):
    rows=db.scalars(select(CalendarSubscription).where(CalendarSubscription.trainer_id==user.id,
        CalendarSubscription.revoked_at.is_(None))).all()
    return [{"id":r.id,"created_at":iso(r.created_at)} for r in rows]

@app.post("/api/calendar/subscriptions/{sub_id}/revoke")
def revoke_calendar_subscription(sub_id: str,user: User=Depends(current_user), db: Session=Depends(db_session)):
    r=db.get(CalendarSubscription,sub_id)
    if not r or r.trainer_id!=user.id: raise HTTPException(404)
    r.revoked_at=datetime.now(timezone.utc);db.commit()
    return {"ok":True}

def ics_escape(value):
    return str(value).replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace("\n","\\n")

def ics_date(dt):
    return utc(dt).strftime("%Y%m%dT%H%M%SZ")

def ics_export(db,trainer_id,start,end):
    events=build_calendar(db,trainer_id,start,end,False)
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Pale Horse Barbell//CRM//EN","CALSCALE:GREGORIAN","X-WR-CALNAME:Pale Horse Training"]
    for e in events:
        if e["kind"]!="confirmed": continue
        lines += ["BEGIN:VEVENT",f"UID:{e['id']}@palehorsebarbell.com",f"DTSTAMP:{ics_date(datetime.now(timezone.utc))}",
                  f"DTSTART:{ics_date(datetime.fromisoformat(e['starts_at']))}",f"DTEND:{ics_date(datetime.fromisoformat(e['ends_at']))}",
                  "SUMMARY:Pale Horse training session","END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)+"\r\n"

@app.get("/api/calendar/export.ics")
def download_calendar(user: User=Depends(current_user),db: Session=Depends(db_session)):
    start=datetime.now(timezone.utc)-timedelta(days=7)
    end=start+timedelta(days=61)
    return RawResponse(content=ics_export(db,user.id,start,end),media_type="text/calendar",
                       headers={"Content-Disposition":"attachment; filename=palehorse-calendar.ics","Cache-Control":"no-store"})

@app.get("/api/calendar/feed/{token}.ics")
def calendar_feed(token: str, db: Session=Depends(db_session)):
    # No session cookie is required: the unguessable URL is the credential.
    digest=hashlib.sha256(token.encode()).hexdigest()
    record=db.scalar(select(CalendarSubscription).where(CalendarSubscription.token_hash==digest,
        CalendarSubscription.revoked_at.is_(None)))
    if not record: raise HTTPException(404)
    start=datetime.now(timezone.utc)-timedelta(days=7)
    end=start+timedelta(days=61)
    return RawResponse(content=ics_export(db,record.trainer_id,start,end),media_type="text/calendar",
                       headers={"Cache-Control":"private, no-store","X-Robots-Tag":"noindex"})


# ---- v0.2.9 one-appointment calendar downloads (no OAuth required) ----
def calendar_event_ics(uid: str, starts_at: datetime, ends_at: datetime,
                       summary: str, updated_at: datetime | None = None) -> str:
    """Private single-event download; deliberately omits attendee/health/contact data."""
    # RFC 5545: escape content and fold long content lines at <=75 octets.
    def fold(line: str) -> str:
        fragments=[]
        current=''
        for character in line:
            candidate=current+character
            if len(candidate.encode('utf-8')) > 75 and current:
                fragments.append(current)
                current=' '+character
            else:
                current=candidate
        fragments.append(current)
        return '\r\n'.join(fragments)
    fields=[
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Pale Horse Barbell//CRM//EN',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'BEGIN:VEVENT',
        'UID:'+uid+'@palehorsebarbell.com',
        'DTSTAMP:'+ics_date(updated_at or datetime.now(timezone.utc)),
        'DTSTART:'+ics_date(starts_at), 'DTEND:'+ics_date(ends_at),
        'SUMMARY:'+ics_escape(summary),
        'DESCRIPTION:'+ics_escape('Pale Horse Barbell training appointment. Confirm changes with your coach.'),
        'END:VEVENT', 'END:VCALENDAR'
    ]
    return '\r\n'.join(fold(line) for line in fields)+'\r\n'

def private_calendar_download(content: str, filename: str):
    return RawResponse(content=content,media_type='text/calendar; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="{filename}"',
        'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
        'X-Robots-Tag':'noindex'
    })

@app.get('/api/calendar/sessions/{session_id}/invitation.ics')
def client_session_invitation(session_id: str, user: User=Depends(current_user),
                              db: Session=Depends(db_session)):
    s=db.get(ClientSession,session_id)
    if not s: raise HTTPException(404,'Session not found')
    trainer_self_or_owner(user,s.trainer_id)
    if s.status!='confirmed': raise HTTPException(409,'Only confirmed sessions can be exported')
    return private_calendar_download(calendar_event_ics(
        s.id,s.starts_at,s.ends_at,'Pale Horse Barbell – '+s.session_type,s.updated_at),
        'palehorse-training.ics')

@app.get('/api/calendar/classes/{event_id}/occurrences/{occurrence_id}/invitation.ics')
def gym_occurrence_invitation(event_id: str, occurrence_id: str,
                               user: User=Depends(current_user),db: Session=Depends(db_session)):
    ev=gym_event_access(db,event_id,user)
    occurrence=db.get(GymEventOccurrence,occurrence_id)
    if not occurrence or occurrence.event_id!=event_id:
        raise HTTPException(404,'Class occurrence not found')
    if occurrence.status!='confirmed' or not ev.active:
        raise HTTPException(409,'Only confirmed class dates can be exported')
    # No roster or attendee data in the exported invitation.
    title=('Pale Horse Barbell – '+ev.name) if ev.kind=='class' else 'Pale Horse Barbell – Busy'
    return private_calendar_download(calendar_event_ics(
        occurrence.id,occurrence.starts_at,occurrence.ends_at,title,occurrence.created_at),
        'palehorse-class.ics')


@app.get('/api/calendar/classes/{event_id}/series.ics')
def gym_class_series_download(event_id: str, user: User=Depends(current_user),
                              db: Session=Depends(db_session)):
    """One download containing confirmed class dates in the upcoming year.

    Each occurrence is its own VEVENT with its existing stable UID. This keeps
    moved times intact and omits cancelled dates instead of re-generating the
    recurrence pattern (which could resurrect cancelled classes).
    """
    ev = gym_event_access(db, event_id, user)
    if not ev.active or ev.kind != 'class':
        raise HTTPException(409, 'Only active group classes can be exported as a series')
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=365)
    dates = db.scalars(select(GymEventOccurrence).where(
        GymEventOccurrence.event_id == event_id,
        GymEventOccurrence.status == 'confirmed',
        GymEventOccurrence.starts_at >= now,
        GymEventOccurrence.starts_at < cutoff,
    ).order_by(GymEventOccurrence.starts_at)).all()
    if not dates:
        raise HTTPException(404, 'No upcoming confirmed class dates to export in the next year')
    title = 'Pale Horse Barbell – ' + ev.name
    # Reuse the single-date exporter so stable IDs, privacy, UTC formatting,
    # and RFC 5545 line-folding remain consistent.
    components = []
    for item in dates:
        single = calendar_event_ics(item.id, item.starts_at, item.ends_at,
                                    title, item.created_at)
        components.append('BEGIN:VEVENT\r\n' + single.split('BEGIN:VEVENT\r\n', 1)[1].split('\r\nEND:VEVENT', 1)[0] + '\r\nEND:VEVENT')
    calendar = ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n'
                'PRODID:-//Pale Horse Barbell//CRM//EN\r\n'
                'CALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n'
                + '\r\n'.join(components) + '\r\nEND:VCALENDAR\r\n')
    return private_calendar_download(calendar, 'palehorse-class-series.ics')


# ---- v0.2.2 existing clients / session scheduling ----
class OnboardIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=50)

class SessionIn(BaseModel):
    lead_id: str
    trainer_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    session_type: str = Field(default="Personal training", max_length=80)
    note: str = Field(default="", max_length=2000)

class SessionMove(BaseModel):
    starts_at: datetime
    ends_at: datetime
    note: str = Field(default="", max_length=2000)

class SessionStatus(BaseModel):
    status: Literal["cancelled", "no_show", "completed"]
    note: str = Field(default="", max_length=2000)

class SeriesIn(BaseModel):
    lead_id: str
    trainer_id: str | None = None
    start_date: date
    weekday: int = Field(ge=0, le=6)
    local_time: time
    duration_minutes: int = Field(ge=15, le=240)
    interval_weeks: int = Field(default=1, ge=1, le=4)
    until_date: date | None = None
    session_type: str = Field(default="Personal training", max_length=80)

def client_access(db, actor, lead_id, tid):
    lead=db.get(Lead,lead_id)
    if not lead: raise HTTPException(404,"Client not found")
    trainer_self_or_owner(actor,tid)
    require_trainer(db,tid)
    if lead.assigned_trainer_id != tid:
        raise HTTPException(403,"Client must be approved and assigned to this trainer")
    return lead

def session_conflict(db,tid,lid,start,end,exclude=None):
    if gym_busy(db,tid,start,end): return True
    stmt=select(ClientSession.id).where(ClientSession.status=="confirmed",ClientSession.starts_at<end,ClientSession.ends_at>start,
         or_(ClientSession.trainer_id==tid,ClientSession.lead_id==lid))
    if exclude: stmt=stmt.where(ClientSession.id!=exclude)
    if db.scalar(stmt): return True
    query=select(Assignment.id).where(Assignment.status=="confirmed",Assignment.starts_at<end,Assignment.ends_at>start,
        or_(Assignment.trainer_id==tid,Assignment.lead_id==lid))
    return db.scalar(query) is not None

def audit_session(db,s,actor,action,detail=""):
    db.add(SessionAudit(session_id=s.id,actor_id=actor.id,action=action,detail=detail))

def serialize_session(s,db):
    lead=db.get(Lead,s.lead_id)
    return {"id":s.id,"lead_id":s.lead_id,"lead_name":lead.name if lead else "Unknown", "trainer_id":s.trainer_id,
            "series_id":s.series_id,"status":s.status,"session_type":s.session_type,"note":s.note,
            "starts_at":iso(s.starts_at),"ends_at":iso(s.ends_at)}

@app.post("/api/clients/onboard")
def onboard_client(data:OnboardIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    if user.role!="trainer": raise HTTPException(403,"Trainer onboarding only")
    lead=Lead(name=data.name.strip(),email=data.email.strip(),phone=data.phone.strip(),stage="converted")
    db.add(lead);db.flush()
    item=ClientOnboarding(trainer_id=user.id,lead_id=lead.id)
    db.add(item);db.commit()
    return {"id":item.id,"status":"pending","message":"Sent for owner approval. Sessions cannot be booked until approved."}

@app.get("/api/clients/onboarding")
def list_onboarding(user:User=Depends(current_user),db:Session=Depends(db_session)):
    stmt=select(ClientOnboarding).order_by(ClientOnboarding.created_at.desc())
    if user.role=="trainer": stmt=stmt.where(ClientOnboarding.trainer_id==user.id)
    else: owner_only(user)
    return [{"id":r.id,"trainer_id":r.trainer_id,"trainer_name":db.get(User,r.trainer_id).name,
      "lead_id":r.lead_id,"client_name":db.get(Lead,r.lead_id).name,"status":r.status} for r in db.scalars(stmt).all()]

@app.post("/api/clients/onboarding/{request_id}/{decision}")
def review_onboarding(request_id:str,decision:Literal["approve","reject"],user:User=Depends(current_user),db:Session=Depends(db_session)):
    owner_only(user)
    row=db.get(ClientOnboarding,request_id)
    if not row: raise HTTPException(404)
    if row.status!="pending": raise HTTPException(409,"Already reviewed")
    row.status="approved" if decision=="approve" else "rejected";row.reviewed_by_id=user.id
    if decision=="approve":
        lead=db.get(Lead,row.lead_id)
        if lead.assigned_trainer_id and lead.assigned_trainer_id!=row.trainer_id: raise HTTPException(409,"Already assigned")
        lead.assigned_trainer_id=row.trainer_id
        # Import rows staged for this client become schedulable only after approval.
        from .imports import activate_approved_client
        activate_approved_client(db,lead.id,user)
    db.commit();return {"status":row.status}

@app.get("/api/sessions/search")
def search_sessions(starts_at: datetime, ends_at: datetime, trainer_id: str | None = None,
                    lead_id: str | None = None, status: str = "all", limit: int = 30,
                    offset: int = 0, user: User = Depends(current_user), db: Session = Depends(db_session)):
    """Paged trainer-scoped appointment query for the Client Sessions list."""
    start, end = calendar_window(starts_at, ends_at)
    if status not in ("all", "upcoming", "completed"):
        raise HTTPException(422, "Invalid status filter")
    if not (1 <= limit <= 100) or not (0 <= offset <= 100000):
        raise HTTPException(422, "Invalid page size or offset")
    stmt = select(ClientSession).where(ClientSession.starts_at < end, ClientSession.ends_at > start)
    if user.role == "trainer":
        if trainer_id and trainer_id != user.id: raise HTTPException(403)
        stmt = stmt.where(ClientSession.trainer_id == user.id)
    else:
        owner_only(user)
        if trainer_id:
            require_trainer(db, trainer_id)
            stmt = stmt.where(ClientSession.trainer_id == trainer_id)
    if lead_id:
        # Never leak an unrelated client's existence; trainer scope still applies.
        stmt = stmt.where(ClientSession.lead_id == lead_id)
    if status == "upcoming":
        stmt = stmt.where(ClientSession.status == "confirmed",
                          ClientSession.starts_at >= datetime.now(timezone.utc))
    elif status == "completed":
        stmt = stmt.where(ClientSession.status == "completed")
    rows = db.scalars(stmt.order_by(ClientSession.starts_at, ClientSession.id).offset(offset).limit(limit + 1)).all()
    return {"items": [serialize_session(row, db) for row in rows[:limit]],
            "has_more": len(rows) > limit, "offset": offset, "limit": limit}

@app.get("/api/sessions")
def list_sessions(starts_at:datetime,ends_at:datetime,trainer_id:str|None=None,user:User=Depends(current_user),db:Session=Depends(db_session)):
    start,end=calendar_window(starts_at,ends_at)
    stmt=select(ClientSession).where(ClientSession.starts_at<end,ClientSession.ends_at>start).order_by(ClientSession.starts_at)
    if user.role=="trainer":
        if trainer_id and trainer_id!=user.id:raise HTTPException(403)
        stmt=stmt.where(ClientSession.trainer_id==user.id)
    else:
        owner_only(user)
        if trainer_id: require_trainer(db,trainer_id);stmt=stmt.where(ClientSession.trainer_id==trainer_id)
    return [serialize_session(s,db) for s in db.scalars(stmt).all()]

@app.post("/api/sessions")
def create_session(data:SessionIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    tid=data.trainer_id if user.role in ("owner","admin") else user.id
    if not tid:raise HTTPException(422,"Choose trainer")
    client_access(db,user,data.lead_id,tid)
    start,end=interval(data.starts_at,data.ends_at)
    if not available(db,tid,start,end) or session_conflict(db,tid,data.lead_id,start,end):raise HTTPException(409,"Outside availability or conflicting session")
    session=ClientSession(lead_id=data.lead_id,trainer_id=tid,starts_at=start,ends_at=end,session_type=data.session_type,note=data.note)
    db.add(session);db.flush();audit_session(db,session,user,"created",data.note)
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,"Concurrent booking conflict")
    return serialize_session(session,db)

@app.post("/api/sessions/{session_id}/reschedule")
def move_session(session_id:str,data:SessionMove,user:User=Depends(current_user),db:Session=Depends(db_session)):
    s=db.get(ClientSession,session_id)
    if not s:raise HTTPException(404)
    trainer_self_or_owner(user,s.trainer_id)
    if s.status not in ("confirmed",):raise HTTPException(409,"Only confirmed sessions can move")
    start,end=interval(data.starts_at,data.ends_at)
    if not available(db,s.trainer_id,start,end) or session_conflict(db,s.trainer_id,s.lead_id,start,end,s.id):raise HTTPException(409,"Outside availability or conflicting session")
    old=f"{iso(s.starts_at)} – {iso(s.ends_at)}";s.starts_at=start;s.ends_at=end;s.updated_at=datetime.now(timezone.utc)
    audit_session(db,s,user,"rescheduled",f"{old} -> {iso(start)} – {iso(end)}. {data.note}")
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,"Concurrent booking conflict")
    return serialize_session(s,db)

@app.post("/api/sessions/{session_id}/status")
def update_session_status(session_id:str,data:SessionStatus,user:User=Depends(current_user),db:Session=Depends(db_session)):
    s=db.get(ClientSession,session_id)
    if not s:raise HTTPException(404)
    trainer_self_or_owner(user,s.trainer_id)
    if s.status!="confirmed":raise HTTPException(409,"Only confirmed sessions can be updated")
    old=s.status;s.status=data.status;s.updated_at=datetime.now(timezone.utc)
    audit_session(db,s,user,"status",f"{old} -> {data.status}. {data.note}")
    db.commit();return serialize_session(s,db)

@app.get("/api/sessions/{session_id}/history")
def session_history(session_id:str,user:User=Depends(current_user),db:Session=Depends(db_session)):
    s=db.get(ClientSession,session_id)
    if not s:raise HTTPException(404)
    trainer_self_or_owner(user,s.trainer_id)
    return [{"action":a.action,"detail":a.detail,"created_at":iso(a.created_at),"actor_id":a.actor_id} for a in db.scalars(select(SessionAudit).where(SessionAudit.session_id==s.id).order_by(SessionAudit.created_at))]

def occurrences(data:SeriesIn):
    # Finite series capped at a year; unlimited series use a 180-day rolling planning horizon.
    first=data.start_date
    last=data.until_date or (first+timedelta(days=180))
    if last<first or last>first+timedelta(days=366):raise HTTPException(422,"Choose an end within one year, or no end")
    day=first+timedelta(days=(data.weekday-first.weekday())%7)
    while day<=last:
        dt=datetime.combine(day,data.local_time,LOCAL_TZ)
        # Verify local time exists unambiguously; reject gaps rather than shift a booking.
        if dt.astimezone(timezone.utc).astimezone(LOCAL_TZ).replace(tzinfo=None)!=dt.replace(tzinfo=None):
            raise HTTPException(422,f"Nonexistent local time on {day}")
        a=dt.astimezone(timezone.utc);b=a+timedelta(minutes=data.duration_minutes)
        yield day,a,b
        day+=timedelta(weeks=data.interval_weeks)

class MultiSeriesIn(BaseModel):
    lead_id: str
    trainer_id: str | None = None
    start_date: date
    until_date: date | None = None
    interval_weeks: int = Field(default=1, ge=1, le=4)
    session_type: str = Field(default="Personal training", max_length=80)
    slots: list[dict] = Field(min_length=1, max_length=14)

def expand_multi(data: MultiSeriesIn):
    rules=[]
    for slot in data.slots:
        try:
            rule=SeriesIn(lead_id=data.lead_id,trainer_id=data.trainer_id,start_date=data.start_date,
                until_date=data.until_date,interval_weeks=data.interval_weeks,session_type=data.session_type,
                weekday=slot['weekday'],local_time=slot['local_time'],duration_minutes=slot['duration_minutes'])
        except (KeyError,ValueError,TypeError) as exc:
            raise HTTPException(422,f"Invalid weekly slot: {exc}")
        rules.append(rule)
    return rules

def validate_multi(data,user,db):
    tid=data.trainer_id if user.role in ('owner','admin') else user.id
    if not tid: raise HTTPException(422,"Trainer required")
    client_access(db,user,data.lead_id,tid)
    rules=expand_multi(data)
    all_entries=[]
    for i,rule in enumerate(rules):
        for day,start,end in occurrences(rule):
            all_entries.append((i,day,start,end))
    if not all_entries:raise HTTPException(422,"No occurrences")
    all_entries.sort(key=lambda item:item[2])
    conflicts=[]
    previous=None
    for i,day,start,end in all_entries:
        if previous and start<previous[3]:
            conflicts.append({"date":str(day),"reason":"Selected weekly slots overlap"})
        if not available(db,tid,start,end) or session_conflict(db,tid,data.lead_id,start,end):
            conflicts.append({"date":str(day),"reason":"Availability or booking conflict"})
        previous=(i,day,start,end)
    return tid,rules,all_entries,conflicts

@app.post("/api/sessions/multi-series/preview")
def preview_multi(data:MultiSeriesIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    tid,rules,entries,conflicts=validate_multi(data,user,db)
    return {"total":len(entries),"conflicts":conflicts,"rule_count":len(rules)}

@app.post("/api/sessions/multi-series")
def create_multi(data:MultiSeriesIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    tid,rules,entries,conflicts=validate_multi(data,user,db)
    if conflicts:raise HTTPException(409,"Resolve conflicts: "+", ".join(c['date'] for c in conflicts[:12]))
    created=[]
    for i,rule in enumerate(rules):
        occ=[entry for entry in entries if entry[0]==i]
        series=SessionSeries(trainer_id=tid,lead_id=data.lead_id,weekday=rule.weekday,local_time=rule.local_time,
            duration_minutes=rule.duration_minutes,interval_weeks=rule.interval_weeks,
            start_date=datetime.combine(rule.start_date,time.min),
            until_date=datetime.combine(rule.until_date,time.min) if rule.until_date else None,
            materialized_through=datetime.combine(occ[-1][1],time.min) if occ else None)
        db.add(series);db.flush();created.append(series.id)
        for _,day,start,end in occ:
            session=ClientSession(trainer_id=tid,lead_id=data.lead_id,series_id=series.id,
                occurrence_date=datetime.combine(day,time.min),starts_at=start,ends_at=end,session_type=data.session_type)
            db.add(session);db.flush();audit_session(db,session,user,'created_recurring',f'Multi-day plan / series {series.id}')
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,"Concurrent booking conflict; retry preview")
    return {"series_ids":created,"sessions_created":len(entries),"rule_count":len(rules),
            "notice":"Open-ended series require periodic extension; each day is an independently editable series."}

@app.post("/api/sessions/series/preview")
def preview_series(data:SeriesIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    tid=data.trainer_id if user.role in ("owner","admin") else user.id
    if not tid:raise HTTPException(422,"Trainer required")
    client_access(db,user,data.lead_id,tid)
    items=[]
    for day,a,b in occurrences(data):
        reason="" if available(db,tid,a,b) and not session_conflict(db,tid,data.lead_id,a,b) else "Availability or booking conflict"
        items.append({"date":str(day),"starts_at":iso(a),"ends_at":iso(b),"conflict":bool(reason),"reason":reason})
    return {"total":len(items),"conflicts":[x for x in items if x["conflict"]],"items":items}

@app.post("/api/sessions/series")
def create_series(data:SeriesIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    tid=data.trainer_id if user.role in ("owner","admin") else user.id
    if not tid:raise HTTPException(422,"Trainer required")
    client_access(db,user,data.lead_id,tid)
    entries=list(occurrences(data))
    if not entries:raise HTTPException(422,"No occurrences")
    bad=[str(day) for day,a,b in entries if not available(db,tid,a,b) or session_conflict(db,tid,data.lead_id,a,b)]
    if bad:raise HTTPException(409,"Resolve conflicts before saving: "+", ".join(bad[:12]))
    series=SessionSeries(trainer_id=tid,lead_id=data.lead_id,weekday=data.weekday,local_time=data.local_time,
      duration_minutes=data.duration_minutes,interval_weeks=data.interval_weeks,start_date=datetime.combine(data.start_date,time.min),
      until_date=datetime.combine(data.until_date,time.min) if data.until_date else None,
      materialized_through=datetime.combine(entries[-1][0],time.min))
    db.add(series);db.flush()
    for day,a,b in entries:
        s=ClientSession(trainer_id=tid,lead_id=data.lead_id,series_id=series.id,occurrence_date=datetime.combine(day,time.min),
          starts_at=a,ends_at=b,session_type=data.session_type)
        db.add(s);db.flush();audit_session(db,s,user,"created_recurring",f"Series {series.id}")
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,"Concurrent booking conflict; retry preview")
    return {"id":series.id,"sessions_created":len(entries),"no_end_date":data.until_date is None,
      "notice":"Indefinite series currently materializes 180 days only; extend it before the horizon expires."}

@app.post("/api/sessions/series/{series_id}/stop")
def stop_series(series_id:str,user:User=Depends(current_user),db:Session=Depends(db_session)):
    series=db.get(SessionSeries,series_id)
    if not series:raise HTTPException(404)
    trainer_self_or_owner(user,series.trainer_id)
    series.active=False
    now=datetime.now(timezone.utc)
    for s in db.scalars(select(ClientSession).where(ClientSession.series_id==series_id,ClientSession.status=="confirmed",ClientSession.starts_at>=now)):
        s.status="cancelled";audit_session(db,s,user,"series_stopped","Future occurrence cancelled")
    db.commit();return {"ok":True}

@app.post("/api/sessions/series/{series_id}/extend")
def extend_indefinite_series(series_id:str,user:User=Depends(current_user),db:Session=Depends(db_session)):
    """Advance an indefinite recurrence 180 days ahead, preserving edited occurrences."""
    series=db.get(SessionSeries,series_id)
    if not series:raise HTTPException(404)
    trainer_self_or_owner(user,series.trainer_id)
    if not series.active or series.until_date is not None:raise HTTPException(409,"Only active indefinite series can extend")
    anchor=series.start_date.date()
    through=series.materialized_through.date() if series.materialized_through else anchor-timedelta(days=1)
    limit=max(date.today(),anchor)+timedelta(days=180)
    to_add=[]
    d=anchor+timedelta(days=(series.weekday-anchor.weekday())%7)
    while d<=limit:
        if d>through:
            dt=datetime.combine(d,series.local_time,LOCAL_TZ)
            if dt.astimezone(timezone.utc).astimezone(LOCAL_TZ).replace(tzinfo=None)!=dt.replace(tzinfo=None):
                raise HTTPException(422,f"Nonexistent local time: {d}")
            a=dt.astimezone(timezone.utc);b=a+timedelta(minutes=series.duration_minutes)
            if not available(db,series.trainer_id,a,b) or session_conflict(db,series.trainer_id,series.lead_id,a,b):
                raise HTTPException(409,f"Conflict while extending series on {d}. Resolve it and retry.")
            to_add.append((d,a,b))
        d+=timedelta(weeks=series.interval_weeks)
    for d,a,b in to_add:
        session=ClientSession(trainer_id=series.trainer_id,lead_id=series.lead_id,series_id=series.id,
                              occurrence_date=datetime.combine(d,time.min),starts_at=a,ends_at=b)
        db.add(session);db.flush();audit_session(db,session,user,"series_extended",str(d))
    if to_add:series.materialized_through=datetime.combine(to_add[-1][0],time.min)
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,"Concurrent booking conflict")
    return {"sessions_added":len(to_add),"materialized_through":iso(series.materialized_through)}

@app.get("/api/sessions/series")
def list_series(user:User=Depends(current_user),db:Session=Depends(db_session)):
    stmt=select(SessionSeries).order_by(SessionSeries.created_at.desc())
    if user.role=="trainer":stmt=stmt.where(SessionSeries.trainer_id==user.id)
    else:owner_only(user)
    return [{"id":s.id,"trainer_id":s.trainer_id,"lead_id":s.lead_id,
             "client_name":db.get(Lead,s.lead_id).name,"active":s.active,"until_date":iso(s.until_date),
             "materialized_through":iso(s.materialized_through)} for s in db.scalars(stmt)]

# v0.2.5: schedule imports and searchable client directory
from . import imports as _schedule_imports  # noqa: F401


# Owner Operations — intentionally small: list, add, complete/reopen, and notes.
OWNER_BUSINESSES = {"pale_horse", "crucible_wellness"}
OWNER_KINDS = {"callback", "follow_up", "supplier", "admin", "other"}

class OwnerTaskCreate(BaseModel):
    business: Literal["pale_horse", "crucible_wellness"]
    kind: Literal["callback", "follow_up", "supplier", "admin", "other"] = "callback"
    title: str = Field(min_length=2, max_length=180)
    contact_name: str = Field(default="", max_length=150)
    contact_email: str = Field(default="", max_length=255)
    contact_phone: str = Field(default="", max_length=50)
    due_at: datetime | None = None
    notes: str = Field(default="", max_length=3000)

class OwnerTaskStatus(BaseModel):
    status: Literal["open", "done"]

class OwnerTaskNote(BaseModel):
    note: str = Field(min_length=1, max_length=2000)

def owner_task_dict(task: OwnerTask):
    return {"id": task.id, "business": task.business, "kind": task.kind,
            "title": task.title, "contact_name": task.contact_name,
            "contact_email": task.contact_email, "contact_phone": task.contact_phone,
            "due_at": iso(task.due_at) if task.due_at else None, "notes": task.notes,
            "status": task.status, "completed_at": iso(task.completed_at) if task.completed_at else None,
            "archived": (task.status == "done" and task.completed_at is not None and
                         task.completed_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc) - timedelta(days=7)),
            "created_at": iso(task.created_at),
            "updated_at": iso(task.updated_at)}

def owner_event(db: Session, task: OwnerTask, user: User, action: str, detail: str = ""):
    db.add(OwnerTaskEvent(task_id=task.id, actor_id=user.id, action=action, detail=detail))

@app.get("/api/owner/tasks")
def owner_tasks(user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    return [owner_task_dict(t) for t in db.scalars(select(OwnerTask).order_by(OwnerTask.created_at.desc())).all()]

@app.post("/api/owner/tasks", status_code=201)
def owner_add_task(payload: OwnerTaskCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    task = OwnerTask(**{**payload.model_dump(), "title": payload.title.strip()}, created_by_id=user.id)
    db.add(task)
    db.flush()
    owner_event(db, task, user, "created", f"{task.business}: {task.title}")
    db.commit()
    db.refresh(task)
    return owner_task_dict(task)

@app.post("/api/owner/tasks/{task_id}/status")
def owner_set_task_status(task_id: str, payload: OwnerTaskStatus, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    task = db.get(OwnerTask, task_id)
    if task is None: raise HTTPException(404, "Task not found")
    if task.status != payload.status:
        task.status = payload.status
        task.completed_at = datetime.now(timezone.utc) if payload.status == "done" else None
        task.updated_at = datetime.now(timezone.utc)
        owner_event(db, task, user, "status", payload.status)
        db.commit()
    return owner_task_dict(task)

@app.post("/api/owner/tasks/{task_id}/notes")
def owner_add_task_note(task_id: str, payload: OwnerTaskNote, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    task = db.get(OwnerTask, task_id)
    if task is None: raise HTTPException(404, "Task not found")
    owner_event(db, task, user, "note", payload.note.strip())
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}

@app.get("/api/owner/tasks/{task_id}/history")
def owner_task_history(task_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    if db.get(OwnerTask, task_id) is None: raise HTTPException(404, "Task not found")
    events = db.scalars(select(OwnerTaskEvent).where(OwnerTaskEvent.task_id == task_id).order_by(OwnerTaskEvent.created_at.desc())).all()
    return [{"id": event.id, "action": event.action, "detail": event.detail,
             "created_at": iso(event.created_at),
             "actor": (db.get(User, event.actor_id).name if db.get(User, event.actor_id) else "Owner")}
            for event in events]


# v0.2.7 — Gmail-to-task integration. Explicit consent; no unattended inbox imports.
# A Google Cloud OAuth web client and secure token encryption key are required.
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_ACCOUNT = os.environ.get("GOOGLE_ALLOWED_EMAIL", "noah@palehorsebarbell.com").lower()

def gmail_owner(user: User):
    owner_only(user)
    if user.email.lower() != GMAIL_ACCOUNT:
        raise HTTPException(403, "Only the designated Gmail account owner may connect or import emails")

def gmail_config():
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "")
    key = os.environ.get("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
    if not all([client_id, client_secret, redirect_uri, key]):
        raise HTTPException(503, "Google Workspace OAuth is not configured. See README-v0.2.7.md")
    try:
        cipher = Fernet(key.encode())
    except Exception:
        raise HTTPException(503, "Invalid Google token encryption key")
    return client_id, client_secret, redirect_uri, cipher

@app.get("/api/owner/gmail/status")
def owner_gmail_status(user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    account_owner = user.email.lower() == GMAIL_ACCOUNT
    connected = db.get(OwnerGmailConnection, user.id) if account_owner else None
    return {"connected": bool(connected), "account": GMAIL_ACCOUNT, "can_connect": account_owner,
            "configured": bool(os.environ.get("GOOGLE_OAUTH_CLIENT_ID") and os.environ.get("GOOGLE_TOKEN_ENCRYPTION_KEY"))}

@app.get("/api/owner/gmail/connect")
def owner_gmail_connect(user: User = Depends(current_user)):
    gmail_owner(user)
    client_id, _, redirect_uri, _ = gmail_config()
    nonce = secrets.token_urlsafe(24)
    state = jwt.encode({"sub": user.id, "nonce": nonce, "exp": datetime.now(timezone.utc)+timedelta(minutes=10)}, SECRET_KEY, algorithm="HS256")
    params = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": GMAIL_SCOPE, "access_type": "offline",
        "prompt": "consent", "state": state})
    result = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + params, status_code=302)
    result.set_cookie("phcrm_google_oauth_nonce", nonce, secure=os.environ.get("COOKIE_SECURE", "false").lower()=="true", httponly=True, samesite="lax", max_age=600)
    return result

@app.get("/api/owner/gmail/callback")
def owner_gmail_callback(request: Request, code: str = "", state: str = "", user: User = Depends(current_user), db: Session = Depends(db_session)):
    gmail_owner(user)
    try:
        payload = jwt.decode(state, SECRET_KEY, algorithms=["HS256"])
        if payload.get("sub") != user.id or not secrets.compare_digest(payload.get("nonce", ""), request.cookies.get("phcrm_google_oauth_nonce", "")):
            raise ValueError("OAuth state mismatch")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(403, "Google authentication state expired or invalid")
    if not code:
        raise HTTPException(400, "Google did not provide an authorization code")
    client_id, client_secret, redirect_uri, cipher = gmail_config()
    try:
        response = httpx.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id":client_id,
            "client_secret":client_secret,"redirect_uri":redirect_uri,"grant_type":"authorization_code"},timeout=15)
        response.raise_for_status()
        tokens = response.json()
        refresh = tokens.get("refresh_token")
        if not refresh: raise ValueError("Google did not return a refresh token")
        profile = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile",headers={"Authorization":"Bearer "+tokens["access_token"]},timeout=15)
        profile.raise_for_status()
        actual_email = profile.json().get("emailAddress", "").lower()
        if actual_email != GMAIL_ACCOUNT:
            raise HTTPException(403, "Connect the designated " + GMAIL_ACCOUNT + " account")
    except HTTPException: raise
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(502, "Google authorization failed. Please try again.")
    connection = db.get(OwnerGmailConnection, user.id)
    if connection is None:
        connection = OwnerGmailConnection(user_id=user.id, account_email=actual_email, encrypted_refresh_token="")
        db.add(connection)
    connection.encrypted_refresh_token = cipher.encrypt(refresh.encode()).decode()
    db.commit()
    result = RedirectResponse("/?gmail=connected", status_code=302)
    result.delete_cookie("phcrm_google_oauth_nonce")
    return result

def gmail_access_token(db: Session, user: User):
    gmail_owner(user)
    connection = db.get(OwnerGmailConnection, user.id)
    if not connection: raise HTTPException(409, "Connect Gmail first")
    client_id, client_secret, _, cipher = gmail_config()
    try:
        refresh = cipher.decrypt(connection.encrypted_refresh_token.encode()).decode()
        response = httpx.post("https://oauth2.googleapis.com/token",data={"client_id":client_id,"client_secret":client_secret,
           "refresh_token":refresh,"grant_type":"refresh_token"},timeout=15)
        response.raise_for_status()
        return response.json()["access_token"]
    except (InvalidToken, httpx.HTTPError, KeyError):
        raise HTTPException(502, "Gmail connection expired. Reconnect the account.")

@app.get("/api/owner/gmail/messages")
def owner_gmail_messages(user: User = Depends(current_user), db: Session = Depends(db_session)):
    token = gmail_access_token(db,user)
    headers = {"Authorization":"Bearer "+token}
    try:
        response = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",params={"maxResults":15,"labelIds":"INBOX"},headers=headers,timeout=15)
        response.raise_for_status()
        items=[]
        for message in response.json().get("messages",[]):
            r=httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages/"+message["id"],params={"format":"metadata","metadataHeaders":["From","Subject"]},headers=headers,timeout=15)
            r.raise_for_status()
            data=r.json()
            h={h["name"].lower():h["value"] for h in data.get("payload",{}).get("headers",[])}
            items.append({"id":data["id"],"subject":h.get("subject") or "(No subject)","sender":h.get("from","")})
        return items
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "Could not load Gmail messages")

class OwnerEmailTaskCreate(BaseModel):
    message_id: str = Field(pattern=r"^[a-zA-Z0-9]+$",min_length=4,max_length=100)
    business: Literal["pale_horse", "crucible_wellness"]
    due_at: datetime | None = None

@app.post("/api/owner/gmail/import-task", status_code=201)
def owner_gmail_import_task(payload: OwnerEmailTaskCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    token = gmail_access_token(db,user)
    try:
        response=httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages/"+payload.message_id,
            params={"format":"metadata","metadataHeaders":["From","Subject","Message-ID"]},
            headers={"Authorization":"Bearer "+token},timeout=15)
        response.raise_for_status()
        data=response.json()
        headers={h["name"].lower():h["value"] for h in data.get("payload",{}).get("headers",[])}
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "Cannot retrieve selected email")
    # Duplicate emails must not generate duplicate tasks. Message ID is not exposed to trainers.
    source_key="gmail:"+user.id+":"+payload.message_id
    existing=db.scalar(select(OwnerTaskEvent).where(OwnerTaskEvent.action=="gmail_import",OwnerTaskEvent.detail==source_key))
    if existing: raise HTTPException(409, "This email is already an owner task")
    from email.utils import parseaddr
    name,addr=parseaddr(headers.get("from",""))
    title=(headers.get("subject") or "Email follow-up").strip()[:180]
    task=OwnerTask(business=payload.business, kind="follow_up",title=title,contact_name=name[:150],contact_email=addr[:255],due_at=payload.due_at,notes="Imported from Gmail. Email content not copied.",created_by_id=user.id)
    db.add(task); db.flush()
    owner_event(db,task,user,"gmail_import",source_key)
    db.commit();db.refresh(task)
    return owner_task_dict(task)

@app.post("/api/owner/gmail/disconnect")
def owner_gmail_disconnect(user: User = Depends(current_user), db: Session = Depends(db_session)):
    gmail_owner(user)
    connection=db.get(OwnerGmailConnection,user.id)
    if connection: db.delete(connection);db.commit()
    return {"ok":True}


# -------- v0.2.8: classes and non-client blocks --------
class GymEventSlotIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    duration_minutes: int = Field(ge=15, le=240)

class GymEventIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    kind: Literal["class", "block"]
    coach_ids: list[str] = Field(min_length=1, max_length=8)
    start_date: date
    until_date: date | None = None
    slots: list[GymEventSlotIn] = Field(min_length=1, max_length=7)

class GymRosterChange(BaseModel):
    lead_id: str
    active: bool

class GymOccMove(BaseModel):
    starts_at: datetime
    ends_at: datetime

class GymOccStatus(BaseModel):
    status: Literal["confirmed", "cancelled"]

def gym_event_access(db: Session, event_id: str, actor: User):
    ev = db.get(GymEvent, event_id)
    if not ev: raise HTTPException(404, "Class or block not found")
    if actor.role not in ("owner", "admin") and not db.scalar(select(GymEventCoach.id).where(
            GymEventCoach.event_id == event_id, GymEventCoach.coach_id == actor.id,
            GymEventCoach.active == True)):
        raise HTTPException(403, "Not a coach for this event")
    return ev

def gym_event_summary(db, ev):
    coaches = db.scalars(select(GymEventCoach).where(GymEventCoach.event_id == ev.id, GymEventCoach.active == True)).all()
    members = db.scalars(select(GymEventMember).where(GymEventMember.event_id == ev.id, GymEventMember.active == True)).all()
    occurrences = db.scalars(select(GymEventOccurrence).where(GymEventOccurrence.event_id == ev.id).order_by(GymEventOccurrence.starts_at)).all()
    return {"id": ev.id, "name": ev.name, "kind": ev.kind, "active": ev.active,
            "coaches": [{"id": c.coach_id,"name": db.get(User,c.coach_id).name} for c in coaches],
            "members": [{"id":m.lead_id,"name":db.get(Lead,m.lead_id).name} for m in members],
            "occurrences": [{"id":o.id,"starts_at":iso(o.starts_at),"ends_at":iso(o.ends_at),"status":o.status} for o in occurrences]}

def gym_log(db,ev,actor,action,detail=""):
    db.add(GymEventLog(event_id=ev.id, actor_id=actor.id, action=action, detail=detail))

def generate_gym_slots(data):
    if data.until_date and data.until_date < data.start_date:
        raise HTTPException(422, "End date is before start date")
    if data.until_date and (data.until_date - data.start_date).days > 364:
        raise HTTPException(422, "Schedule up to one year at a time, then extend as needed")
    # Limit materialization to one year. Ongoing groups can be extended in later releases.
    finish = min(data.until_date or (data.start_date + timedelta(days=364)), data.start_date + timedelta(days=364))
    if finish < data.start_date: raise HTTPException(422, "Invalid date range")
    seen = set()
    result = []
    day = data.start_date
    while day <= finish:
        for slot in data.slots:
            if day.weekday() != slot.weekday: continue
            start = datetime.combine(day,slot.start_time,LOCAL_TZ).astimezone(timezone.utc)
            end = (datetime.combine(day,slot.start_time,LOCAL_TZ) + timedelta(minutes=slot.duration_minutes)).astimezone(timezone.utc)
            if end <= start: raise HTTPException(422,"Invalid session time")
            key=(start,end)
            if key in seen: raise HTTPException(422,"Duplicate class slot")
            seen.add(key); result.append(key)
        day += timedelta(days=1)
    if not result: raise HTTPException(422,"No sessions match selected days")
    # Detect overlapping slots within the same class.
    result.sort()
    if any(a[0] < b[1] and a[1] > b[0] for a,b in zip(result[1:],result[:-1])):
        raise HTTPException(422,"The selected class slots overlap")
    return result

def gym_validate(db, coach_ids, slots, except_occurrence=None):
    for cid in coach_ids:
        for start,end in slots:
            if gym_busy(db,cid,start,end,except_occurrence):
                raise HTTPException(409,f"Coach already has a class or block at {start.isoformat()}")
            if db.scalar(select(ClientSession.id).where(ClientSession.trainer_id == cid,
                     ClientSession.status == "confirmed", ClientSession.starts_at < end,
                     ClientSession.ends_at > start)):
                raise HTTPException(409,f"Coach has a client session at {start.isoformat()}")
            if db.scalar(select(Assignment.id).where(Assignment.trainer_id == cid,
                     Assignment.status == "confirmed", Assignment.starts_at < end,
                     Assignment.ends_at > start)):
                raise HTTPException(409,f"Coach has an assignment at {start.isoformat()}")

@app.get("/api/gym-events")
def list_gym_events(user:User=Depends(current_user), db:Session=Depends(db_session)):
    stmt=select(GymEvent).where(GymEvent.active == True).order_by(GymEvent.created_at.desc())
    if user.role == "trainer":
        stmt=stmt.join(GymEventCoach, GymEventCoach.event_id == GymEvent.id).where(
            GymEventCoach.coach_id == user.id, GymEventCoach.active == True)
    return [gym_event_summary(db,e) for e in db.scalars(stmt).all()]

@app.post("/api/gym-events/preview")
def preview_gym_event(data:GymEventIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    coach_ids=list(dict.fromkeys(data.coach_ids))
    if user.role == "trainer" and coach_ids != [user.id]:
        raise HTTPException(403,"Trainers can schedule only themselves; owner can assign multiple coaches")
    for cid in coach_ids:
        c=db.get(User,cid)
        if not c or c.role not in ("owner","admin","trainer"):
            raise HTTPException(422,"Invalid coach")
    slots=generate_gym_slots(data)
    gym_validate(db,coach_ids,slots)
    return {"count":len(slots),"first":iso(slots[0][0]),"last":iso(slots[-1][0]),
            "message":"No conflicts found. Availability rules still apply to individual appointments."}

@app.post("/api/gym-events",status_code=201)
def create_gym_event(data:GymEventIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    coach_ids=list(dict.fromkeys(data.coach_ids))
    if user.role == "trainer" and coach_ids != [user.id]:
        raise HTTPException(403,"Trainers can schedule only themselves")
    for cid in coach_ids:
        c=db.get(User,cid)
        if not c or c.role not in ("owner","admin","trainer"):
            raise HTTPException(422,"Invalid coach")
    slots=generate_gym_slots(data)
    # Cooperative transaction locks protect simultaneous class/block creation on PostgreSQL.
    if engine.dialect.name == "postgresql":
        for cid in sorted(coach_ids):
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),{"key":"gym-event-"+cid})
    gym_validate(db,coach_ids,slots)
    ev=GymEvent(name=data.name.strip(),kind=data.kind,created_by_id=user.id)
    db.add(ev);db.flush()
    for cid in coach_ids: db.add(GymEventCoach(event_id=ev.id,coach_id=cid))
    for slot in data.slots:
        db.add(GymEventPattern(event_id=ev.id,weekday=slot.weekday,start_time=slot.start_time,
              duration_minutes=slot.duration_minutes,materialized_through=datetime.combine(min(data.until_date or (data.start_date+timedelta(days=364)),data.start_date + timedelta(days=364)),time.min),
              end_date=datetime.combine(data.until_date,time.min) if data.until_date else None))
    for start,end in slots: db.add(GymEventOccurrence(event_id=ev.id,starts_at=start,ends_at=end))
    gym_log(db,ev,user,"created",f"{len(slots)} occurrences; {len(coach_ids)} coaches")
    db.commit()
    return gym_event_summary(db,ev)

@app.post("/api/gym-events/{event_id}/members")
def change_gym_roster(event_id:str,data:GymRosterChange,user:User=Depends(current_user),db:Session=Depends(db_session)):
    ev=gym_event_access(db,event_id,user)
    if ev.kind != "class": raise HTTPException(422,"Only classes have clients")
    lead=db.get(Lead,data.lead_id)
    if not lead or lead.stage != "converted" or (user.role == "trainer" and lead.assigned_trainer_id != user.id):
        raise HTTPException(403,"Use an approved active client")
    member=db.scalar(select(GymEventMember).where(GymEventMember.event_id == event_id,
                                                  GymEventMember.lead_id == data.lead_id))
    if data.active and not member: db.add(GymEventMember(event_id=event_id,lead_id=data.lead_id))
    elif member:
        member.active=data.active
        member.left_at=None if data.active else datetime.now(timezone.utc)
    gym_log(db,ev,user,"member_added" if data.active else "member_removed",data.lead_id)
    db.commit()
    return gym_event_summary(db,ev)

@app.post("/api/gym-events/{event_id}/occurrences/{occ_id}/status")
def gym_occurrence_status(event_id:str,occ_id:str,data:GymOccStatus,user:User=Depends(current_user),db:Session=Depends(db_session)):
    ev=gym_event_access(db,event_id,user)
    o=db.get(GymEventOccurrence,occ_id)
    if not o or o.event_id != event_id: raise HTTPException(404)
    if data.status == "confirmed" and o.status != "confirmed":
        coaches=db.scalars(select(GymEventCoach).where(GymEventCoach.event_id==event_id,GymEventCoach.active==True)).all()
        gym_validate(db,[c.coach_id for c in coaches],[(utc(o.starts_at),utc(o.ends_at))],o.id)
    o.status=data.status
    gym_log(db,ev,user,"occurrence_status",data.status+":"+occ_id)
    db.commit()
    return {"ok":True}

@app.post("/api/gym-events/{event_id}/occurrences/{occ_id}/move")
def gym_occurrence_move(event_id:str,occ_id:str,data:GymOccMove,user:User=Depends(current_user),db:Session=Depends(db_session)):
    ev=gym_event_access(db,event_id,user)
    o=db.get(GymEventOccurrence,occ_id)
    if not o or o.event_id != event_id: raise HTTPException(404)
    start,end=interval(data.starts_at,data.ends_at)
    coaches=db.scalars(select(GymEventCoach).where(GymEventCoach.event_id==event_id,GymEventCoach.active==True)).all()
    gym_validate(db,[c.coach_id for c in coaches],[(start,end)],o.id)
    before=iso(o.starts_at)
    o.starts_at=start;o.ends_at=end
    gym_log(db,ev,user,"occurrence_moved",before+" -> "+iso(start))
    db.commit()
    return {"ok":True}

@app.get("/api/gym-events/{event_id}/history")
def gym_event_history(event_id:str,user:User=Depends(current_user),db:Session=Depends(db_session)):
    gym_event_access(db,event_id,user)
    return [{"action":e.action,"detail":e.detail,"created_at":iso(e.created_at)} for e in
            db.scalars(select(GymEventLog).where(GymEventLog.event_id==event_id).order_by(GymEventLog.created_at.desc())).all()]

@app.get("/api/owner/daily-briefing")
def daily_briefing(user:User=Depends(current_user),db:Session=Depends(db_session)):
    owner_only(user)
    today=datetime.now(LOCAL_TZ).date()
    tasks=db.scalars(select(OwnerTask).where(OwnerTask.status=="open")).all()
    due=[{"id":t.id,"title":t.title,"business":t.business,"due_at":iso(t.due_at)} for t in tasks
         if t.due_at and utc(t.due_at).astimezone(LOCAL_TZ).date() <= today]
    pending=db.scalars(select(ClientOnboarding).where(ClientOnboarding.status=="pending")).all()
    assignments=db.scalars(select(Assignment).where(Assignment.status.in_(["pending","proposed"]))).all()
    return {"date":today.isoformat(),"tasks":due,"onboarding_count":len(pending),
            "assignment_count":len(assignments),"email_enabled":False,
            "email_message":"Connect and authorize Google Workspace sending before daily email delivery can be enabled."}

@app.get("/api/gym-events/coaches")
def gym_coaches(user:User=Depends(current_user),db:Session=Depends(db_session)):
    if user.role=="trainer":
        return [{"id":user.id,"name":user.name}]
    owner_only(user)
    return [{"id":u.id,"name":u.name} for u in db.scalars(
        select(User).where(User.role.in_(["owner","admin","trainer"])).order_by(User.name)).all()]

class GymCoachChange(BaseModel):
    coach_id: str
    active: bool

@app.post("/api/gym-events/{event_id}/coaches")
def change_gym_coach(event_id:str,data:GymCoachChange,user:User=Depends(current_user),db:Session=Depends(db_session)):
    owner_only(user)
    ev=gym_event_access(db,event_id,user)
    coach=db.get(User,data.coach_id)
    if not coach or coach.role not in ("trainer","owner","admin"):
        raise HTTPException(422,"Invalid coach")
    existing=db.scalar(select(GymEventCoach).where(GymEventCoach.event_id==event_id,
                                                    GymEventCoach.coach_id==data.coach_id))
    if data.active:
        slots=[(utc(o.starts_at),utc(o.ends_at)) for o in db.scalars(
            select(GymEventOccurrence).where(GymEventOccurrence.event_id==event_id,
                                              GymEventOccurrence.status=="confirmed")).all()]
        gym_validate(db,[data.coach_id],slots)
        if existing: existing.active=True
        else: db.add(GymEventCoach(event_id=event_id,coach_id=data.coach_id))
    else:
        active_coaches=db.scalars(select(GymEventCoach).where(GymEventCoach.event_id==event_id,
                                                              GymEventCoach.active==True)).all()
        if len(active_coaches)<=1 and existing and existing.active:
            raise HTTPException(422,"A class or block needs at least one coach")
        if existing: existing.active=False
    gym_log(db,ev,user,"coach_added" if data.active else "coach_removed",data.coach_id)
    db.commit()
    return gym_event_summary(db,ev)


@app.post("/api/gym-events/{event_id}/extend")
def extend_gym_event(event_id:str,user:User=Depends(current_user),db:Session=Depends(db_session)):
    ev=gym_event_access(db,event_id,user)
    patterns=db.scalars(select(GymEventPattern).where(GymEventPattern.event_id==event_id)).all()
    if not patterns: raise HTTPException(422,"This event has no weekly schedule")
    coach_ids=[c.coach_id for c in db.scalars(select(GymEventCoach).where(
        GymEventCoach.event_id==event_id,GymEventCoach.active==True)).all()]
    slots=[]
    new_marks=[]
    for rule in patterns:
        if rule.end_date and rule.materialized_through.date() >= rule.end_date.date():
            continue
        first=rule.materialized_through.date()+timedelta(days=1)
        end=min(first + timedelta(days=182),rule.end_date.date() if rule.end_date else first+timedelta(days=182))
        # Reuse normal generation and validation rather than bypassing conflict checks.
        data=GymEventIn(name=ev.name,kind=ev.kind,coach_ids=coach_ids,start_date=first,until_date=end,
                        slots=[GymEventSlotIn(weekday=rule.weekday,start_time=rule.start_time,
                                              duration_minutes=rule.duration_minutes)])
        slots += generate_gym_slots(data)
        new_marks.append((rule,end))
    if not slots: return {"added":0,"message":"Already scheduled through the end date"}
    if engine.dialect.name == "postgresql":
        for cid in sorted(coach_ids):
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),{"key":"gym-event-"+cid})
    gym_validate(db,coach_ids,slots)
    for a,b in slots: db.add(GymEventOccurrence(event_id=ev.id,starts_at=a,ends_at=b))
    for rule,day in new_marks: rule.materialized_through=datetime.combine(day,time.min)
    gym_log(db,ev,user,"extended",f"Added {len(slots)} occurrences")
    db.commit()
    return {"added":len(slots)}
