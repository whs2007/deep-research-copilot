import { useState, useRef, useEffect } from 'react';
const API = 'http://localhost:8002';
const UID = () => localStorage.getItem('deep_uid') || '';
const S = (k, v) => localStorage.setItem(k, v);

function App() {
  const [user, setUser] = useState(null);
  const [showLogin, setShowLogin] = useState(true);
  const [tabs, setTabs] = useState([{ id: 0, topic: '', running: false, progress: [], report: '', timer: 0, iter: '-', evid: '-', qual: '-' }]);
  const [activeTab, setActiveTab] = useState(0);
  const [history, setHistory] = useState([]);
  const [err, setErr] = useState('');
  const [lu, setLu] = useState(''); const [lp, setLp] = useState('');

  useEffect(() => {
    const uid = UID();
    if (uid) fetch(API+'/api/user',{headers:{'X-User-ID':uid}}).then(r=>r.ok?r.json():null).then(d=>{if(d){setUser(d);setShowLogin(false);loadH(uid)}});
  }, []);

  const loadH = async (uid) => {
    try { const r = await fetch(API+'/api/history?limit=50',{headers:{'X-User-ID':uid||UID()}}); if(r.ok) setHistory(await r.json()); } catch(e) {}
  };

  const doL = async () => {
    if(!lu||!lp) return setErr('请输入用户名和密码');
    try {
      const r = await fetch(API+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:lu,password:lp})});
      if(!r.ok){const e=await r.json();throw new Error(e.detail||'登录失败');}
      const d=await r.json(); S('deep_uid',d.user_id); S('deep_token',d.token); setUser(d); setShowLogin(false); loadH(d.user_id);
    } catch(e) { setErr(e.message); }
  };

  const doR = async () => {
    if(!lu||!lp) return setErr('请输入用户名和密码');
    if(lp.length<4) return setErr('密码至少4位');
    try {
      const r = await fetch(API+'/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:lu,password:lp})});
      if(!r.ok){const e=await r.json();throw new Error(e.detail||'注册失败');}
      const d=await r.json(); S('deep_uid',d.user_id); S('deep_token',d.token); setUser(d); setShowLogin(false); loadH(d.user_id);
    } catch(e) { setErr(e.message); }
  };

  const doLogout = () => { localStorage.removeItem('deep_uid'); localStorage.removeItem('deep_token'); setUser(null); setShowLogin(true); setHistory([]); };

  const newTab = () => { const t=[...tabs,{id:Date.now(),topic:'',running:false,progress:[],report:'',timer:0,iter:'-',evid:'-',qual:'-'}]; setTabs(t); setActiveTab(t.length-1); };
  const closeTab = (i) => { if(i===0) return; const t=tabs.filter((_,j)=>j!==i); setTabs(t); setActiveTab(Math.min(activeTab,t.length-1)); };

  const start = async (i) => {
    const tab = {...tabs[i]}; if(!tab.topic) return;
    tab.running=true; tab.progress=[]; tab.report=''; tab.timer=0; tab.iter='-'; tab.evid='-'; tab.qual='-';
    const nt=[...tabs]; nt[i]=tab; setTabs(nt);
    const timer=setInterval(()=>{setTabs(p=>{const n=[...p];if(n[i])n[i]={...n[i],timer:(n[i].timer||0)+1};return n;});},1000);
    try {
      const resp=await fetch(API+'/api/research/stream?topic='+encodeURIComponent(tab.topic)+'&max_iterations=3',{headers:{'X-User-ID':UID()}});
      const reader=resp.body.getReader(); const dec=new TextDecoder(); let buf='';
      while(true){const{done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});
        const lines=buf.split('\n');buf=lines.pop();
        for(const line of lines){if(!line.startsWith('data: '))continue;const d=line.slice(6);
          if(d==='[DONE]'){clearInterval(timer);setTabs(p=>{const n=[...p];if(n[i])n[i]={...n[i],running:false};return n;});loadH(UID());continue;}
          try{const msg=JSON.parse(d);
            if(msg.type==='progress'){setTabs(p=>{const n=[...p];if(!n[i])return p;n[i]={...n[i],progress:[...n[i].progress,msg]};
              if(msg.node==='critic'&&msg.status==='complete'){n[i].iter=msg.iteration||'-';n[i].qual=msg.quality_score!=null?Number(msg.quality_score).toFixed(2):'-';}
              if(msg.node==='search'&&msg.status==='complete')n[i].evid=msg.total_count||'-';return n;});}
            else if(msg.type==='report'){clearInterval(timer);setTabs(p=>{const n=[...p];if(n[i])n[i]={...n[i],running:false,report:msg.data||''};return n;});loadH(UID());}
          } catch(e) {}
        }
      }
    } catch(e) { clearInterval(timer); setTabs(p=>{const n=[...p];if(n[i])n[i]={...n[i],running:false,report:'连接失败: '+e.message};return n;}); }
  };

  const viewReport = async (sid) => {
    try{const r=await fetch(API+'/api/report/'+sid,{headers:{'X-User-ID':UID()}});if(!r.ok)return;const d=await r.json();
      const t=[...tabs,{id:Date.now(),topic:d.topic,running:false,progress:[],report:d.final_report||'',timer:0,iter:d.iteration_count||'-',evid:d.evidence_count||'-',qual:(d.fact_quality_score||0).toFixed(2)}];
      setTabs(t);setActiveTab(t.length-1);} catch(e) {}
  };

  const tab = tabs[activeTab]||tabs[0];
  const PROGRESS_NAMES={planner:'任务规划',search:'信息检索',critic:'质量审核',synthesizer:'报告生成'};
  const PROGRESS_ICONS={planner:'🧠',search:'🔍',critic:'🔬',synthesizer:'📝'};

  if(showLogin) return (
    <div style={{minHeight:'100vh',background:'#0f1117',display:'flex',alignItems:'center',justifyContent:'center'}}>
      <div style={{background:'#161b22',border:'1px solid #30363d',borderRadius:12,padding:32,width:380}}>
        <h2 style={{color:'#e1e4e8',fontSize:18,fontWeight:600,marginBottom:20}}>🔐 登录深度研报</h2>
        <input style={{width:'100%',background:'#0d1117',border:'1px solid #30363d',borderRadius:8,padding:'10px 14px',color:'#e1e4e8',fontSize:14,marginBottom:10,outline:'none'}} placeholder="用户名" value={lu} onChange={e=>setLu(e.target.value)} />
        <input style={{width:'100%',background:'#0d1117',border:'1px solid #30363d',borderRadius:8,padding:'10px 14px',color:'#e1e4e8',fontSize:14,marginBottom:10,outline:'none'}} type="password" placeholder="密码" value={lp} onChange={e=>setLp(e.target.value)} />
        {err && <p style={{color:'#f85149',fontSize:12,marginBottom:8}}>{err}</p>}
        <button onClick={doL} style={{width:'100%',background:'#238636',border:'none',borderRadius:8,padding:'10px',color:'#fff',fontSize:14,cursor:'pointer',marginBottom:8}}>🔑 登录</button>
        <button onClick={doR} style={{width:'100%',background:'#21262d',border:'none',borderRadius:8,padding:'10px',color:'#e1e4e8',fontSize:14,cursor:'pointer'}}>📝 注册新账号</button>
      </div>
    </div>
  );

  return (
    <div style={{height:'100vh',display:'flex',flexDirection:'column',background:'#0f1117',color:'#e1e4e8',overflow:'hidden'}}>
      <header style={{background:'#161b22',borderBottom:'1px solid #30363d',padding:'8px 14px',display:'flex',alignItems:'center',gap:10,flexShrink:0}}>
        <b style={{fontSize:16,background:'linear-gradient(135deg,#58a6ff,#3fb950)',WebkitBackgroundClip:'text',WebkitTextFillColor:'transparent'}}>深度研报</b>
        <span style={{fontSize:11,color:'
