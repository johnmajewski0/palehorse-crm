"""v0.2.5 minimal schedule import / client directory.

XLSX and CSV use the same fixed header template. Preview has no side effects.
Pending client relationships are never assigned to a trainer until owner approval.
"""
import base64
import calendar
import csv
import hashlib
import io
import re
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, select, or_
from sqlalchemy.exc import IntegrityError

from .main import (Base, engine, app, db_session, current_user, User, Lead, ClientOnboarding,
    ClientSession, SessionSeries, Activity, client_access, session_conflict,
    occurrences, SeriesIn, LOCAL_TZ, audit_session, trainer_self_or_owner, owner_only)

COLUMNS = ["first_name", "last_name", "email", "phone", "day", "start_time",
           "duration_minutes", "frequency", "start_date", "end_date", "session_type"]
DAYS = {name.lower(): idx for idx, name in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}
FREQUENCIES = {"weekly": 1, "biweekly": 2, "every 2 weeks": 2,
               "every 3 weeks": 3, "every 4 weeks": 4,
               "one-time": 0, "monthly": 0}
SPECIAL_FREQUENCIES = {"one-time", "monthly"}

class ScheduleImportRow(Base):
    __tablename__ = "crm_schedule_import_rows"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    trainer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False, index=True)
    source_key = Column(String(64), unique=True, nullable=False)
    payload = Column(Text, nullable=False)
    state = Column(String(24), nullable=False)  # pending_approval / imported / needs_attention
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=True)

Base.metadata.create_all(engine, tables=[ScheduleImportRow.__table__])

