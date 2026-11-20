import { useMemo, useState } from "react";
import {
  Activity, ArrowUpRight, Atom, Bell, Check, ChevronDown, CircleHelp,
  Command, Cpu, Download, FileCheck2, Fingerprint, FlaskConical, Gauge,
  Github, LayoutDashboard, LockKeyhole, Menu, Play, Radio, RefreshCw,
  Search, Settings2, Shield, ShieldCheck, SlidersHorizontal, Sparkles,
  Terminal, Workflow, X, Zap
} from "lucide-react";

type Tab = "Overview" | "Campaign runner" | "Providers" | "Evidence";
const providers = [
  { id: "openai", name: "OpenAI", model: "GPT family", color: "cyan", key: "OPENAI_API_KEY" },
  { id: "anthropic", name: "Anthropic", model: "Claude family", color: "pink", key: "ANTHROPIC_API_KEY" },
  { id: "gemini", name: "Google Gemini", model: "Gemini family", color: "violet", key: "GEMINI_API_KEY" },
  { id: "ollama", name: "Ollama", model: "Local models", color: "green", key: "No key by default" },
  { id: "deepseek", name: "DeepSeek", model: "DeepSeek models", color: "blue", key: "DEEPSEEK_API_KEY" },
  { id: "groq", name: "Groq", model: "Groq-hosted models", color: "orange", key: "GROQ_API_KEY" },
  { id: "together", name: "Together", model: "Hosted open models", color: "pink", key: "TOGETHER_API_KEY" },
  { id: "custom", name: "Custom endpoint", model: "Operator configured", color: "muted", key: "Server-side config" }
];

const initialEvents = [
  { time: "19:42:08", title: "Benchmark manifest loaded", detail: "81 cases · OpenMind Benchmark v0.8.0", type: "ok" },
  { time: "19:41:52", title: "Provider adapters discovered", detail: "8 evaluation targets available in this interface", type: "info" },
  { time: "19:40:11", title: "Evidence store ready", detail: "Waiting for a connected evaluation API", type: "info" }
];

