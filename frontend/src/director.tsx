import React, {useEffect, useState} from 'react';

// Director console: pipelines, agents and the error journal for the session owner.
type Diagnostic = {kind:string;message:string;file?:string;line?:number};
type Stage = {name:string;agent:string;state:string;job_id?:string;attempts?:number;error?:string;diagnostics?:Diagnostic[]};
export type Pipeline = {pipeline_id:string;pipeline:string;project_id:string;state:string;progress:string;current_stage:string;current_agent:string;stages:Stage[];failure?:{error?:string;category?:string;next_action?:string;retryable?:boolean};result?:Record<string,unknown>;next_tools?:string[];error?:string};
type Listed = {pipeline_id:string;pipeline:string;project_id:string;state:string;current_stage:string;current_agent:string;created_at:string};
type Agent = {id:string;name:string;specialty:string;status:string;stages:string[];active_tasks:{pipeline_id:string;stage:string;project_id:string}[]};
type ErrorEntry = {error_id:string;time:string;project_id:string;stage:string;agent:string;error:string;category:string;next_action:string;diagnostics:Diagnostic[]};
type Catalog = {pipelines:Record<string,{description:string;requires_changeset:boolean}>;build_enabled_projects:string[]};
type Check = {path:string;code:string;severity:string;line?:number;message:string};
export type Changeset = {error?:string;file_count?:number;files?:{path:string;diff:string;diff_truncated:boolean}[];verification?:{verdict:string;checks:Check[]}};
export type Plan = {error?:string;description?:string;stages?:{name:string;agent:string;description:string}[]};

const STATE:Record<string,string>={running:'выполняется',completed:'завершён',failed:'ошибка',cancelled:'отменён',pending:'ожидает'};
const AGENT:Record<string,string>={director:'AI Director',developer:'Разработчик',tester:'Тестировщик',devops:'DevOps',artist:'3D / Godot'};
const VERDICT:Record<string,string>={pass:'замечаний нет',warn:'есть предупреждения',block:'заблокировано проверкой'};
const api=async(path:string,method='GET',body?:unknown)=>{
 const r=await fetch('/nexusai/api/director/'+path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});
 if(!r.ok)throw Error('HTTP '+r.status);
 return r.json();
};

function Diagnostics({items}:{items?:Diagnostic[]}){
 if(!items?.length)return null;
 return <ul className="director-diagnostics">{items.map((d,i)=><li key={i}>{d.file?<code>{d.file}{d.line?':'+d.line:''}</code>:null} {d.message}</li>)}</ul>;
}

export function PlanView({plan}:{plan:Plan}){
 if(plan.error)return <p className="error">План недоступен: {plan.error}</p>;
 return <><p className="hint">{plan.description}</p><ol className="director-stages">{plan.stages?.map(s=><li key={s.name}><strong>{s.description}</strong><small>{AGENT[s.agent]||s.agent} · {s.name}</small></li>)}</ol></>;
}

export function ChangesetView({changeset}:{changeset:Changeset}){
 if(changeset.error)return <p className="error">Набор изменений устарел или недоступен: {changeset.error}</p>;
 const verdict=changeset.verification?.verdict||'';
 return <div className="director-changeset"><p><strong>Изменяемых файлов:</strong> {changeset.file_count} · <strong>Проверка:</strong> <span className={'verdict-'+verdict}>{VERDICT[verdict]||verdict}</span></p>
  {changeset.verification?.checks.length?<ul className="director-diagnostics">{changeset.verification.checks.map((c,i)=><li key={i}><code>{c.path}{c.line?':'+c.line:''}</code> {c.message}</li>)}</ul>:null}
  {changeset.files?.map(f=><details key={f.path} open><summary>{f.path}</summary><pre className="diff">{f.diff}{f.diff_truncated?'\n… сравнение сокращено':''}</pre></details>)}
  <p className="hint">Изменения применяются только к изолированной копии. Исходные файлы игры остаются без изменений.</p></div>;
}

export function PipelineView({pipeline}:{pipeline:Pipeline}){
 if(pipeline.error)return <p className="error">{pipeline.error}</p>;
 return <div className="director-pipeline"><p><strong>{pipeline.pipeline}</strong> · {pipeline.project_id} · <span className={'state-'+pipeline.state}>{STATE[pipeline.state]||pipeline.state}</span> · {pipeline.progress}</p>
  <ol className="director-stages">{pipeline.stages.map(s=><li key={s.name} className={'state-'+s.state}><strong>{s.name}</strong><small>{AGENT[s.agent]||s.agent} · {STATE[s.state]||s.state}{s.attempts&&s.attempts>1?' · попытка '+s.attempts:''}</small>{s.error&&<p className="error">{s.error}</p>}<Diagnostics items={s.diagnostics}/></li>)}</ol>
  {pipeline.failure&&<p className="hint">{pipeline.failure.next_action}</p>}
  {pipeline.state==='completed'&&pipeline.result&&<pre>{JSON.stringify(pipeline.result,null,2)}</pre>}</div>;
}

