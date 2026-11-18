import React,{useEffect,useState} from 'react';
import {CalendarDays,Clock3,UserRoundPlus,Users,ArrowRight,RefreshCw,CheckCircle2, Bell,ClipboardCheck} from 'lucide-react';

type User={id:string,name:string,role:string};
type Lead={id:string,name:string,stage:string};
type Trainer={id:string,name:string,email:string};
type Page='home'|'pipeline'|'scheduling'|'calendar'|'sessions'|'imports'|'owner-operations'|'classes';
type Event={id:string,kind:string,title:string,starts_at:string,trainer_name?:string};
type Approval={id:string,status:string};
type Assignment={id:string,status:string};
type Notification={id:string,read_at:string|null};
const et=(v:string)=>new Date(v).toLocaleString('en-US',{timeZone:'America/New_York',weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
export default function Home({me,leads,trainers,navigate}:{me:User,leads:Lead[],trainers:Trainer[],navigate:(page:Page)=>void}){
 const owner=me.role!=='trainer';const [events,setEvents]=useState<Event[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');const [refreshId,setRefreshId]=useState(0);const [attention,setAttention]=useState({approvals:0,assignments:0,alerts:0});const [attentionError,setAttentionError]=useState(false);
 useEffect(()=>{let alive=true;const now=new Date(),end=new Date(now.getTime()+7*86400000),q=new URLSearchParams({starts_at:now.toISOString(),ends_at:end.toISOString()});
 fetch('/api/calendar/events?'+q.toString(),{credentials:'include'}).then(async r=>{if(!r.ok)throw new Error('Calendar unavailable');return r.json()}).then((data:Event[])=>{if(alive)setEvents(data)}).catch(()=>{if(alive)setError('Upcoming sessions could not be loaded. Your calendar is still available.')}).finally(()=>{if(alive)setLoading(false)});
 return()=>{alive=false}},[me.id,refreshId]);
 useEffect(()=>{if(!owner)return;let alive=true;
  const get=async<T,>(path:string):Promise<T>=>{const r=await fetch('/api'+path,{credentials:'include'});if(!r.ok)throw Error('Could not load '+path);return r.json()};
  Promise.all([get<Approval[]>('/clients/onboarding'),get<Assignment[]>('/scheduling/assignments'),get<Notification[]>('/scheduling/notifications')])
    .then(([approvals,assignments,notifications])=>{if(alive){setAttention({
      approvals:approvals.filter(x=>x.status==='pending').length,
      assignments:assignments.filter(x=>['pending','requested','proposed'].includes(x.status)).length,
      alerts:notifications.filter(x=>!x.read_at).length});setAttentionError(false)}})
    .catch(()=>{if(alive)setAttentionError(true)});
  return()=>{alive=false};
 },[me.id,owner,refreshId]);
 const booked=events.filter(e=>e.kind==='confirmed').sort((a,b)=>new Date(a.starts_at).getTime()-new Date(b.starts_at).getTime()).slice(0,5);
 const pending=events.filter(e=>e.kind==='pending'||e.kind==='proposed').length;
 const go=(p:Page)=>navigate(p);
 return <div className="ux-home"><header><div><p className="kicker">PALE HORSE / {owner?'OWNER COMMAND CENTER':'TRAINER WORKSPACE'}</p><h1>{owner?'Gym overview':'Your training day'}<span className="accent">.</span></h1><p className="muted">{owner?'Your schedule, trainers and clients — all in one place.':'Your sessions and client tools, without the clutter.'}</p></div></header>
 <section className="ux-hero" aria-label="Quick actions"><div><p className="kicker">GET STARTED</p><h2>{owner?'What needs your attention?':'What would you like to do?'}</h2><p className="muted">Choose an action below; you can always return here using the sidebar.</p></div><div className="ux-actions">
 <button onClick={()=>go('calendar')} className="ux-action"><CalendarDays size={22}/><strong>{owner?'View all trainers':'View my calendar'}</strong><small>See upcoming sessions and free time</small><ArrowRight size={16}/></button>
 <button onClick={()=>go('classes')} className="ux-action"><Users size={22}/><strong>Classes &amp; time blocks</strong><small>Group coaching or reserve a personal block</small><ArrowRight size={16}/></button>
 <button onClick={()=>go('imports')} className="ux-action"><UserRoundPlus size={22}/><strong>{owner?'Import schedules & clients':'Import my clients'}</strong><small>Excel upload, contact directory and approvals</small><ArrowRight size={16}/></button>
 <button onClick={()=>go('scheduling')} className="ux-action"><Clock3 size={22}/><strong>{owner?'Assignments & hours':'Set my availability'}</strong><small>{owner?'Review requests and trainer availability':'Edit weekly hours, time off and requests'}</small><ArrowRight size={16}/></button>
 <button onClick={()=>go('pipeline')} className="ux-action"><Users size={22}/><strong>{owner?'Prospects':'My prospects'}</strong><small>{owner?'Manage new inquiries and follow-up':'Follow up with assigned prospects'}</small><ArrowRight size={16}/></button>
 {owner&&<button onClick={()=>go('owner-operations')} className="ux-action"><ClipboardCheck size={22}/><strong>Owner Operations</strong><small>Private callbacks and Crucible Wellness follow-ups</small><ArrowRight size={16}/></button>}
 </div></section>
 {owner&&<section className="ux-attention" aria-label="Owner action center">
   <div className="ux-attention-heading"><h2>Needs your attention</h2><button className="secondary" onClick={()=>setRefreshId(x=>x+1)}><RefreshCw size={15}/> REFRESH</button></div>
   {attentionError&&<p className="muted" role="status">Attention counts couldn't load. You can still open the management screens below.</p>}
   <div className="ux-attention-cards">
     <button className="ux-attention-card" onClick={()=>go('sessions')}><ClipboardCheck size={20}/><span><strong>Client approvals</strong><small>Review existing-client requests</small></span><b>{attentionError?'—':attention.approvals}</b><ArrowRight size={16}/></button>
     <button className="ux-attention-card" onClick={()=>go('scheduling')}><Clock3 size={20}/><span><strong>Assignment requests</strong><small>Pending trainer responses</small></span><b>{attentionError?'—':attention.assignments}</b><ArrowRight size={16}/></button>
     <button className="ux-attention-card" onClick={()=>go('scheduling')}><Bell size={20}/><span><strong>Unread notifications</strong><small>Trainer updates and changes</small></span><b>{attentionError?'—':attention.alerts}</b><ArrowRight size={16}/></button>
   </div>
 </section>}
 <div className="ux-overview"><section className="panel ux-upcoming"><div className="panel-title"><div><h2>Coming up this week</h2><p>{owner?'Confirmed sessions across the gym':'Your next confirmed sessions'} · Eastern Time</p></div><button className="secondary" onClick={()=>{setLoading(true);setError('');setRefreshId(x=>x+1)}} aria-label="Refresh upcoming sessions"><RefreshCw size={16}/> REFRESH</button></div>
 {loading?<p className="ux-message" role="status">Loading sessions…</p>:error?<p className="ux-message" role="alert">{error}</p>:booked.length?booked.map(e=><div className="ux-session" key={e.id}><span className="ux-session-mark"><CheckCircle2 size={17}/></span><div><strong>{e.title||'Training session'}</strong><small>{et(e.starts_at)}{owner&&e.trainer_name?' · '+e.trainer_name:''}</small></div></div>):<div className="ux-empty"><CalendarDays size={28}/><strong>No confirmed sessions in the next seven days</strong><p>New bookings will show up here once confirmed.</p></div>}
 <button className="ux-more" onClick={()=>go('calendar')}>OPEN CALENDAR <ArrowRight size={16}/></button></section>
 <section className="panel ux-glance"><div className="panel-title"><div><h2>At a glance</h2><p>Quick counts from your current workspace</p></div></div><div className="ux-kpi"><span>{owner?'Gym prospects':'My assigned prospects'}</span><strong>{leads.length}</strong></div><div className="ux-kpi"><span>Pending calendar requests (next 7 days)</span><strong>{loading?'—':pending}</strong></div>{owner&&<div className="ux-kpi"><span>Trainer accounts</span><strong>{trainers.length}</strong></div>}<p className="ux-glance-help">To manage existing clients and recurring training plans, use <button onClick={()=>go('sessions')}>Client sessions</button>.</p></section></div>
 </div>;
}
