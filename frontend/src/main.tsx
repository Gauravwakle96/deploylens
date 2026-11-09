import { StrictMode, useCallback, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, ArrowDownRight, ArrowUpRight, Box, Check, ChevronRight, Circle, Clock3, Code2, ExternalLink, GitBranch, GitCommitHorizontal, GitPullRequest, Layers3, LayoutDashboard, ListChecks, Radio, RefreshCw, Search, Server, ShieldCheck, Terminal, TriangleAlert, X } from 'lucide-react'
import './style.css'

type Job = {name:string; status:string; started_at:string|null; completed_at:string|null}
type Pipeline = {id:number; title:string; status:string; commit_sha:string; branch:string; started_at:string; url:string; jobs:Job[]}
type Release = {id:number; commit_sha:string; version:string; deployed_at:string; environment:string; run_id:number}
type Incident = {id:number; service:string; opened_at:string; resolved_at:string|null; detail:string}
type Log = {at:string; request_id:string; method:string; path:string; status:number; duration_ms:number}
type Data = {
  generated_at:string; environment:string; version:string; repository:string;
  service:{name:string; status:string; last_checked:string|null; latency_ms:number|null; sample_success_percent:number|null; samples:number; interval_seconds:number};
  checks:{id:number; checked_at:string; healthy:boolean; latency_ms:number}[];
  pipelines:Pipeline[]; releases:Release[]; incidents:Incident[]; pipeline_success_percent:number|null;
  github:{success:boolean; detail:string; checked_at:string}|null;
  observability:{requests:number; errors:number; uptime_seconds:number; logs:Log[]};
}
type Tab = 'Overview'|'Pipelines'|'Incidents'|'Logs'
const when = (date:string|null) => date ? new Date(date).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'Waiting for first check'
const short = (sha:string) => sha.slice(0,7)
const label = (status:string) => status.replaceAll('_',' ')
function Badge({status}:{status:string}) { return <span className={`badge ${['success','healthy','resolved'].includes(status)?'good':['failure','down','timed_out','open'].includes(status)?'bad':'neutral'}`}><span className="status-dot"/>{label(status)}</span> }
function Empty({title,detail}:{title:string;detail:string}) {return <div className="empty"><Layers3 size={25}/><strong>{title}</strong><p>{detail}</p></div>}
function App(){
  const [data,setData]=useState<Data|null>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(true)
  const [tab,setTab]=useState<Tab>('Overview')
  const [search,setSearch]=useState('')
  const [selected,setSelected]=useState<number|null>(null)
  const refresh=useCallback(async(signal?:AbortSignal)=>{
    setBusy(true)
    try {const response=await fetch('/api/dashboard',{signal}); if(!response.ok)throw new Error('Dashboard is temporarily unavailable.'); const result:Data=await response.json();setData(result);setError('')}
    catch(e){if(!(e instanceof DOMException && e.name==='AbortError'))setError('Could not refresh the dashboard. Check the service and try again.')}
    finally{setBusy(false)}
  },[])
  useEffect(()=>{const controller=new AbortController();void refresh(controller.signal); const timer=setInterval(()=>void refresh(controller.signal),30000);return()=>{controller.abort();clearInterval(timer)}},[refresh])
  const service=data?.service
  const openIncidents=data?.incidents.filter(i=>!i.resolved_at).length ?? 0
  const latest=data?.pipelines[0]
  const releases=data?.releases.filter(r=>`${r.commit_sha} ${r.version}`.toLowerCase().includes(search.toLowerCase()))??[]
  const pipeline=data?.pipelines.find(p=>p.id===selected)??latest
  const tabs:{name:Tab; icon:typeof Activity}[]=[{name:'Overview',icon:LayoutDashboard},{name:'Pipelines',icon:GitPullRequest},{name:'Incidents',icon:TriangleAlert},{name:'Logs',icon:Terminal}]
  const repoUrl=`https://github.com/${data?.repository??'Gauravwakle96/deploylens'}`
  return <div className="shell">
    <a className="skip" href="#main">Skip to content</a>
    <aside className="sidebar">
      <a className="brand" href="/"><span className="brand-icon"><Layers3 size={23}/></span>DeployLens<span className="brand-period">.</span></a>
      <div className="workspace"><span className="avatar">GW</span><div><strong>Gauravâ€™s workspace</strong><small>Personal workspace</small></div><ChevronRight size={15}/></div>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Main navigation">{tabs.map(({name,icon:Icon})=><button key={name} className={tab===name?'nav-item active':'nav-item'} onClick={()=>setTab(name)} aria-current={tab===name?'page':undefined}><Icon size={18}/>{name}{name==='Incidents'&&openIncidents>0&&<span className="nav-count">{openIncidents}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="connection"><span className={`status-dot ${data?.github?.success?'connected':''}`}/><div><strong>{data?.github?.success?'GitHub connected':'GitHub sync pending'}</strong><small>{data?.github?.success?'Collecting real workflow results':'Results appear after the first run'}</small></div></div><a href={repoUrl} target="_blank" rel="noreferrer"><Code2 size={16}/> View source <ArrowUpRight size={15}/></a><div className="profile"><span className="avatar small">GW</span><span>Gaurav Wakle<small>Module 5 Â· CI/CD & Monitoring</small></span></div></div>
    </aside>
    <div className="content"><header className="topbar"><div className="breadcrumbs">Workspace <ChevronRight size={14}/> <strong>{tab}</strong></div><div className="topbar-right"><span className="environment"><span className="status-dot connected"/>{data?.environment??'connecting'}</span><a aria-label="Open GitHub repository" href={repoUrl} target="_blank" rel="noreferrer"><GitBranch size={18}/></a></div></header>
    <main id="main"><div className="page-heading"><div><p className="eyebrow">RELEASE OBSERVABILITY</p><h1>{tab==='Overview'?'Every release. In focus.':tab}</h1><p className="subtitle">{tab==='Overview'?'Your deployments, pipelines, and service health â€” in one place.':tab==='Pipelines'?'Follow each commit from build to deployment.':tab==='Incidents'?'A timestamped record of failures and recoveries.':'Request activity from the current application process.'}</p></div><button className="button refresh" disabled={busy} onClick={()=>void refresh()}><RefreshCw size={15} className={busy?'spinning':''}/>{busy?'Refreshing':'Refresh'}</button></div>
    {error&&<div className="notice error" role="alert"><TriangleAlert size={18}/>{error}<button onClick={()=>void refresh()}>Retry</button></div>}
    {data?.github&&!data.github.success&&<div className="notice"><Clock3 size={18}/>{data.github.detail}</div>}
    {!data ? <div className="loading" role="status">{error?'Waiting for a connection.':'Connecting to your workspaceâ€¦'}</div> : <>
      {tab==='Overview'&&<>
        <section className={`health-banner ${service?.status==='down'?'degraded':''}`}><div className="health-banner-icon">{service?.status==='healthy'?<ShieldCheck size={23}/>:<Activity size={23}/>}</div><div><strong>{service?.status==='healthy'?'Monitored service is operational':service?.status==='down'?'Monitored service needs attention':'Waiting for a fresh health check'}</strong><p>{service?.name} <span>Â·</span> Last checked {when(service?.last_checked??null)}</p></div><Badge status={service?.status??'unknown'}/></section>
        <section className="stats" aria-label="Workspace statistics">
          <article><div className="stat-label">Verified releases <Box size={17}/></div><strong>{data.releases.length}<span>releases</span></strong><p><GitCommitHorizontal size={14}/>{data.releases[0]?short(data.releases[0].commit_sha):'First deployment coming up'}</p></article>
          <article><div className="stat-label">Pipeline success <ListChecks size={17}/></div><strong>{data.pipeline_success_percent??'â€”'}{data.pipeline_success_percent!==null&&<span>%</span>}</strong><p>Across recent completed pipelines</p></article>
          <article><div className="stat-label">Health check success <Activity size={17}/></div><strong>{service?.sample_success_percent??'â€”'}{service?.sample_success_percent!==null&&<span>%</span>}</strong><p>{service?.samples} samples Â· last 24 hours</p></article>
          <article><div className="stat-label">Open incidents <TriangleAlert size={17}/></div><strong>{openIncidents}<span>active</span></strong><p>{openIncidents?'Investigate recent failed checks':'No active incidents recorded'}</p></article>
        </section>
        <section className="panel pipeline-panel"><div className="panel-heading"><div><h2>Latest pipeline</h2><p>{latest?latest.title:'Your next push starts the first pipeline'}</p></div><button className="text-button" onClick={()=>setTab('Pipelines')}>View pipelines <ArrowUpRight size={15}/></button></div>{latest?<><div className="pipeline-meta"><Badge status={latest.status}/><span><GitBranch size={14}/>{latest.branch}</span><code>{short(latest.commit_sha)}</code><span className="muted">{when(latest.started_at)}</span></div><div className="stages">{['Build & Test','Docker','Deploy','Monitor'].map((stage,index)=>{const job=latest.jobs.find(j=>j.name===stage);const status=job?.status??'pending';return <div className="stage-wrap" key={stage}><div className={`stage ${status==='success'?'passed':status==='failure'?'failed':''}`}><span className="stage-symbol">{status==='success'?<Check size={17}/>:status==='failure'?<X size={17}/>:<Circle size={15}/>}</span><div><strong>{stage}</strong><small>{label(status)}</small></div>{index===0?<Code2 size={18}/>:index===1?<Box size={18}/>:index===2?<Server size={18}/>:<Radio size={18}/>}</div>{index<3&&<ChevronRight size={16} className="stage-arrow"/>}</div>})}</div></>:<Empty title="Ready for your first pipeline" detail="Push to GitHub to build, test, containerize, and deploy this application."/>}</section>
        <div className="two-column"><section className="panel"><div className="panel-heading"><div><h2>Release history <span className="count">{data.releases.length}</span></h2><p>Confirmed deployments of the running version</p></div></div><label className="search"><Search size={15}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search by commit or version" aria-label="Search releases"/></label>{releases.length?<div className="release-list">{releases.map(r=><a href={`${repoUrl}/commit/${r.commit_sha}`} key={r.id} target="_blank" rel="noreferrer"><span className="release-icon"><Box size={18}/></span><div><strong>{r.version}</strong><small><code>{short(r.commit_sha)}</code> Â· {when(r.deployed_at)}</small></div><Badge status="success"/><ArrowUpRight size={15}/></a>)}</div>:<Empty title={search?'No matching releases':'No verified releases yet'} detail={search?'Try another commit or version.':'A successful deployment and health check will appear here.'}/>}</section>
        <section className="panel"><div className="panel-heading"><div><h2>Service health</h2><p>{service?.name}</p></div><span className="mono">{service?.latency_ms!==null?`${service?.latency_ms.toFixed(0)} ms`:'â€”'}</span></div><div className="health-chart" role="img" aria-label={`${service?.samples} health samples, ${service?.sample_success_percent??'unknown'} percent successful`}>
          {data.checks.length?data.checks.map(c=><div key={c.id} className={c.healthy?'health-bar up':'health-bar down'} title={`${when(c.checked_at)} Â· ${c.healthy?'Passed':'Failed'} Â· ${c.latency_ms.toFixed(0)} ms`}/>):<p>No samples collected yet.</p>}</div><div className="chart-legend"><span>Up to 60 recent checks</span><span><i/> Passed <i className="red"/> Failed</span></div><div className="health-details"><span>Probe interval<strong>{service?.interval_seconds}s</strong></span><span>Observation window<strong>24 hours</strong></span></div><p className="panel-footnote">Sample-based availability. Gaps are not counted as successful checks.</p></section></div>
        <section className="panel timeline-panel"><div className="panel-heading"><div><h2>Incident timeline</h2><p>Failures and recoveries as they happen</p></div><button className="text-button" onClick={()=>setTab('Incidents')}>View all <ArrowUpRight size={15}/></button></div>{data.incidents.length?<IncidentList incidents={data.incidents.slice(0,3)}/>:<div className="no-incidents"><ShieldCheck size={21}/><div><strong>No incidents recorded</strong><p>When a health check fails, the incident and its recovery will appear here.</p></div></div>}</section>
      </>}
      {tab==='Pipelines'&&<div className="pipeline-layout"><section className="panel"><div className="panel-heading"><h2>Workflow runs</h2><a className="text-button" href={`${repoUrl}/actions`} target="_blank" rel="noreferrer">GitHub Actions <ExternalLink size={14}/></a></div>{data.pipelines.length?data.pipelines.map(p=><button className={`run-row ${pipeline?.id===p.id?'selected':''}`} key={p.id} onClick={()=>setSelected(p.id)}><GitPullRequest size={18}/><span><strong>{p.title}</strong><small>{short(p.commit_sha)} Â· {when(p.started_at)}</small></span><Badge status={p.status}/></button>):<Empty title="No pipeline runs yet" detail="The first workflow run will be imported from GitHub automatically."/>}</section><section className="panel"><div className="panel-heading"><h2>Job details</h2></div>{pipeline?<div className="job-list"><h3>{pipeline.title}</h3>{pipeline.jobs.map((job,i)=><div className="job" key={i}><div><strong>{job.name}</strong><small>{when(job.started_at)}</small></div><Badge status={job.status}/></div>)}<a className="button" href={pipeline.url} target="_blank" rel="noreferrer">Open full build logs <ExternalLink size={14}/></a></div>:<Empty title="Select a workflow run" detail="Individual job results and build logs will appear here."/>}</section></div>}
      {tab==='Incidents'&&<section className="panel"><div className="panel-heading"><h2>Incident history</h2><Badge status={openIncidents?'open':'resolved'}/></div>{data.incidents.length?<IncidentList incidents={data.incidents}/>:<Empty title="No incidents recorded" detail="Monitoring creates an incident on failure and resolves it on recovery."/>}</section>}
      {tab==='Logs'&&<><section className="stats logs-stats"><article><div className="stat-label">Requests <Activity size={17}/></div><strong>{data.observability.requests}</strong><p>Since this process started</p></article><article><div className="stat-label">Server errors <TriangleAlert size={17}/></div><strong>{data.observability.errors}</strong><p>HTTP responses with status 500+</p></article><article><div className="stat-label">Process uptime <Clock3 size={17}/></div><strong>{Math.floor(data.observability.uptime_seconds/60)}<span>min</span></strong><p>Counters reset after a restart</p></article></section><section className="panel"><div className="panel-heading"><div><h2>Request logs</h2><p>Recent sanitized events Â· no request bodies or credentials</p></div><a href="/metrics" className="text-button" target="_blank" rel="noreferrer">Metrics <ExternalLink size={14}/></a></div><div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable request logs"><table><thead><tr><th>Time</th><th>Request</th><th>Status</th><th>Duration</th><th>Request ID</th></tr></thead><tbody>{data.observability.logs.map(l=><tr key={l.request_id}><td>{when(l.at)}</td><td><code>{l.method} {l.path}</code></td><td><span className={`http-status ${l.status<400?'good':'bad'}`}>{l.status}</span></td><td>{l.duration_ms} ms</td><td><code>{l.request_id}</code></td></tr>)}</tbody></table></div></section></>}
    </>}
    <footer><span><span className="footer-dot"/>DeployLens <span className="footer-separator">/</span> Built by Gaurav Wakle</span><span aria-live="polite">{data?`Updated ${when(data.generated_at)}`:'Connecting'} <span className="footer-separator">Â·</span> Refreshes every 30s</span></footer>
    </main></div>
  </div>
}
function IncidentList({incidents}:{incidents:Incident[]}) {return <div className="incidents">{incidents.map(i=><div className="incident" key={i.id}><span className={`incident-icon ${i.resolved_at?'resolved':''}`}>{i.resolved_at?<ArrowDownRight size={19}/>:<TriangleAlert size={19}/>}</span><div><strong>{i.service} Â· {i.detail}</strong><p>Opened {when(i.opened_at)}{i.resolved_at&&` Â· Recovered ${when(i.resolved_at)}`}</p></div><Badge status={i.resolved_at?'resolved':'open'}/></div>)}</div>}
createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>)
