import React,{useEffect,useState} from 'react';
import {CalendarDays,House,Users,Menu,ArrowLeft,LogOut,Clock3,ChevronRight,RefreshCw,CalendarPlus} from 'lucide-react';
import Calendar from './Calendar';
import Sessions from './Sessions';
import Imports from './Imports';
import Scheduling from './Scheduling';
import Classes from './Classes';

type Trainer={id:string,name:string,email:string,role:string};
type Lead={id:string,name:string,email:string,phone:string,interest:string,stage:string,assigned_trainer_id:string|null,trainer_name:string|null,created_at:string};
type Event={id:string,kind:string,title:string,starts_at:string,ends_at:string};
type Tab='today'|'calendar'|'clients'|'more'|'sessions'|'hours'|'classes'|'imports';
const tz='America/New_York';
const displayTime=(date:string)=>new Date(date).toLocaleTimeString('en-US',{timeZone:tz,hour:'numeric',minute:'2-digit'});
const dayHeader=(date:string)=>new Date(date).toLocaleDateString('en-US',{timeZone:tz,weekday:'long',month:'short',day:'numeric'});
export default function MobileTrainer({me,leads,logout,openFull}:{me:Trainer,leads:Lead[],logout:()=>Promise<void>,openFull:()=>void}){
 const [tab,setTab]=useState<Tab>('today'),[events,setEvents]=useState<Event[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[search,setSearch]=useState('');
 useEffect(()=>{let alive=true;setBusy(true);setError('');const start=new Date();start.setHours(0,0,0,0);const end=new Date(start);end.setDate(end.getDate()+2);
 const q=new URLSearchParams({starts_at:start.toISOString(),ends_at:end.toISOString()});
 fetch('/api/calendar/events?'+q,{credentials:'include'}).then(async r=>{if(!r.ok)throw Error('Could not load sessions');return r.json()}).then((data:Event[])=>{if(alive)setEvents(data)}).catch(()=>{if(alive)setError('Schedule unavailable. Try refreshing.')}).finally(()=>{if(alive)setBusy(false)});
 return()=>{alive=false}},[me.id,refresh]);
 const today=new Date().toLocaleDateString('en-CA',{timeZone:tz});
 const current=events.filter(e=>e.kind==='confirmed'&&new Date(e.starts_at).toLocaleDateString('en-CA',{timeZone:tz})===today).sort((a,b)=>a.starts_at.localeCompare(b.starts_at));
 const entries=leads.filter(l=>(l.name+' '+l.email).toLowerCase().includes(search.trim().toLowerCase()));
 const go=(v:Tab)=>{setTab(v);window.scrollTo({top:0,behavior:'auto'})};
 return <div className="mobile-trainer">
  <header className="mt-head"><div className="mt-brand"><img src="/palehorse-logo.png" alt="Pale Horse Barbell"/><div><small>PALE HORSE · TRAINER</small><strong>{tab==='today'?'My Day':tab==='calendar'?'My Calendar':tab==='clients'?'My Clients':tab==='more'?'More':tab==='sessions'?'Client Sessions':tab==='hours'?'My Availability':tab==='classes'?'Classes & Blocks':'Clients & Imports'}</strong></div></div><button className="mt-icon" aria-label="Refresh my schedule" onClick={()=>setRefresh(x=>x+1)}><RefreshCw size={20}/></button></header>
  <main className="mt-body">
   {tab==='today'&&<><p className="mt-kicker">{dayHeader(new Date().toISOString())}</p><h1>Good day, {me.name.split(' ')[0]}.</h1><div className="mt-summary"><strong>{busy?'…':current.length}</strong><span>confirmed sessions today</span></div>{error&&<p role="alert">{error}</p>}<h2>Today's schedule</h2>{busy?<p className="mt-muted">Loading your day…</p>:current.length?current.map(e=><div className="mt-event" key={e.id}><span className="mt-when">{displayTime(e.starts_at)}</span><div><strong>{e.title||'Training session'}</strong><small>{displayTime(e.starts_at)} – {displayTime(e.ends_at)}</small></div></div>):<p className="mt-empty">Nothing confirmed for today.</p>}<button className="mt-action" onClick={()=>go('sessions')}><CalendarPlus size={20}/> Manage sessions <ChevronRight size={18}/></button><button className="mt-action" onClick={()=>go('hours')}><Clock3 size={20}/> Set my availability <ChevronRight size={18}/></button></>}
   {tab==='clients'&&<><label className="mt-search">Find a client or prospect<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search by name or email"/></label><p className="mt-muted">Your assigned records only</p>{entries.length?entries.map(l=><div className="mt-client" key={l.id}><strong>{l.name}</strong><small>{l.interest} · {l.stage}</small><div className="mt-contact">{l.phone&&<a href={'tel:'+l.phone}>Call</a>}{l.email&&<a href={'mailto:'+l.email}>Email</a>}</div></div>):<p className="mt-empty">No matching clients or prospects.</p>}<button className="mt-action" onClick={()=>go('imports')}><Users size={20}/> Client directory & imports <ChevronRight size={18}/></button></>}
   {tab==='calendar'&&<Calendar me={me} trainers={[]}/>}
   {tab==='sessions'&&<><button className="mt-back" onClick={()=>go('more')}><ArrowLeft size={17}/> Back</button><Sessions me={me} trainers={[]} leads={leads}/></>}
   {tab==='hours'&&<><button className="mt-back" onClick={()=>go('more')}><ArrowLeft size={17}/> Back</button><Scheduling me={me} trainers={[]} leads={leads}/></>}
   {tab==='classes'&&<><button className="mt-back" onClick={()=>go('more')}><ArrowLeft size={17}/> Back</button><Classes me={me} leads={leads}/></>}
   {tab==='imports'&&<><button className="mt-back" onClick={()=>go('clients')}><ArrowLeft size={17}/> Back</button><Imports me={me} trainers={[]}/></>}
   {tab==='more'&&<><p className="mt-muted">Everything else, when you need it.</p><button className="mt-action" onClick={()=>go('sessions')}><CalendarDays size={20}/> Client Sessions <ChevronRight size={18}/></button><button className="mt-action" onClick={()=>go('hours')}><Clock3 size={20}/> Availability & Assignments <ChevronRight size={18}/></button><button className="mt-action" onClick={()=>go('classes')}><Users size={20}/> Classes & Blocks <ChevronRight size={18}/></button><button className="mt-action" onClick={()=>go('imports')}><Users size={20}/> Client Imports <ChevronRight size={18}/></button><button className="mt-action" onClick={openFull}>Open full CRM <ChevronRight size={18}/></button><button className="mt-action" onClick={logout}><LogOut size={20}/> Sign out <ChevronRight size={18}/></button></>}
  </main>
  <nav className="mt-nav" aria-label="Trainer mobile navigation">{([{id:'today',label:'Today',Icon:House},{id:'calendar',label:'Calendar',Icon:CalendarDays},{id:'clients',label:'Clients',Icon:Users},{id:'more',label:'More',Icon:Menu}] as const).map(x=><button key={x.id} className={tab===x.id||(['sessions','hours','classes','imports'].includes(tab)&&x.id==='more')?'active':''} onClick={()=>go(x.id)} aria-current={tab===x.id?'page':undefined}><x.Icon size={21}/><span>{x.label}</span></button>)}</nav>
 </div>
}