class ImportFile(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    content_base64: str = Field(min_length=1, max_length=1500000)
    trainer_id: str | None = None

class ImportCommit(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    content_base64: str = Field(min_length=1, max_length=1500000)
    trainer_id: str | None = None
    acknowledged: bool = True

class ContactUpdate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    phone: str = Field(min_length=3, max_length=50)


def target_trainer(user, tid, db):
    tid = tid if user.role in ('owner', 'admin') else user.id
    if not tid: raise HTTPException(422, "Choose a trainer")
    trainer_self_or_owner(user, tid)
    trainer = db.get(User, tid)
    if trainer is None or trainer.role != 'trainer': raise HTTPException(422, "Unknown trainer")
    return tid


def read_rows(data):
    try: raw = base64.b64decode(data.content_base64, validate=True)
    except Exception: raise HTTPException(422, "Invalid file encoding")
    if len(raw) > 900_000: raise HTTPException(413, "File exceeds the 900 KB import limit")
    name=data.filename.lower()
    if name.endswith('.csv'):
        try:
            decoded=raw.decode('utf-8-sig')
            rows=list(csv.reader(io.StringIO(decoded)))
        except (UnicodeError,csv.Error): raise HTTPException(422, "Upload a UTF-8 CSV")
    elif name.endswith('.xlsx'):
        from openpyxl import load_workbook
        try:
            wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
            sheet=wb['Schedule Import'] if 'Schedule Import' in wb.sheetnames else wb.active
            rows=list(sheet.iter_rows(values_only=True, max_row=502))
            wb.close()
        except Exception: raise HTTPException(422, "Invalid Excel file")
    else: raise HTTPException(422, "Use .xlsx or .csv")
    if not rows: raise HTTPException(422, "The spreadsheet is empty")
    header=[str(v or '').strip().lower().replace(' ', '_') for v in rows[0]]
    if header[:len(COLUMNS)]!=COLUMNS:
        raise HTTPException(422, "Use the Pale Horse template; columns must match the template headings")
    nonempty=[]
    for index, values in enumerate(rows[1:], 2):
        entries=list(values[:len(COLUMNS)])
        if any(v is not None and str(v).strip() for v in entries):
            nonempty.append((index, dict(zip(COLUMNS, entries))))
    if len(nonempty)>250: raise HTTPException(422, "Import at most 250 schedule rows at a time")
    return nonempty


def textval(v): return str(v or '').strip()

def normalize_date(value):
    if isinstance(value,datetime): return value.date()
    if isinstance(value,date): return value
    return date.fromisoformat(textval(value))

def normalize_time(value):
    if isinstance(value, datetime): return value.time().replace(tzinfo=None)
    if isinstance(value,time): return value.replace(tzinfo=None)
    if isinstance(value,(int,float)) and 0<=value<1:
        mins=round(value*1440)
        return time(mins//60%24,mins%60)
    s=textval(value)
    try:return time.fromisoformat(s)
    except ValueError:return datetime.strptime(s.upper(),'%I:%M %p').time()


def normalize(item):
    first=textval(item['first_name'])
    last=textval(item['last_name'])
    email=textval(item['email']).lower()
    phone=textval(item['phone'])
    if not first or not last or len(first+' '+last)>150:raise ValueError('First and last name required (150 characters max)')
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(email)>255:raise ValueError('Valid client email required')
    if not phone or len(phone)>50 or len(re.sub(r'\D','',phone))<7:raise ValueError('Valid phone required; enter as text')
    day=textval(item['day']).lower()
    if day not in DAYS:raise ValueError('Day must be Monday through Sunday')
    start=normalize_time(item['start_time'])
    duration=int(item['duration_minutes'])
    if duration<15 or duration>240:raise ValueError('Duration must be 15–240 minutes')
    frequency=textval(item['frequency']).lower()
    freq=FREQUENCIES.get(frequency)
    if freq is None:raise ValueError('Frequency must be One-time, Weekly, Biweekly, Every 3 Weeks, Every 4 Weeks, or Monthly')
    first_day=normalize_date(item['start_date'])
    if frequency in SPECIAL_FREQUENCIES and DAYS[day]!=first_day.weekday():
        raise ValueError('For One-time and Monthly, Training Day must match Schedule Start Date')
    end=normalize_date(item['end_date']) if textval(item['end_date']) else None
    if end and (end<first_day or end>first_day+timedelta(days=366)):
        raise ValueError('End date must be after start date and within one year; leave blank for rolling 180 days')
    kind=textval(item.get('session_type')) or 'Personal training'
    if len(kind)>80:raise ValueError('Session type is too long')
    return dict(first_name=first,last_name=last,email=email,phone=phone,weekday=DAYS[day],
                day=day.capitalize(),start_time=start.strftime('%H:%M'),duration_minutes=duration,
                frequency=frequency,interval_weeks=freq,start_date=first_day.isoformat(),end_date=end.isoformat() if end else None,
                session_type=kind)


def match_client(db,row,trainer_id):
    matches=db.scalars(select(Lead).where(Lead.email==row['email']).limit(3)).all()
    if len(matches)>1:return None,'Multiple clients with this email; owner must resolve'
    if matches:
        client=matches[0]
        if client.assigned_trainer_id not in (None,trainer_id):return None,'Client is assigned to another trainer'
        if client.name.strip().casefold()!=f"{row['first_name']} {row['last_name']}".casefold():
            return None,'Email matches another client name; review before import'
        if client.phone and re.sub(r'\D','',client.phone)!=re.sub(r'\D','',row['phone']):
            return None,'Phone differs from existing contact; review before import'
        return client,None
    # A matching phone with a different email is uncertain, not a safe automatic merge.
    phone_digits=re.sub(r'\D','',row['phone'])
    if phone_digits:
        for candidate in db.scalars(select(Lead).where(Lead.phone!='')).all():
            if re.sub(r'\D','',candidate.phone)==phone_digits:
                return None,'Phone belongs to a client with another email; owner review needed'
    return None,None


def source_key(tid,row):
    import json
    source={key:row[key] for key in ('email','day','start_time','duration_minutes','frequency','interval_weeks','start_date','end_date','session_type')}
    return hashlib.sha256((tid+'|'+json.dumps(source,sort_keys=True)).encode()).hexdigest()


def proposed_occurrences(row,lead_id,tid):
    # Calendar-month recurrence and one-time appointments are materialized as individual
    # audited sessions. Weekly series continue to use the existing recurring engine.
    frequency=row.get('frequency', 'weekly')
    if frequency in SPECIAL_FREQUENCIES:
        first=date.fromisoformat(row['start_date'])
        limit=date.fromisoformat(row['end_date']) if row['end_date'] else first+timedelta(days=180)
        days=[]
        if frequency=='one-time':
            days=[first]
        else:
            year,month=first.year,first.month
            while True:
                # A Jan 31 series goes to Feb 28/29, then Mar 31: stable month anchor.
                target=date(year,month,min(first.day,calendar.monthrange(year,month)[1]))
                if target>limit:break
                days.append(target)
                month+=1
                if month==13:year,month=year+1,1
        starts=time.fromisoformat(row['start_time'])
        result=[]
        for day in days:
            local_dt=datetime.combine(day,starts,LOCAL_TZ)
            if local_dt.astimezone(timezone.utc).astimezone(LOCAL_TZ).replace(tzinfo=None)!=local_dt.replace(tzinfo=None):
                raise ValueError(f'Nonexistent local time on {day}')
            start=local_dt.astimezone(timezone.utc)
            result.append((day,start,start+timedelta(minutes=row['duration_minutes'])))
        return None,result
    rule=SeriesIn(lead_id=lead_id,trainer_id=tid,start_date=date.fromisoformat(row['start_date']),
                  weekday=row['weekday'],local_time=time.fromisoformat(row['start_time']),
                  duration_minutes=row['duration_minutes'],interval_weeks=row['interval_weeks'],
                  until_date=date.fromisoformat(row['end_date']) if row['end_date'] else None,
                  session_type=row['session_type'])
    return rule,list(occurrences(rule))


def assess(data,user,db):
    tid=target_trainer(user,data.trainer_id,db)
    parsed=read_rows(data)
    output=[]
    pending=[]
    seen_keys=set()
    for number,raw in parsed:
        try:
            row=normalize(raw)
            key=source_key(tid,row)
            if key in seen_keys:raise ValueError('Duplicate spreadsheet row')
            seen_keys.add(key)
            existing=db.scalar(select(ScheduleImportRow.id).where(ScheduleImportRow.source_key==key))
            if existing:raise ValueError('Already imported or awaiting approval')
            lead,err=match_client(db,row,tid)
            if err:raise ValueError(err)
            row['client_name']=row['first_name']+' '+row['last_name']
            row['source_key']=key
            row['existing_lead_id']=lead.id if lead else None
            row['state']='ready' if lead and lead.assigned_trainer_id==tid else 'approval_required'
            # For a new or unassigned client, scheduling is deferred until approval.
            _,occ=proposed_occurrences(row,lead.id if lead else 'pending',tid)
            if not occ:raise ValueError('No sessions fall inside selected dates')
            row['sessions']=len(occ)
            for day,start,end in occ:
                if lead and lead.assigned_trainer_id==tid and session_conflict(db,tid,lead.id,start,end):
                    raise ValueError(f'Conflicts with existing appointment on {day}')
                # Reject overlaps among rows in this upload (same trainer even for different clients).
                if any(start<other_end and end>other_start for other_start,other_end in pending):
                    raise ValueError(f'Overlapping imported sessions on {day}')
            pending.extend((start,end) for _,start,end in occ)
            output.append({'row':number,'state':row['state'],'message':'Ready to book' if row['state']=='ready' else 'Client needs owner approval',**row})
        except (ValueError,TypeError,HTTPException) as exc:
            output.append({'row':number,'state':'error','message':str(exc.detail if isinstance(exc,HTTPException) else exc)})
    return tid,output


def materialize(db, item, actor):
    """Create a series + occurrences, preserving the pending import on conflict."""
    import json
    row=json.loads(item.payload)
    rule,occ=proposed_occurrences(row,item.lead_id,item.trainer_id)
    if not occ:
        item.state='needs_attention';item.detail='No sessions to schedule';return False
    for day,start,end in occ:
        if session_conflict(db,item.trainer_id,item.lead_id,start,end):
            item.state='needs_attention';item.detail=f'Conflict on {day}; schedule manually';return False
    series=None
    if rule is not None:
        series=SessionSeries(trainer_id=item.trainer_id,lead_id=item.lead_id,weekday=rule.weekday,
            local_time=rule.local_time,duration_minutes=rule.duration_minutes,interval_weeks=rule.interval_weeks,
            start_date=datetime.combine(rule.start_date,time.min),
            until_date=datetime.combine(rule.until_date,time.min) if rule.until_date else None,
            materialized_through=datetime.combine(occ[-1][0],time.min))
        db.add(series);db.flush()
    for day,start,end in occ:
        session=ClientSession(trainer_id=item.trainer_id,lead_id=item.lead_id,series_id=series.id if series else None,
            occurrence_date=datetime.combine(day,time.min),starts_at=start,ends_at=end,
            session_type=row['session_type'])
        db.add(session);db.flush();audit_session(db,session,actor,'imported_from_template',f'Import row {item.id}')
    item.state='imported';item.applied_at=datetime.now(timezone.utc)
    item.detail=f'{len(occ)} sessions imported'
    return True


def activate_approved_client(db, lead_id, actor):
    items=db.scalars(select(ScheduleImportRow).where(ScheduleImportRow.lead_id==lead_id,
        ScheduleImportRow.state=='pending_approval').order_by(ScheduleImportRow.created_at)).all()
    for item in items:
        try:
            with db.begin_nested():materialize(db,item,actor)
        except IntegrityError:
            item.state='needs_attention';item.detail='Concurrent booking conflict; schedule manually'


@app.post('/api/imports/schedule/preview')
def preview_schedule(data:ImportFile,user:User=Depends(current_user),db=Depends(db_session)):
    tid,rows=assess(data,user,db)
    return {'trainer_id':tid,'total':len(rows),'errors':sum(r['state']=='error' for r in rows),
            'pending_approval':sum(r['state']=='approval_required' for r in rows),'rows':rows}

@app.post('/api/imports/schedule/commit')
def commit_schedule(data:ImportCommit,user:User=Depends(current_user),db=Depends(db_session)):
    if not data.acknowledged:raise HTTPException(422,'Preview and confirm the import')
    tid,rows=assess(data,user,db)
    if not rows:raise HTTPException(422,'No rows to import')
    if any(r['state']=='error' for r in rows):raise HTTPException(409,'Fix preview errors before importing; no changes saved')
    import json
    results={'scheduled':0,'awaiting_approval':0,'sessions_created':0}
    # Keep all rows atomic; SQL-level exclusion still protects concurrent confirmation.
    try:
        for row in rows:
            lead=db.get(Lead,row['existing_lead_id']) if row['existing_lead_id'] else None
            if not lead:
                # Reuse a new/pending client created earlier in this same transaction.
                lead=db.scalar(select(Lead).where(Lead.email==row['email']))
                if not lead:
                    lead=Lead(name=row['client_name'],email=row['email'],phone=row['phone'],stage='converted')
                    db.add(lead);db.flush()
            state='pending_approval' if lead.assigned_trainer_id!=tid else 'ready'
            if state=='pending_approval':
                has_request=db.scalar(select(ClientOnboarding.id).where(ClientOnboarding.lead_id==lead.id,
                    ClientOnboarding.trainer_id==tid,ClientOnboarding.status=='pending'))
                if not has_request:db.add(ClientOnboarding(lead_id=lead.id,trainer_id=tid))
            item=ScheduleImportRow(trainer_id=tid,created_by_id=user.id,lead_id=lead.id,
                source_key=row['source_key'],payload=json.dumps({k:row[k] for k in ('email','day','weekday','start_time','duration_minutes','interval_weeks','start_date','end_date','session_type')}),
                state=state)
            db.add(item);db.flush()
            if state=='ready':
                if not materialize(db,item,user):raise HTTPException(409,item.detail)
                results['scheduled']+=1;results['sessions_created']+=row['sessions']
            else:results['awaiting_approval']+=1
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'A concurrent import or booking conflict occurred; preview again')
    except HTTPException:
        db.rollback();raise
    return results

@app.get('/api/imports/schedule/status')
def import_status(user:User=Depends(current_user),db=Depends(db_session)):
    query=select(ScheduleImportRow).order_by(ScheduleImportRow.created_at.desc()).limit(200)
    if user.role=='trainer':query=query.where(ScheduleImportRow.trainer_id==user.id)
    result=[]
    for row in db.scalars(query):
        lead=db.get(Lead,row.lead_id)
        result.append({'id':row.id,'client_name':lead.name if lead else 'Unknown','state':row.state,
                       'detail':row.detail,'created_at':row.created_at.isoformat()})
    return result

@app.get('/api/clients/directory')
def clients_directory(user:User=Depends(current_user),db=Depends(db_session)):
    stmt=select(Lead).where(Lead.assigned_trainer_id.is_not(None)).order_by(Lead.name)
    if user.role=='trainer':stmt=stmt.where(Lead.assigned_trainer_id==user.id)
    result=[]
    for lead in db.scalars(stmt):
        result.append({'id':lead.id,'name':lead.name,'email':lead.email,'phone':lead.phone,
                       'trainer_id':lead.assigned_trainer_id,'stage':lead.stage})
    return result

@app.patch('/api/clients/directory/{lead_id}')
def update_client_contact(lead_id:str,data:ContactUpdate,user:User=Depends(current_user),db=Depends(db_session)):
    lead=db.get(Lead,lead_id)
    if not lead or not lead.assigned_trainer_id:raise HTTPException(404,'Active client not found')
    trainer_self_or_owner(user,lead.assigned_trainer_id)
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',data.email.strip()):raise HTTPException(422,'Valid email required')
    other=db.scalar(select(Lead.id).where(Lead.email==data.email.strip().lower(),Lead.id!=lead.id))
    if other:raise HTTPException(409,'Email already belongs to another client')
    old=f'email:{lead.email}; phone:{lead.phone}'
    lead.email=data.email.strip().lower();lead.phone=data.phone.strip()
    db.add(Activity(lead_id=lead.id,actor_id=user.id,message='Contact updated from '+old))
    db.commit()
    return {'id':lead.id,'name':lead.name,'email':lead.email,'phone':lead.phone}
