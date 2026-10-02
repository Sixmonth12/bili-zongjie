export class AppError extends Error { constructor(message, status=400) { super(message); this.status=status; } }
export function check(ok, message, status=400) { if(!ok) throw new AppError(message,status); }
export function field(data,key,max=6000) { const v=data?.[key]; check(typeof v==='string' && v.trim() && v.length<=max,`缺少有效字段：${key}`); return v.trim(); }
const stamp=n=>{check(Number.isFinite(Number(n)) && n>=0,'字幕时间无效'); const s=Math.floor(n);return [Math.floor(s/3600),Math.floor(s/60)%60,s%60].map(v=>String(v).padStart(2,'0')).join(':');};
export function parseTranscript(raw) {
  check(typeof raw==='string' && raw.trim(),'请导入字幕。');check(raw.length<=650000,'字幕超过 55,000 字符，请分段导入。');raw=raw.replace(/^\uFEFF/,'').trim();let segments=[];
  if(/^[{[]/.test(raw)) {
    let data;try{data=JSON.parse(raw);}catch{throw new AppError('JSON 字幕无法解析。');}
    const rows=Array.isArray(data)?data:data.body??data.segments;check(Array.isArray(rows),'JSON 需要 body 或 segments 数组。');
    for(const r of rows){check(r && typeof r==='object','字幕行无效');const text=String(r.content??r.text??'').trim();if(text)segments.push({text,start:(r.from??r.start)==null?null:stamp(r.from??r.start),end:(r.to??r.end)==null?null:stamp(r.to??r.end)});}
  }else for(const block of raw.replace(/\r\n/g,'\n').split(/\n\s*\n/)){
    const lines=block.split('\n'),i=lines.findIndex(l=>l.includes('-->'));
    if(i>=0){const times=lines[i].match(/(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}/g)||[];const text=lines.slice(i+1).join(' ').trim();if(text)segments.push({text,start:times[0]?.replace(',','.')??null,end:times[1]?.replace(',','.')??null});}
    else if(!/^(WEBVTT|NOTE|STYLE|REGION)/.test(block)) for(const text of lines.map(l=>l.trim()).filter(Boolean))segments.push({text,start:null,end:null});
  }
  check(segments.length,'没有有效字幕正文。');check(segments.reduce((n,s)=>n+s.text.length,0)<=55000,'正文超过 55,000 字符');return segments.map((s,i)=>({...s,id:'S'+(i+1)}));
}
export function validatePlan(raw,segments){
  const plan=Object.fromEntries(['main_idea','overview','coverage','structure'].map(k=>[k,field(raw,k)]));
  const pre=raw.prerequisites??[];check(Array.isArray(pre)&&pre.length<=12&&pre.every(p=>typeof p==='string'&&p.length<1500),'前置知识格式无效');plan.prerequisites=pre;
  check(Array.isArray(raw.points)&&raw.points.length>=1&&raw.points.length<=5,'需要 1–5 个知识点');const ids=new Set(segments.map(s=>s.id));
  plan.points=raw.points.map((p,i)=>{const out=Object.fromEntries(['title','claim','why','conditions','pitfall','question'].map(k=>[k,field(p,k)]));check(Array.isArray(p.refs)&&p.refs.length&&p.refs.every(r=>ids.has(r)),'模型引用不存在的字幕段落');const kind=p.kind??'原文';check(['原文','推断','补充'].includes(kind),'观点类型无效');return {...out,id:'K'+(i+1),kind,refs:[...new Set(p.refs)]};});return plan;
}
const point=s=>s.plan.points[s.current];
const latest=s=>s.messages.findLast(m=>m.question)?.question||'';
function message(s,role,text,question=''){s.messages.push({role,text,question,time:Date.now()/1000,point:point(s).id});}
function advance(s){s.assisted=false;s.stage='explain';if(s.current+1>=s.plan.points.length){s.ended=true;return '';}s.current++;return point(s).question;}
export async function newSession(data,model,constants){
  const demo=data.demo===true,segments=parseTranscript(demo?constants.demoText:data.transcript);
  const learning={goal:String(data.goal||'理解并应用核心知识').slice(0,1000),level:String(data.level||'基础了解').slice(0,200),minutes:String(data.minutes||'20').slice(0,20)};
  const plan=validatePlan(demo?constants.demoPlan:await model(constants.planInstruction,{segments,learning}),segments);
  const s={id:crypto.randomUUID(),title:demo?'如何真正学会一个知识点':String(data.title||'未命名学习').slice(0,200),url:demo?'':String(data.url||'').slice(0,500),demo,segments,learning,plan,current:0,stage:'explain',assisted:false,ended:false,records:{},messages:[],created:Date.now()/1000};
  for(const p of plan.points)s.records[p.id]={status:'未验证',evidence:[],skipped:false};message(s,'coach',demo?'固定演示课程，不评判答案正确性。':'学习地图已准备好。',point(s).question);return s;
}
export async function turn(s,data,model,instruction){
  if(data.action==='ask'){
    check(!s.ended,'本轮已结束，请先继续薄弱点');const answer=field(data,'answer',2000),question=latest(s);
    let feedback='演示不调用模型。配置模型并用视频材料开始学习后，可以自由追问。';
    if(!s.demo){const result=await model('回答追加问题，使用提供片段的真实 ID 标注依据，不足就说明，补充须标注。不评分、不改变练习题。只输出 JSON {"feedback":"不超过250字的解释"}。',{action:'ask',answer,point:point(s),segments:s.segments,history:s.messages.slice(-12),learning:s.learning});feedback=field(result,'feedback',3000);s.assisted=true;}
    message(s,'user','追问：'+answer);message(s,'coach',feedback,question);return s;
  }
  check(!s.ended,'本轮已结束，请继续薄弱点或导出。');const action=data.action,answer=data.answer??'',p=point(s),r=s.records[p.id];if(action==='answer')check(typeof answer==='string'&&answer.trim()&&answer.length<=6000,'请输入 1–6000 字符的回答。');
  if(action==='skip'){message(s,'user','跳过当前知识点');r.skipped=true;message(s,'coach','已跳过，仍需练习。',advance(s));}
  else if(action==='end'){s.ended=true;message(s,'coach','本次学习已保存，可以导出笔记或继续薄弱点。');}
  else {check(['answer','hint','explain'].includes(action),'未知学习动作');
    if(s.demo){message(s,'user',action==='answer'?answer:action==='hint'?'给提示':'直接讲解');let q=latest(s);if(action==='answer'){if(s.stage==='explain'){s.stage='apply';q='把这个方法用于下一次学习，你会怎样做？';}else q=advance(s);}message(s,'coach',action==='answer'?'演示仅保存回答，不评判正确性。':action==='hint'?'关注原文中的动作、条件与检验方式。':p.claim,q);}
    else {
      const result=await model(instruction,{action,answer,question:latest(s),point:p,segments:s.segments,stage:s.stage,assisted:s.assisted,learning:s.learning,history:s.messages.slice(-12),record:r});
      let feedback=field(result,'feedback'),q=field(result,'question',2000);const reason=field(result,'evidence',2000),v=result.verdict;
      check(['correct','partial','incorrect','unassessed'].includes(v)&&typeof result.advance==='boolean','模型反馈格式无效');check(action==='answer'||(v==='unassessed'&&!result.advance),'提示或讲解不能算作掌握');
      r.evidence.push({action,answer,question:latest(s),verdict:v,reason,assisted:s.assisted,stage:s.stage});message(s,'user',action==='answer'?answer:action==='hint'?'给提示':'直接讲解');
      if(action!=='answer'){s.assisted=true;if(r.status==='未验证')r.status='需要提示';if(action==='explain')s.stage='explain';}
      else if(v==='correct'){if(s.assisted){s.assisted=false;s.stage='explain';feedback+='\n这次有提示支持，还需独立验证。';q='请合上概要，用自己的例子解释作用和适用条件。';}else if(s.stage==='explain'){r.status='可独立解释';s.stage='apply';}else if(result.advance){r.status='可迁移应用';q=advance(s);}}
      else if(['partial','incorrect'].includes(v)){s.assisted=true;if(r.status==='未验证')r.status='需要提示';}message(s,'coach',feedback,q);
    }
  }return s;
}
export function resume(s){if(!s.ended)return s;const i=s.plan.points.findIndex(p=>s.records[p.id].status!=='可迁移应用');check(i>=0,'所有知识点已有迁移证据，可设定更深入目标。');Object.assign(s,{ended:false,current:i,stage:'explain',assisted:false});message(s,'coach','继续检验薄弱点，先做无提示解释。',point(s).question);return s;}
export function exportNotes(s){return ['# '+s.title,'模式：'+(s.demo?'固定演示，不评判正确性':'模型学习'),'目标：'+s.learning.goal,'来源：'+(s.url||'导入材料'),'## 主旨',s.plan.main_idea,'## 概要',s.plan.overview,'覆盖范围：'+s.plan.coverage,'## 知识关系',s.plan.structure,...s.plan.points.flatMap(p=>['## '+p.title,p.claim,'价值：'+p.why,'条件：'+p.conditions,'易错点：'+p.pitfall,'类型：'+p.kind,'依据：'+p.refs.join(', '),'掌握状态：'+s.records[p.id].status,...s.records[p.id].evidence.map(e=>'判断依据：'+e.reason+(e.assisted?'（有提示）':'（无提示）'))]),'## 下一次练习',s.plan.points.filter(p=>s.records[p.id].status!=='可迁移应用').map(p=>p.title).join('、')||'已有迁移证据，可提高难度','## 学习对话',...s.messages.flatMap(m=>[(m.role==='user'?'我：':'教练：')+m.text,m.question?'问题：'+m.question:'']),'## 原始材料',...s.segments.map(p=>`[${p.id}] ${p.start||''} ${p.text}`)].join('\n\n');}
