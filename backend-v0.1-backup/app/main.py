"""Pale Horse CRM MVP API. Local development starter; not production hardened."""
import os
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Text, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
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

Base.metadata.create_all(engine)
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
        owner_only(user)
        if payload.assigned_trainer_id:
            t = db.get(User, payload.assigned_trainer_id)
            if not t or t.role != "trainer": raise HTTPException(400, "Unknown trainer")
        lead.assigned_trainer_id = payload.assigned_trainer_id
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
