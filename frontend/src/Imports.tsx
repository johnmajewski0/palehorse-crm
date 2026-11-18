import React, {useEffect, useState} from 'react';
import {Download, Upload, Search, CheckCircle, AlertTriangle} from 'lucide-react';

type User={id:string;name:string;role:string};
type Trainer={id:string;name:string;email:string};
type Client={id:string;name:string;email:string;phone:string;trainer_id:string;stage:string};
type PreviewRow={row:number;client_name?:string;day?:string;start_time?:string;sessions?:number;state:'ready'|'approval_required'|'error';message:string};
type Imported={id:string;client_name:string;state:string;detail:string};
function csrf(){return document.cookie.split('; ').find(s=>s.startsWith('phcrm_csrf='))?.split('=')[1]||''}
async function api(path:string,method='GET',body?:unknown){const r=await fetch('/api'+path,{method,credentials:'include',headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-CSRF-Token':csrf()}:{})},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.detail||'Request failed');return data;}
export default function Imports({me,trainers}:{me:User;trainers:Trainer[]}){
 const owner=me.role==='owner'||me.role==='admin';
 const [trainer,setTrainer]=useState('');const [clients,setClients]=useState<Client[]>([]);const [filter,setFilter]=useState('');
 const [file,setFile]=useState<File|null>(null);const [fileData,setFileData]=useState('');
 const [preview,setPreview]=useState<{total:number;errors:number;pending_approval:number;rows:PreviewRow[]}|null>(null);
 const [history,setHistory]=useState<Imported[]>([]);const [message,setMessage]=useState('');const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);const [editing,setEditing]=useState<Client|null>(null);
 const [email,setEmail]=useState('');const [phone,setPhone]=useState('');
 useEffect(()=>{if(owner&&trainers.length&&!trainer)setTrainer(trainers[0].id)},[owner,trainers,trainer]);
 async function refresh(){try{const [people,imports]=await Promise.all([api('/clients/directory'),api('/imports/schedule/status')]);setClients(people);setHistory(imports)}catch(e){setError(String(e))}}
 useEffect(()=>{refresh()},[]);
 const selected=owner?trainer:me.id;
 async function chooseFile(picked:File|null){setFile(picked);setFileData('');setPreview(null);setError('');setMessage('');if(!picked)return;if(!/\.(xlsx|csv)$/i.test(picked.name)){setError('Choose an .xlsx or .csv template file');return}if(picked.size>900000){setError('Maximum file size is 900 KB');return}
  const reader=new FileReader();reader.onload=()=>{const data=String(reader.result||'');setFileData(data.split(',')[1]||'')};reader.onerror=()=>setError('Could not read spreadsheet');reader.readAsDataURL(picked);
 }
 async function operation(task:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await task()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 const payload=()=>({filename:file!.name,content_base64:fileData,trainer_id:selected});
 const visible=clients.filter(c=>(!owner||c.trainer_id===selected)&&`${c.name} ${c.email} ${c.phone}`.toLowerCase().includes(filter.toLowerCase()));
 return <div className="cal-page"><header><div><p className="kicker">PALE HORSE / CLIENTS</p><h1>Clients &amp; imports<span className="accent">.</span></h1><p className="muted">Download. Fill in. Upload. Review. Done.</p></div></header>
 {error&&<div className="error-banner">{error}</div>}{message&&<div className="panel minor" style={{padding:14,marginBottom:18}}><CheckCircle size={16} style={{verticalAlign:'middle',marginRight:9}}/>{message}</div>}
 <div className="panel minor" style={{padding:24,marginBottom:22}}>
  <h2>Import a training schedule</h2><p className="muted">One row per weekly time slot. Include each client's name, email and phone. Use multiple rows for clients who train more than once a week.</p>
  {owner&&<label style={{display:'block',marginBottom:18}}>Trainer<select value={trainer} onChange={e=>{setTrainer(e.target.value);setPreview(null)}}>{trainers.map(t=><option value={t.id} key={t.id}>{t.name}</option>)}</select></label>}
  <div className="import-actions"><a className="secondary import-download" href="/palehorse-schedule-template.xlsx" download><Download size={17}/> DOWNLOAD EXCEL TEMPLATE</a>
   <label className="import-file">Upload completed Excel or CSV<input type="file" accept=".xlsx,.csv" onChange={e=>chooseFile(e.target.files?.[0]||null)}/></label>
   <button type="button" className="secondary" disabled={!fileData||!selected||busy} onClick={()=>operation(async()=>{setPreview(await api('/imports/schedule/preview','POST',payload()))})}><Upload size={16}/> PREVIEW IMPORT</button>
  </div>
  {file&&<p className="muted">Selected file: {file.name}</p>}
  {preview&&<div className="import-preview"><h3>Review before importing</h3><p className="muted">{preview.total} rows · {preview.pending_approval} need owner approval · {preview.errors} errors. No changes have been saved yet.</p>
   <div style={{overflowX:'auto'}}><table className="import-table"><thead><tr><th>Row</th><th>Client</th><th>Schedule</th><th>Sessions</th><th>Result</th></tr></thead><tbody>{preview.rows.map(r=><tr key={r.row}><td>{r.row}</td><td>{r.client_name||'—'}</td><td>{r.day||'—'} {r.start_time||''}</td><td>{r.sessions??'—'}</td><td>{r.state==='error'?<AlertTriangle size={14} style={{verticalAlign:'middle'}}/>:null} {r.message}</td></tr>)}</tbody></table></div>
   <button type="button" className="primary" disabled={!!preview.errors||!preview.total||busy} onClick={()=>operation(async()=>{const result=await api('/imports/schedule/commit','POST',{...payload(),acknowledged:true});setMessage(`${result.sessions_created} appointments scheduled. ${result.awaiting_approval} schedule row(s) waiting for Noah's approval.`);setPreview(null);setFile(null);setFileData('');await refresh()})}>CONFIRM IMPORT</button>
  </div>}
  <p className="muted" style={{marginTop:16}}>New clients require owner approval. Existing approved clients are booked immediately if there are no conflicts. Reimporting the same rows is blocked.</p>
 </div>
 <div className="panel minor" style={{padding:24,marginBottom:22}}><h2>Client directory</h2><p className="muted">Only your assigned clients and their contact details are shown to trainers.</p>
  <label className="import-search"><Search size={17}/><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Search name, email, or phone"/></label>
  {visible.length===0?<p className="muted">No approved clients found.</p>:visible.map(c=><div className="cal-sub" key={c.id}><div><strong>{c.name}</strong><p className="muted">{c.email} · {c.phone||'No phone'}</p></div><button className="secondary" onClick={()=>{setEditing(c);setEmail(c.email);setPhone(c.phone)}}>EDIT CONTACT</button></div>)}
  {editing&&<div className="modal-form"><h3>Edit {editing.name}</h3><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label><label>Phone<input value={phone} onChange={e=>setPhone(e.target.value)} required/></label><button className="primary" disabled={busy} onClick={()=>operation(async()=>{await api('/clients/directory/'+editing.id,'PATCH',{email,phone});setEditing(null);setMessage('Contact updated, with an audit entry.');await refresh()})}>SAVE CONTACT</button><button className="secondary" onClick={()=>setEditing(null)}>CANCEL</button></div>}
 </div>
 <div className="panel minor" style={{padding:24}}><h2>Recent imports</h2><button className="secondary" onClick={refresh}>REFRESH</button>{history.slice(0,35).map(i=><div className="cal-sub" key={i.id}><span>{i.client_name}</span><span className="muted">{i.state.replaceAll('_',' ')} {i.detail&&`· ${i.detail}`}</span></div>)}{!history.length&&<p className="muted">No imports yet.</p>}</div>
 </div>;
}
