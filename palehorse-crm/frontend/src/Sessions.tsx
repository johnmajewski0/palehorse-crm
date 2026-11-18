import React,{useEffect,useState} from 'react';
type User={id:string,name:string,email:string,role:string};
type Trainer={id:string,name:string,email:string};
type Lead={id:string,name:string,assigned_trainer_id:string|null};
type Session={id:string,lead_id:string,lead_name:string,trainer_id:string,starts_at:string,ends_at:string,status:string,series_id:string|null,session_type:string};
type Onboard={id:string,trainer_name:string,client_name:string,status:string};
function csrf(){return document.cookie.split('; ').find(s=>s.startsWith('phcrm_csrf='))?.split('=')[1]||''}
async function api(path:string,method='GET',payload?:unknown){const r=await fetch('/api'+path,{method,credentials:'include',headers:{'Content-Type':'application/json',...(method==='GET'?{}:{'X-CSRF-Token':csrf()})},body:payload===undefined?undefined:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d));return d}
const toIso=(v:string)=>new Date(v).toISOString();
const fmt=(v:string)=>new Date(v).toLocaleString('en-US',{timeZone:'America/New_York',dateStyle:'medium',timeStyle:'short'});
export default function Sessions({me,trainers,leads}:{me:User,trainers:Trainer[],leads:Lead[]}){
 const owner=me.role!=='trainer';const [trainer,setTrainer]=useState(owner?(trainers[0]?.id||''):me.id),[client,setClient]=useState('');
 const [seriesList,setSeriesList]=useState<{id:string,client_name:string,active:boolean,until_date:string|null,materialized_through:string|null,trainer_id:string}[]>([]),[list,setList]=useState<Session[]>([]),[requests,setRequests]=useState<Onboard[]>([]),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [name,setName]=useState(''),[email,setEmail]=useState(''),[phone,setPhone]=useState('');
 const [start,setStart]=useState(''),[end,setEnd]=useState(''),[type,setType]=useState('Personal training');
 const [recurring,setRecurring]=useState(false),[weekday,setWeekday]=useState('0'),[clock,setClock]=useState('17:00'),[minutes,setMinutes]=useState('60'),[weeks,setWeeks]=useState('1'),[from,setFrom]=useState(''),[until,setUntil]=useState('');
 const [slots,setSlots]=useState([{weekday:0,local_time:'17:00',duration_minutes:60},{weekday:2,local_time:'17:00',duration_minutes:60}]);
 const [preview,setPreview]=useState<{total:number,conflicts:{date:string,reason:string}[]}|null>(null);
 const [clientList,setClientList]=useState<Lead[]>(leads);const [editing,setEditing]=useState<Session|null>(null),[moveStart,setMoveStart]=useState(''),[moveEnd,setMoveEnd]=useState('');
 const relevant=clientList.filter(l=>l.assigned_trainer_id===(owner?trainer:me.id));
 async function reload(){try{const d=new Date(),a=new Date(d.getTime()-30*864e5),b=new Date(d.getTime()+31*864e5);const q=new URLSearchParams({starts_at:a.toISOString(),ends_at:b.toISOString()});if(trainer)q.set('trainer_id',trainer);setList(await api('/sessions?'+q));setRequests(await api('/clients/onboarding'));setClientList(await api('/leads'));setSeriesList(await api('/sessions/series'))}catch(e){setError(String(e))}}
 useEffect(()=>{if(owner&&!trainer&&trainers.length)setTrainer(trainers[0].id)},[owner,trainer,trainers]);
 useEffect(()=>{reload()},[trainer]);
 async function action(fn:()=>Promise<unknown>){setError('');setNotice('');try{await fn();setNotice('Saved successfully');await reload()}catch(e){setError(String(e))}}
 const multiPayload=()=>({lead_id:client,trainer_id:owner?trainer:me.id,start_date:from,interval_weeks:Number(weeks),until_date:until||null,session_type:type,slots});
 const payload=()=>({lead_id:client,trainer_id:owner?trainer:me.id,start_date:from,weekday:Number(weekday),local_time:clock,duration_minutes:Number(minutes),interval_weeks:Number(weeks),until_date:until||null,session_type:type});
 return <div className="cal-page"><header><div><p className="kicker">PALE HORSE / CLIENT SESSIONS</p><h1>Client sessions<span className="accent">.</span></h1><p className="muted">Existing clients, appointments and recurring bookings. All times shown in Eastern Time.</p></div></header>
 {error&&<div className="error-banner">{error}</div>}{notice&&<p className="muted">{notice}</p>}
 <div className="panel minor" style={{padding:24,marginBottom:22}}><h2>Existing client onboarding</h2><p className="muted">Trainers can register existing clients; Noah approves ownership before any sessions are booked.</p>
 {!owner&&<form className="modal-form" onSubmit={e=>{e.preventDefault();action(async()=>{await api('/clients/onboard','POST',{name,email,phone});setName('');setEmail('');setPhone('')})}}><label>Client name<input required value={name} onChange={e=>setName(e.target.value)}/></label><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)}/></label><label>Phone<input value={phone} onChange={e=>setPhone(e.target.value)}/></label><button className="primary">SEND FOR APPROVAL</button></form>}
 {requests.filter(x=>owner||x.status==='pending').map(x=><div className="cal-sub" key={x.id}><span>{x.client_name} · {x.trainer_name} · {x.status}</span>{owner&&x.status==='pending'&&<><button className="secondary" onClick={()=>action(()=>api('/clients/onboarding/'+x.id+'/approve','POST'))}>APPROVE</button><button className="secondary" onClick={()=>action(()=>api('/clients/onboarding/'+x.id+'/reject','POST'))}>REJECT</button></>}</div>)}
 </div>
 <div className="panel minor" style={{padding:24,marginBottom:22}}><h2>Book a session</h2><div className="modal-form">
 {owner&&<label>Trainer<select value={trainer} onChange={e=>{setTrainer(e.target.value);setClient('')}}>{trainers.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>}
 <label>Approved client<select value={client} onChange={e=>setClient(e.target.value)}><option value="">Choose client</option>{relevant.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
 <label>Session type<select value={type} onChange={e=>setType(e.target.value)}><option>Personal training</option><option>Assessment</option><option>Group training</option><option>Consultation</option></select></label>
 <label><input type="checkbox" checked={recurring} onChange={e=>{setRecurring(e.target.checked);setPreview(null)}}/> Repeat this session</label>
 {!recurring?<><label>Start (local)<input type="datetime-local" value={start} onChange={e=>setStart(e.target.value)}/></label><label>End (local)<input type="datetime-local" value={end} onChange={e=>setEnd(e.target.value)}/></label><button className="primary" disabled={!client||!start||!end} onClick={()=>action(()=>api('/sessions','POST',{lead_id:client,trainer_id:owner?trainer:me.id,starts_at:toIso(start),ends_at:toIso(end),session_type:type}))}>BOOK SESSION</button></>:
 <><label>First eligible date<input type="date" value={from} onChange={e=>{setFrom(e.target.value);setPreview(null)}}/></label>
 <p className="muted">Add as many weekly sessions as needed, with different days, times, and durations.</p>
 {slots.map((slot,i)=><div className="multi-rule" key={i}>
 <label>Day<select value={slot.weekday} onChange={e=>{setSlots(v=>v.map((r,j)=>i===j?{...r,weekday:Number(e.target.value)}:r));setPreview(null)}}>{['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((day,n)=><option key={day} value={n}>{day}</option>)}</select></label>
 <label>Start time<input type="time" value={slot.local_time} onChange={e=>{setSlots(v=>v.map((r,j)=>i===j?{...r,local_time:e.target.value}:r));setPreview(null)}}/></label>
 <label>Duration (min)<input type="number" min="15" max="240" value={slot.duration_minutes} onChange={e=>{setSlots(v=>v.map((r,j)=>i===j?{...r,duration_minutes:Number(e.target.value)}:r));setPreview(null)}}/></label>
 <button className="secondary" disabled={slots.length===1} onClick={()=>{setSlots(v=>v.filter((_,j)=>j!==i));setPreview(null)}}>REMOVE</button>
 </div>)}
 <button className="secondary" disabled={slots.length>=14} onClick={()=>{setSlots(v=>[...v,{weekday:0,local_time:'17:00',duration_minutes:60}]);setPreview(null)}}>+ ADD WEEKLY SESSION</button>
 <label>Repeat every (weeks)<select value={weeks} onChange={e=>{setWeeks(e.target.value);setPreview(null)}}><option value="1">Every week</option><option value="2">Every 2 weeks</option><option value="4">Every 4 weeks</option></select></label>
 <label>End date (blank = rolling 180 days)<input type="date" value={until} onChange={e=>{setUntil(e.target.value);setPreview(null)}}/></label>
 <button className="secondary" disabled={!client||!from} onClick={async()=>{setError('');setPreview(null);try{setPreview(await api('/sessions/multi-series/preview','POST',multiPayload()))}catch(e){setError(String(e))}}}>PREVIEW ALL SESSIONS</button>
 {preview&&<div className="multi-results"><p>{preview.total} appointments checked · {preview.conflicts.length} conflicts</p>{preview.conflicts.map((x,i)=><p className="error" key={i}>{x.date}: {x.reason}</p>)}</div>}
 <button className="primary" disabled={!preview||preview.conflicts.length>0} onClick={()=>action(async()=>{const result=await api('/sessions/multi-series','POST',multiPayload());setPreview(null);setNotice(result.sessions_created+' appointments created')})}>CREATE WEEKLY TRAINING PLAN</button></>} </div></div>
 <div className="panel minor" style={{padding:24,marginBottom:22}}><h2>Recurring schedules</h2><p className="muted">Indefinite series require periodic extension; stopping a series cancels future occurrences but retains history.</p>{seriesList.filter(s=>s.active&&(!owner||s.trainer_id===trainer)).map(s=><div className="cal-sub" key={s.id}><span>{s.client_name} · Through {s.materialized_through?.slice(0,10)}</span>{!s.until_date&&<button className="secondary" onClick={()=>action(()=>api('/sessions/series/'+s.id+'/extend','POST'))}>EXTEND 180 DAYS</button>}<button className="secondary" onClick={()=>{if(confirm('Cancel all future confirmed occurrences?'))action(()=>api('/sessions/series/'+s.id+'/stop','POST'))}}>STOP SERIES</button></div>)}</div>
 <div className="panel minor" style={{padding:24}}><h2>Sessions (last 30 / next 31 days)</h2><button className="secondary" onClick={reload}>REFRESH</button>
 {list.map(s=><div className="cal-sub" key={s.id}><div><b>{s.lead_name}</b><p className="muted">{fmt(s.starts_at)} · {s.session_type} · {s.status}{s.series_id?' · Recurring':''}</p></div>{s.status==='confirmed'&&<><button className="secondary" onClick={()=>{setEditing(s);setMoveStart('');setMoveEnd('')}}>RESCHEDULE</button><button className="secondary" onClick={()=>action(()=>api('/sessions/'+s.id+'/status','POST',{status:'cancelled'}))}>CANCEL</button><button className="secondary" onClick={()=>action(()=>api('/sessions/'+s.id+'/status','POST',{status:'no_show'}))}>NO SHOW</button></>}</div>)}
 {editing&&<div className="modal-form"><h3>Reschedule {editing.lead_name}</h3><p>Moving only this occurrence. Original date retained in history.</p><label>New start<input type="datetime-local" value={moveStart} onChange={e=>setMoveStart(e.target.value)}/></label><label>New end<input type="datetime-local" value={moveEnd} onChange={e=>setMoveEnd(e.target.value)}/></label><button className="primary" disabled={!moveStart||!moveEnd} onClick={()=>action(async()=>{await api('/sessions/'+editing.id+'/reschedule','POST',{starts_at:toIso(moveStart),ends_at:toIso(moveEnd)});setEditing(null)})}>CONFIRM MOVE</button><button className="secondary" onClick={()=>setEditing(null)}>CLOSE</button></div>}
 </div></div>
}
