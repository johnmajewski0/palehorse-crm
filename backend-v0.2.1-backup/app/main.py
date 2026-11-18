"""Pale Horse CRM MVP API. Local development starter; not production hardened."""
import os
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

Base.metadata.create_all(engine)
# PostgreSQL exclusion constraint is the final arbiter of concurrent confirmed bookings.
# It also covers overlapping bookings for the same client on different trainers.
if engine.dialect.name == "postgresql":
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
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
    stage: Literal["new", "contacted", "consultation", "trial", "converted", "follow_up", "lost"] | None = None
    assigned_trainer_id: str | None = None

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

@app.get("/api/leads")
def leads(user: User = Depends(current_user), db: Session = Depends(db_session)):
    stmt = select(Lead).order_by(Lead.created_at.desc())
    if user.role == "trainer": stmt = stmt.where(Lead.assigned_trainer_id == user.id)
    return [serialize_lead(l, db) for l in db.scalars(stmt).all()]

@app.post("/api/leads")
def add_lead(payload: LeadCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owner_only(user)
    lead = Lead(**payload.model_dump()); db.add(lead); db.commit(); db.refresh(lead)
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
def gmail_status(user: User = Depends(current_user)):
    owner_only(user)
    return {"connected":False,"account":"noah@palehorsebarbell.com","message":"Google Workspace OAuth has not been configured. No Gmail data is accessed."}


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

def conflicts(db, trainer_id, lead_id, start, end, exclude_id=None):
    query = select(Assignment).where(Assignment.status == "confirmed", Assignment.starts_at < end,
                                      Assignment.ends_at > start,
                                      or_(Assignment.trainer_id == trainer_id, Assignment.lead_id == lead_id))
    if exclude_id: query = query.where(Assignment.id != exclude_id)
    return db.scalar(query) is not None

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
    sessions=[(max(utc(a.starts_at),start),min(utc(a.ends_at),end)) for a in assignments if a.status=="confirmed"]
    free=subtract_intervals(working,merge_intervals(sessions))
    items=[]
    for i,(a,b) in enumerate(free):
        items.append({"id":f"free-{trainer_id}-{i}","kind":"free","trainer_id":trainer_id,"starts_at":iso(a),"ends_at":iso(b),"title":"Available"})
    for i,(a,b) in enumerate(blocked):
        if a<b: items.append({"id":f"off-{trainer_id}-{i}","kind":"unavailable","trainer_id":trainer_id,"starts_at":iso(a),"ends_at":iso(b),"title":"Unavailable"})
    for a in assignments:
        title=(db.get(Lead,a.lead_id).name if include_details and db.get(Lead,a.lead_id) else "Training session") if a.status=="confirmed" else "Awaiting response"
        items.append({"id":a.id,"kind":a.status,"trainer_id":trainer_id,"starts_at":iso(a.starts_at),"ends_at":iso(a.ends_at),"title":title})
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
        ids=[trainer_id] if trainer_id else list(db.scalars(select(User.id).where(User.role=="trainer")))
    results=[]
    for tid in ids:
        t=require_trainer(db,tid)
        for item in build_calendar(db,tid,start,end,True):
            item["trainer_name"]=t.name
            results.append(item)
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
