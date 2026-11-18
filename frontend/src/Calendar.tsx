import React,{useEffect,useState} from 'react';
import {CalendarDays,ChevronLeft,ChevronRight,Download,Link2,RotateCcw,Copy} from 'lucide-react';
type User={id:string,name:string,email:string,role:string};
type Trainer={id:string,name:string,email:string};
type Event={id:string,kind:string,trainer_id:string,trainer_name:string,starts_at:string,ends_at:string,title:string};
function csrf(){return document.cookie.split('; ').find(s=>s.startsWith('phcrm_csrf='))?.split('=')[1]||''}
async function api(path:string,method='GET'){const r=await fetch('/api'+path,{method,credentials:'include',headers:method==='GET'?{}:{'X-CSRF-Token':csrf()}});const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'Request failed');return d}
const fmt=(d:Date)=>d.toLocaleDateString('en-US',{month:'short',day:'numeric'});
const local=(value:string)=>new Date(value).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',timeZone:'America/New_York'});
const daykey=(d:Date)=>d.toLocaleDateString('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'});
function monday(d:Date){const v=new Date(d);v.setHours(12,0,0,0);v.setDate(v.getDate()-((v.getDay()+6)%7));return v}
export default function Calendar({me,trainers}:{me:User,trainers:Trainer[]}){
 const owner=me.role!=='trainer';const [scope,setScope]=useState(owner?'all':me.id),[mode,setMode]=useState<'day'|'week'|'month'>('week');
 const [cursor,setCursor]=useState(new Date()),[events,setEvents]=useState<Event[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const [subscriptions,setSubscriptions]=useState<{id:string,created_at:string}[]>([]),[newUrl,setNewUrl]=useState('');
 const range=(()=>{let start:Date,end:Date;if(mode==='day'){start=new Date(cursor);start.setHours(0,0,0,0);end=new Date(start);end.setDate(end.getDate()+1)}else if(mode==='week'){start=monday(cursor);start.setHours(0,0,0,0);end=new Date(start);end.setDate(end.getDate()+7)}else{start=new Date(cursor.getFullYear(),cursor.getMonth(),1);end=new Date(cursor.getFullYear(),cursor.getMonth()+1,1)}return {start,end}})();
 const key=range.start.toISOString()+'-'+range.end.toISOString()+'-'+scope;
 async function refresh(){setLoading(true);setError('');try{const q=new URLSearchParams({starts_at:range.start.toISOString(),ends_at:range.end.toISOString()});if(scope!=='all')q.set('trainer_id',scope);setEvents(await api('/calendar/events?'+q.toString()))}catch(e){setError(String(e))}finally{setLoading(false)}}
 useEffect(()=>{refresh()},[key]);
 useEffect(()=>{api('/calendar/subscriptions').then(setSubscriptions).catch(()=>{})},[]);
 function move(n:number){const d=new Date(cursor);if(mode==='day')d.setDate(d.getDate()+n);else if(mode==='week')d.setDate(d.getDate()+n*7);else d.setMonth(d.getMonth()+n);setCursor(d)}
 async function subscribe(){try{const r=await api('/calendar/subscription','POST');setNewUrl(window.location.origin+r.path);setSubscriptions(await api('/calendar/subscriptions'))}catch(e){setError(String(e))}}
 async function revoke(id:string){if(!confirm('Revoke this calendar link? Google Calendar will stop receiving updates from it.'))return;try{await api('/calendar/subscriptions/'+id+'/revoke','POST');setSubscriptions(await api('/calendar/subscriptions'));setNewUrl('')}catch(e){setError(String(e))}}
 const days:Date[]=[];for(let d=new Date(range.start);d<range.end;d.setDate(d.getDate()+1))days.push(new Date(d));
 const scheduleForDay=(date:Date)=>events.filter(e=>daykey(new Date(e.starts_at))===daykey(date));
 const title=(mode==='month'?cursor.toLocaleDateString('en-US',{month:'long',year:'numeric'}):fmt(range.start)+' – '+fmt(new Date(range.end.getTime()-86400000)));
 return <div className="cal-page"><header><div><p className="kicker">COMMAND CENTER / {owner?'MASTER CALENDAR':'PERSONAL CALENDAR'}</p><h1>{owner?'Master calendar':'My calendar'}<span className="accent">.</span></h1><p className="muted">Availability, pending requests and confirmed training sessions · Eastern Time</p></div></header>
 <div className="cal-toolbar"><div className="cal-controls"><button className="secondary" onClick={()=>move(-1)} aria-label="Previous"><ChevronLeft size={18}/></button><button className="secondary" onClick={()=>setCursor(new Date())}>TODAY</button><button className="secondary" onClick={()=>move(1)} aria-label="Next"><ChevronRight size={18}/></button><strong>{title}</strong></div><div className="cal-controls">{owner&&<select aria-label="Trainer filter" value={scope} onChange={e=>setScope(e.target.value)}><option value="all">All trainers</option>{trainers.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select>}<select aria-label="Calendar view" value={mode} onChange={e=>setMode(e.target.value as 'day'|'week'|'month')}><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option></select><button className="secondary" onClick={refresh} aria-label="Refresh"><RotateCcw size={16}/></button></div></div>
 <div className="cal-legend"><span><i className="legend-free"/> Available</span><span><i className="legend-confirmed"/> Confirmed</span><span><i className="legend-pending"/> Pending / proposed</span><span><i className="legend-unavailable"/> Unavailable</span></div>
 {error&&<p className="error-banner">{error}</p>}{loading&&<p className="muted">Updating calendar…</p>}
 <div className={'cal-grid '+(mode==='day'?'cal-one':mode==='month'?'cal-month':'')}>
 {days.map(d=><div className="cal-day" key={d.toISOString()}><div className="cal-day-head"><strong>{d.toLocaleDateString('en-US',{weekday:'short',timeZone:'America/New_York'})}</strong><span>{fmt(d)}</span></div><div className="cal-day-body">{scheduleForDay(d).map(e=><div className={'cal-event event-'+e.kind} key={e.id+'-'+e.trainer_id} title={`${e.trainer_name} · ${e.title}`}><b>{local(e.starts_at)}–{local(e.ends_at)}</b><span>{e.title}</span>{owner&&<small>{e.trainer_name}</small>}</div>)}{!scheduleForDay(d).length&&<span className="cal-empty">No entries</span>}</div></div>)}
 </div>
 <div className="panel cal-export"><div className="panel-title"><div><h2>Calendar exports</h2><p>Your own read-only calendar (including owners who coach). Confirmed times only; no client identities.</p></div><CalendarDays size={22}/></div><div className="cal-export-actions"><a className="secondary cal-link" href="/api/calendar/export.ics"><Download size={16}/> DOWNLOAD .ICS</a><button className="secondary" onClick={subscribe}><Link2 size={16}/> CREATE PRIVATE SUBSCRIPTION</button></div>
 {newUrl&&<div className="cal-secret"><p><b>New private subscription URL — copy it now.</b> This URL is a credential; anyone possessing it can see your session times.</p><code>{newUrl}</code><button className="secondary" onClick={()=>navigator.clipboard.writeText(newUrl)}><Copy size={15}/> COPY LINK</button></div>}
 {!!subscriptions.length&&<div className="cal-subs"><b>Active subscriptions</b>{subscriptions.map(s=><div key={s.id} className="cal-sub"><span>Created {new Date(s.created_at).toLocaleDateString()}</span><button className="secondary" onClick={()=>revoke(s.id)}>REVOKE</button></div>)}</div>}
 <p className="fine">Google Calendar (on a computer): Other calendars → + → From URL. Apple Calendar on Mac: File → New Calendar Subscription; on iPhone: Calendars → Add Calendar → Add Subscription Calendar. Use the private link above. Subscriptions require a public HTTPS address after deployment: localhost will not work from Google or Apple servers. Refresh timing is controlled by each provider; revoked links may remain cached.</p></div>
 </div>
}