export default function App() {
  const [tab, setTab] = useState<Tab>("Overview");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(["gemini", "openai"]);
  const [suite, setSuite] = useState("guardrail-lab");
  const [maxRequests, setMaxRequests] = useState(20);
  const [workers, setWorkers] = useState(2);
  const [timeout, setTimeout] = useState(45);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState("Demo mode · API not connected");
  const [events, setEvents] = useState(initialEvents);
  const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
  const connected = Boolean(apiBase);

  const chosenNames = useMemo(() => selected.map(id => providers.find(p => p.id === id)?.name).filter(Boolean).join(", "), [selected]);

  function toggleProvider(id: string) {
    setSelected(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id]);
  }

  async function runCampaign() {
    if (!selected.length || running) return;
    setRunning(true);
    const stamp = new Date().toLocaleTimeString("en-GB", { hour12: false });
    if (!connected) {
      setNotice("Demo run · no model was contacted");
      setEvents(old => [{ time: stamp, title: "Local demo campaign prepared", detail: `${selected.length} providers selected · ${maxRequests} request ceiling · synthetic preview only`, type: "warn" }, ...old]);
      window.setTimeout(() => setRunning(false), 650);
      return;
    }
    try {
      const response = await fetch(`${apiBase}/api/campaigns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ providers: selected, suite, max_requests: maxRequests, workers, timeout_seconds: timeout })
      });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const data = await response.json();
      setNotice("Campaign request accepted by API");
      setEvents(old => [{ time: stamp, title: "Campaign submitted", detail: data.id ? `Run ID: ${data.id}` : "Backend accepted the campaign request", type: "ok" }, ...old]);
    } catch (error) {
      setNotice(`API error · ${error instanceof Error ? error.message : "Request failed"}`);
      setEvents(old => [{ time: stamp, title: "Campaign request failed", detail: "Check the API URL, CORS policy, and backend logs.", type: "bad" }, ...old]);
    } finally {
      setRunning(false);
    }
  }

  const navItems: { label: Tab; icon: typeof LayoutDashboard }[] = [
    { label: "Overview", icon: LayoutDashboard },
    { label: "Campaign runner", icon: Workflow },
    { label: "Providers", icon: Cpu },
    { label: "Evidence", icon: FileCheck2 }
  ];

  return <div className="app-shell">
    <div className="ambient ambient-a" /><div className="ambient ambient-b" />
    <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
      <div className="brand">
        <div className="brand-mark"><Atom size={22} /></div>
        <div><div className="brand-name">OPENMIND<span>//</span></div><div className="brand-sub">SECURITY LAB <i>v0.8</i></div></div>
        <button className="icon-btn mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={18}/></button>
      </div>
      <div className="workspace-label">WORKSPACE <span>01</span></div>
      <nav className="nav-list">
        {navItems.map(({label, icon: Icon}) => <button key={label} className={`nav-item ${tab === label ? "active" : ""}`} onClick={() => {setTab(label); setMobileOpen(false);}}>
          <Icon size={17}/><span>{label}</span>{label === "Evidence" && <span className="nav-count">03</span>}
        </button>)}
      </nav>
      <div className="side-divider"/>
      <div className="workspace-label">OPERATIONS</div>
      <button className="nav-item" onClick={() => setNotice("Settings are managed by your deployment environment.")}><Settings2 size={17}/><span>Configuration</span></button>
      <button className="nav-item" onClick={() => setNotice("Documentation is available in the project README.")}><CircleHelp size={17}/><span>Documentation</span><ArrowUpRight size={13} className="nav-external"/></button>
      <div className="sidebar-bottom">
        <div className="secure-card">
          <div className="secure-icon"><ShieldCheck size={17}/></div>
          <div><strong>SAFE MODE ACTIVE</strong><span>Reviewed benign probes only</span></div>
          <span className="pulse-dot"/>
        </div>
        <a className="github-link" href="https://github.com/tjcrims0nx/OpenMind-Jailbreak-Lab" target="_blank" rel="noreferrer"><Github size={15}/> Repository <ArrowUpRight size={13}/></a>
        <div className="user-row"><div className="avatar">OM</div><div><b>Operator console</b><span>Local workspace</span></div><ChevronDown size={15}/></div>
      </div>
    </aside>

    {mobileOpen && <button className="scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)}/>}
    <main className="main-area">
      <header className="topbar">
        <div className="top-left"><button className="icon-btn mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={19}/></button><div className="breadcrumb">WORKSPACE <span>/</span> <b>{tab.toUpperCase()}</b></div></div>
        <div className="top-actions"><div className={`connection-pill ${connected ? "connected" : ""}`}><span className="pulse-dot"/>{connected ? "API CONFIGURED" : "LOCAL PREVIEW"}</div><button className="icon-btn" aria-label="Notifications" onClick={() => setNotice("No new system alerts.")}><Bell size={17}/></button><div className="top-avatar">O</div></div>
      </header>

      <div className="content-wrap">
        <section className="hero-row">
          <div><div className="eyebrow"><span className="eyebrow-line"/> AI SECURITY / RESEARCH ENVIRONMENT</div>
            <h1>{tab === "Overview" ? <>Probe the boundary.<br/><em>Prove the result.</em></> : tab === "Campaign runner" ? <>Campaign <em>control.</em></> : tab === "Providers" ? <>Multi-model <em>matrix.</em></> : <>Evidence <em>ledger.</em></>}</h1>
            <p className="hero-copy">A controlled environment for evaluating instruction boundaries, guardrails, and model robustness — with reproducible evidence.</p>
          </div>
          <div className="hero-orb"><div className="orb-ring ring-one"/><div className="orb-ring ring-two"/><div className="orb-core"><Fingerprint size={35}/><span>OMJB</span></div><div className="orb-cross cross-a"/><div className="orb-cross cross-b"/></div>
        </section>

        <div className="status-strip"><div className="status-left"><span className="live-dot"/><b>SYSTEM NOMINAL</b><span className="status-sep">/</span><span>{notice}</span></div><div className="status-right"><span>UTC {new Date().toLocaleTimeString("en-GB",{hour12:false})}</span><span className="status-sep">·</span><span>BUILD 0.8.0</span></div></div>

        {tab === "Overview" && <Overview setTab={setTab} events={events}/>}
        {tab === "Campaign runner" && <Campaign selected={selected} toggle={toggleProvider} suite={suite} setSuite={setSuite} maxRequests={maxRequests} setMaxRequests={setMaxRequests} workers={workers} setWorkers={setWorkers} timeout={timeout} setTimeout={setTimeout} run={runCampaign} running={running} connected={connected} chosenNames={chosenNames}/>}
        {tab === "Providers" && <Providers selected={selected} toggle={toggleProvider}/>}
        {tab === "Evidence" && <Evidence events={events}/>}
        <footer><span>OPENMIND // TEST WITH INTENT. VERIFY WITH EVIDENCE.</span><span><LockKeyhole size={12}/> AUTHORIZED RESEARCH ONLY</span></footer>
      </div>
    </main>
  </div>;
}

function Overview({setTab, events}: {setTab:(t:Tab)=>void; events:{time:string;title:string;detail:string;type:string}[]}) {
  return <>
    <div className="metrics-grid">
      <Metric icon={FlaskConical} label="BENCHMARK CASES" value="81" sub="v0.8.0 · versioned corpus" color="cyan"/>
      <Metric icon={Cpu} label="PROVIDER TARGETS" value="08" sub="Native + compatible adapters" color="violet"/>
      <Metric icon={Activity} label="EVIDENCE EVENTS" value={String(events.length).padStart(2,"0")} sub="This browser session" color="pink"/>
      <Metric icon={Gauge} label="RUN BUDGET" value="READY" sub="Finite limits configurable" color="green"/>
    </div>
    <div className="section-heading"><div><div className="eyebrow">01 / CONTROL DECK</div><h2>Evaluation overview</h2></div><button className="text-action" onClick={() => setTab("Campaign runner")}>OPEN CAMPAIGN RUNNER <ArrowUpRight size={14}/></button></div>
    <div className="dashboard-grid">
      <div className="panel suite-panel"><div className="panel-head"><div><span className="panel-kicker">ACTIVE SUITE</span><h3>Guardrail Lab</h3></div><span className="tag tag-green">READY</span></div>
        <p className="muted">A reviewed set of defensive checks for instruction boundaries, untrusted content handling, and benign controls.</p>
        <div className="suite-stats"><div><strong>76</strong><span>RUNNABLE CASES</span></div><div><strong>24</strong><span>CORE CASES</span></div><div><strong>52</strong><span>SAFE ADAPTATIONS</span></div></div>
        <div className="progress-label"><span>SUITE CATALOGUED</span><b>100%</b></div><div className="progress-track"><i style={{width:"100%"}}/></div>
        <button className="primary-btn" onClick={() => setTab("Campaign runner")}><Play size={15} fill="currentColor"/> Configure evaluation <ArrowUpRight size={15}/></button>
      </div>
      <div className="panel activity-panel"><div className="panel-head"><div><span className="panel-kicker">SYSTEM TELEMETRY</span><h3>Recent activity</h3></div><span className="live-label"><i/> LIVE FEED</span></div>
        <div className="event-list">{events.slice(0,4).map((e,i)=><div className="event-row" key={i}><div className={`event-icon ${e.type}`}>{e.type==="ok"?<Check size={14}/>:e.type==="warn"?<Zap size={14}/>:<Radio size={14}/>}</div><div className="event-copy"><b>{e.title}</b><span>{e.detail}</span></div><time>{e.time}</time></div>)}</div>
        <button className="subtle-btn" onClick={() => setTab("Evidence")}>VIEW EVIDENCE LOG <ArrowUpRight size={13}/></button>
      </div>
    </div>
    <div className="section-heading compact"><div><div className="eyebrow">02 / RESEARCH MODULES</div><h2>Lab instruments</h2></div></div>
    <div className="module-grid">
      <Module icon={Workflow} n="01" title="Mutation & replay" desc="Typed transforms, deterministic seeds, and replayable candidate traces." status="REVIEWED INPUTS"/>
      <Module icon={Shield} n="02" title="Guardrail evaluation" desc="Structured checks, candidate signals, and human adjudication workflow." status="76 CASES"/>
      <Module icon={FileCheck2} n="03" title="Evidence & provenance" desc="Run manifests, hashes, trace records, and exportable findings." status="AUDIT READY"/>
    </div>
    <div className="notice"><ShieldCheck size={17}/><p><b>Research integrity:</b> automated signals are candidates, not proof. Review and reproduce findings before drawing conclusions.</p></div>
  </>;
}

function Metric({icon:Icon,label,value,sub,color}:{icon:typeof Activity;label:string;value:string;sub:string;color:string}) {
  return <div className={`metric-card metric-${color}`}><div className="metric-top"><span>{label}</span><Icon size={17}/></div><div className="metric-value">{value}</div><div className="metric-sub">{sub}</div><div className="metric-decoration"/></div>;
}
function Module({icon:Icon,n,title,desc,status}:{icon:typeof Activity;n:string;title:string;desc:string;status:string}) {
  return <div className="module-card"><div className="module-top"><div className="module-icon"><Icon size={19}/></div><span>{n}</span></div><h3>{title}</h3><p>{desc}</p><div className="module-status"><i/>{status}<ArrowUpRight size={13}/></div></div>;
}

function Campaign(props:any) {
  return <div className="campaign-layout">
    <div className="panel campaign-main"><div className="panel-head"><div><span className="panel-kicker">CAMPAIGN CONFIGURATION</span><h3>Build an evaluation run</h3></div><span className="tag tag-cyan">BOUNDED</span></div>
      <label className="field-label">TEST SUITE</label><select className="select-field" value={props.suite} onChange={e=>props.setSuite(e.target.value)}><option value="guardrail-lab">Guardrail Lab · 76 cases</option><option value="benchmark-v0.8">OpenMind Benchmark · 81 cases</option><option value="benign-controls">Reviewed benign controls</option></select>
      <div className="field-label provider-label">TARGET PROVIDERS <span>{props.selected.length} SELECTED</span></div>
      <div className="provider-pick-grid">{providers.map(p=><button key={p.id} className={`provider-pick ${props.selected.includes(p.id)?"picked":""}`} onClick={()=>props.toggle(p.id)}><span className={`provider-dot dot-${p.color}`}/><span>{p.name}</span>{props.selected.includes(p.id)&&<Check size={14}/>}</button>)}</div>
      <div className="field-label limits-label">EXECUTION LIMITS <span>HARD CEILINGS</span></div>
      <div className="limits-grid">
        <label>MAX REQUESTS <div className="number-control"><button onClick={()=>props.setMaxRequests(Math.max(1,props.maxRequests-5))}>−</button><b>{props.maxRequests}</b><button onClick={()=>props.setMaxRequests(Math.min(500,props.maxRequests+5))}>+</button></div></label>
        <label>WORKERS <div className="number-control"><button onClick={()=>props.setWorkers(Math.max(1,props.workers-1))}>−</button><b>{props.workers}</b><button onClick={()=>props.setWorkers(Math.min(8,props.workers+1))}>+</button></div></label>
        <label>TIMEOUT (SEC) <div className="number-control"><button onClick={()=>props.setTimeout(Math.max(5,props.timeout-5))}>−</button><b>{props.timeout}</b><button onClick={()=>props.setTimeout(Math.min(180,props.timeout+5))}>+</button></div></label>
      </div>
      <button className="primary-btn run-btn" disabled={props.running||!props.selected.length} onClick={props.run}>{props.running?<RefreshCw size={16} className="spin"/>:<Play size={16} fill="currentColor"/>}{props.running?"Submitting…":"Prepare campaign"}<ArrowUpRight size={15}/></button>
      <div className="safe-note"><LockKeyhole size={14}/><span>Use reviewed benign probes. Backend must enforce authorization, budget, and request limits.</span></div>
    </div>
    <div className="campaign-side">
      <div className="panel"><span className="panel-kicker">RUN SUMMARY</span><h3>Configuration</h3><div className="summary-row"><span>Providers</span><b>{props.selected.length}</b></div><div className="summary-row"><span>Suite</span><b>{props.suite}</b></div><div className="summary-row"><span>Request ceiling</span><b>{props.maxRequests}</b></div><div className="summary-row"><span>Concurrency</span><b>{props.workers} workers</b></div><div className="summary-row"><span>Timeout</span><b>{props.timeout}s</b></div><div className="summary-divider"/><div className="summary-total"><span>SELECTED TARGETS</span><p>{props.chosenNames||"No providers selected"}</p></div></div>
      <div className="panel api-panel"><div className="api-icon"><Terminal size={18}/></div><div><b>{props.connected?"API endpoint configured":"Demo mode active"}</b><p>{props.connected?"Campaign requests will be sent to your configured backend.":"Connect your Python API to run real evaluations. Demo mode never contacts a model."}</p></div><span className={`api-indicator ${props.connected?"on":""}`}/></div>
    </div>
  </div>;
}

function Providers({selected,toggle}:{selected:string[];toggle:(id:string)=>void}) {
  return <><div className="section-heading"><div><div className="eyebrow">03 / TARGET ADAPTERS</div><h2>Provider matrix</h2></div><span className="tag tag-cyan">{providers.length} TARGET TYPES</span></div>
    <div className="providers-grid">{providers.map(p=><div className="panel provider-card" key={p.id}><div className="provider-card-top"><span className={`provider-logo dot-${p.color}`}><Cpu size={18}/></span><span className={`tag ${selected.includes(p.id)?"tag-green":"tag-muted"}`}>{selected.includes(p.id)?"SELECTED":"AVAILABLE IN UI"}</span></div><h3>{p.name}</h3><p>{p.model}</p><div className="provider-key"><LockKeyhole size={13}/>{p.key}</div><button className={`select-provider ${selected.includes(p.id)?"selected":""}`} onClick={()=>toggle(p.id)}>{selected.includes(p.id)?<><Check size={14}/> Selected</>:<>＋ Add target</>}</button></div>)}</div>
    <div className="notice"><LockKeyhole size={17}/><p>Credentials belong in your Python backend's environment or deployment secrets. They must never be embedded in this frontend.</p></div>
  </>;
}

function Evidence({events}:{events:{time:string;title:string;detail:string;type:string}[]}) {
  return <><div className="section-heading"><div><div className="eyebrow">04 / AUDIT TRAIL</div><h2>Evidence ledger</h2></div><span className="tag tag-muted">SESSION LOG</span></div>
    <div className="panel evidence-panel"><div className="panel-head"><div><span className="panel-kicker">EVENT STREAM</span><h3>Recorded activity</h3></div><button className="subtle-btn" onClick={()=>navigator.clipboard?.writeText(JSON.stringify(events,null,2))}><Download size={13}/> COPY JSON</button></div>
      {events.map((e,i)=><div className="evidence-row" key={i}><div className={`event-icon ${e.type}`}>{e.type==="ok"?<Check size={14}/>:e.type==="warn"?<Zap size={14}/>:<Radio size={14}/>}</div><div><b>{e.title}</b><p>{e.detail}</p></div><time>{e.time}</time></div>)}
      <div className="empty-evidence"><Fingerprint size={25}/><b>Evidence stays inspectable.</b><span>Connect the evaluation API to populate real run records and provider responses.</span></div>
    </div>
  </>;
}