export function DirectorConsole(){
 const [list,setList]=useState<Listed[]>([]);
 const [agents,setAgents]=useState<Agent[]>([]);
 const [errors,setErrors]=useState<ErrorEntry[]>([]);
 const [catalog,setCatalog]=useState<Catalog|null>(null);
 const [selected,setSelected]=useState<Pipeline|null>(null);
 const [pipeline,setPipeline]=useState('build_apk');
 const [project,setProject]=useState('');
 const [busy,setBusy]=useState(false);
 const [problem,setProblem]=useState('');
 const load=async()=>{try{const [p,a,e,c]=await Promise.all([api('pipelines'),api('agents'),api('errors?limit=10'),api('catalog')]);setList(p.pipelines);setAgents(a.agents);setErrors(e.errors);setCatalog(c);setProject(prev=>prev||c.build_enabled_projects[0]||'');setProblem('')}catch(e){setProblem(String(e))}};
 useEffect(()=>{load()},[]);
 const act=async(run:()=>Promise<Pipeline>)=>{setBusy(true);setProblem('');try{const r=await run();if(r.error&&!r.pipeline_id)throw Error(r.error);setSelected(r);await load()}catch(e){setProblem(String(e))}finally{setBusy(false)}};
 const launchable=Object.entries(catalog?.pipelines||{}).filter(([,spec])=>!spec.requires_changeset);
 return <section className="mission" aria-label="AI Director"><div className="mission-head"><div><span className="eyebrow">AI DIRECTOR · КОНВЕЙЕРЫ</span><h2>Автономный директор</h2><p className="hint">Этапы выполняются по правилам и переключаются автоматически. Исходные проекты не изменяются, публикация отключена.</p></div><button className="refresh" disabled={busy} onClick={load}>Обновить</button></div>
  <form className="mission-form" onSubmit={e=>{e.preventDefault();act(()=>api('pipelines','POST',{pipeline,project_id:project}))}}><label>Конвейер<select value={pipeline} onChange={e=>setPipeline(e.target.value)}>{launchable.map(([key,spec])=><option key={key} value={key}>{key} — {spec.description}</option>)}</select></label><label>Проект<select value={project} onChange={e=>setProject(e.target.value)}>{catalog?.build_enabled_projects.map(p=><option key={p} value={p}>{p}</option>)}</select></label><button disabled={busy||!project}>Запустить конвейер</button><p className="hint">Конвейеры с изменением кода запускаются через заявку из чата и подтверждаются здесь после просмотра сравнения.</p></form>
  {problem&&<p className="error" role="alert">{problem}</p>}
  {selected&&<div className="mission-form"><PipelineView pipeline={selected}/><div className="mission-actions"><button disabled={busy} onClick={()=>act(()=>api('pipelines/'+selected.pipeline_id))}>Обновить состояние</button>{selected.state==='running'&&<button disabled={busy} onClick={()=>act(()=>api('pipelines/'+selected.pipeline_id+'/cancel','POST'))}>Остановить</button>}{selected.state==='failed'&&selected.failure?.retryable&&<button disabled={busy} onClick={()=>act(()=>api('pipelines/'+selected.pipeline_id+'/retry','POST'))}>Повторить этап</button>}</div></div>}
  <h3>Конвейеры</h3>{list.length?<ul className="mission-list">{list.map(p=><li key={p.pipeline_id}><p><strong>{p.pipeline}</strong> · {p.project_id} · <span className={'state-'+p.state}>{STATE[p.state]||p.state}</span></p><small>Этап: {p.current_stage} ({AGENT[p.current_agent]||p.current_agent}) · {new Date(p.created_at).toLocaleString('ru-RU')}</small><div className="mission-actions"><button disabled={busy} onClick={()=>act(()=>api('pipelines/'+p.pipeline_id))}>Открыть</button></div></li>)}</ul>:<p className="hint">Конвейеров пока нет.</p>}
  <h3>Агенты</h3><ul className="mission-list">{agents.map(a=><li key={a.id}><p><strong>{a.name}</strong> · {a.specialty}</p><small>{a.stages.length?'Этапы: '+a.stages.join(', '):'Этапы не назначены'}{a.active_tasks.length?' · в работе: '+a.active_tasks.length:''}</small></li>)}</ul>
  <h3>Журнал ошибок</h3>{errors.length?<ul className="mission-list">{errors.map(e=><li key={e.error_id+e.time}><p><strong>{e.category}</strong> · {e.project_id} · {e.stage}</p><small>{new Date(e.time).toLocaleString('ru-RU')} · {e.error}</small><Diagnostics items={e.diagnostics}/><p className="hint">{e.next_action}</p></li>)}</ul>:<p className="hint">Ошибок не зафиксировано.</p>}
 </section>;
}
