'use strict';
const $ = id => document.getElementById(id);
let session = null, config = {}, busy = false, toastTimer;
const draftFields = ['videoUrl','transcript','studyTitle','goal','level','minutes'];
let activeDraftKey = '', pendingStart = false;
let summaryRequested = false;
const storage = {
  prefix(){return 'bili-study:'+(window.studyIdentity?.multi_user ? window.studyIdentity.user?.id+':' : '');},
  get(key) {try{return JSON.parse(localStorage.getItem(this.prefix()+key));}catch{return null;}},
  set(key,value) {try{localStorage.setItem(this.prefix()+key,JSON.stringify(value));return true;}catch{return false;}},
  remove(key) {try{localStorage.removeItem(this.prefix()+key);}catch{}}
};
function answerKey(s) {return 'answer:'+s.id+':'+s.messages.length;}
function saveAnswer() {
  if(!activeDraftKey)return;
  const saved=storage.set(activeDraftKey,$('answer').value);
  $('answerStatus').textContent=saved ? ($('answer').value ? '草稿已保存 · '+$('answer').value.length+' / 6000' : 'Ctrl / ⌘ + Enter 发送') : '无法保存草稿，请保持页面打开';
  $('sendAnswer').disabled=!$('answer').value.trim();
}
function saveMaterial() {
  const saved=storage.set('material',Object.fromEntries(draftFields.map(id=>[id,$(id).value])));
  $('draftStatus').textContent=saved ? '材料草稿已自动保存' : '浏览器空间不足，请备份材料';
  updateReadiness();
}
function updateReadiness() {
  const count=materialLength($('transcript').value), hasMaterial=!!$('transcript').value.trim();
  $('charCount').textContent=count.toLocaleString()+' / 55,000 字符';
  $('charCount').classList.toggle('over-limit',count>55000);
  $('materialReady').textContent=hasMaterial ? '✓ 材料已添加' : '① 添加学习材料';
  $('materialReady').classList.toggle('complete',hasMaterial);
  $('setupShortcut').textContent=config.model ? '✓ 模型已配置（未验证连接）' : '② 配置模型';
  $('setupShortcut').classList.toggle('complete',!!config.model);
  $('startHelp').textContent=count>55000 ? '材料过长，请按章节拆分' : !hasMaterial ? '先读取字幕，或直接粘贴材料' : !config.model ? '下一步：配置用于学习的模型' : '准备好了，开始提炼与提问';
  $('startStudy').textContent=hasMaterial&&!config.model ? '配置模型并继续 →' : '生成学习地图 →';
  $('startStudy').disabled=!hasMaterial||count>55000;
  $('configDot').classList.toggle('ready',!!config.model);
}
function setView(view) {
  $('studyLayout').dataset.view=view;
  $('practiceView').setAttribute('aria-pressed',String(view==='practice'));
  $('mapView').setAttribute('aria-pressed',String(view==='map'));
  $('focusView').setAttribute('aria-pressed',String(view==='focus'));
}

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(response.status===401){location.reload();throw new Error('登录已失效，请重新登录。');}
  let result;
  try {result=await response.json();} catch {throw new Error('服务响应异常，请确认本地 App 已启动。');}
  if (!response.ok) throw new Error(result.error || '请求失败，请重试。');
  return result;
}
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function toast(message, error=false) {
  $('toast').textContent = message;
  $('toast').className = 'toast' + (error ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), error ? 10000 : 3500);
}
async function operation(message, task) {
  if (busy) return;
  busy = true;
  const errorBox=session ? $('studyError') : $('homeError');
  errorBox.classList.add('hidden');
  $('busyText').textContent = message;
  $('busyOverlay').classList.remove('hidden');
  try { await task(); } catch (error) {errorBox.textContent=error.message;errorBox.classList.remove('hidden');toast(error.message, true);}
  finally { busy = false; $('busyOverlay').classList.add('hidden'); }
}
async function refreshSessions() {
  const sessions = await api('/api/sessions');
  $('sessionCount').textContent = sessions.length;
  $('sessionList').replaceChildren();
  if (!sessions.length) $('sessionList').append(el('p','empty-list','你的学习记录会出现在这里。'));
  for (const s of sessions) {
    const button = el('button','session-item' + (session?.id === s.id ? ' active' : ''));
    button.append(el('strong','',s.title), el('small','',`${s.demo ? '演示' : '学习'} · ${s.ended ? '已结束' : '进行中'} · ${new Date(s.updated * 1000).toLocaleDateString('zh-CN')}`));
    button.addEventListener('click', () => operation('正在恢复学习记录', async () => {saveAnswer();session = await api('/api/session?id='+encodeURIComponent(s.id));setView('practice');renderSession();await refreshSessions();window.scrollTo({top:0});}));
    $('sessionList').append(button);
  }
}
function home() {
  saveAnswer();activeDraftKey='';storage.remove('active');
  session = null;
  document.querySelector('.sidebar').classList.remove('show-history');$('mobileHistory').setAttribute('aria-expanded','false');
  $('homeView').classList.remove('hidden');$('studyView').classList.add('hidden');
  $('breadcrumbText').textContent = '开始学习';
  updateReadiness();window.scrollTo({top:0});
  refreshSessions().catch(error => toast(error.message,true));
}
$('mobileHistory').addEventListener('click',()=>{const open=document.querySelector('.sidebar').classList.toggle('show-history');$('mobileHistory').setAttribute('aria-expanded',String(open));});
function statusClass(status) { return status === '需要提示' ? ' assisted' : status.startsWith('可') ? ' verified' : ''; }
function showSource(id) {
  const seg=session.segments.find(s=>s.id===id);if(!seg)return;
  $('sourceTitle').textContent=id+(seg.start ? ' · '+seg.start+'–'+(seg.end||'') : ' · 原文段落');
  $('sourceText').textContent=seg.text;$('sourceVideo').classList.add('hidden');
  try {const url=new URL(session.url);if(url.protocol==='https:'&&['www.bilibili.com','bilibili.com'].includes(url.hostname)){if(seg.start)url.searchParams.set('t',Math.floor(toSeconds(seg.start)));$('sourceVideo').href=url.href;$('sourceVideo').classList.remove('hidden');}}catch{}
  $('sourceDialog').showModal();
}
function renderSession() {
  storage.set('active',session.id);
  const key=answerKey(session);
  if(key!==activeDraftKey){activeDraftKey=key;$('answer').value=storage.get(key)||'';}
  saveAnswer();
  document.querySelector('.sidebar').classList.remove('show-history');$('mobileHistory').setAttribute('aria-expanded','false');
  $('homeView').classList.add('hidden');$('studyView').classList.remove('hidden');
  $('breadcrumbText').textContent = session.title;
  $('sessionTitle').textContent = session.title;
  $('sessionGoal').textContent = '学习目标：'+session.learning.goal;
  $('modeBadge').textContent = session.demo ? '演示 · 无模型评判' : '模型学习';
  $('modeBadge').className = 'mode-badge' + (session.demo ? '' : ' real');
  $('pointCount').textContent = session.plan.points.length+' 个核心知识点';
  const summary = $('summary');summary.replaceChildren();
  summary.append(el('div','summary-main',session.plan.main_idea),el('p','summary-copy',session.plan.overview),el('div','section-label','知识关系'),el('div','structure-box',session.plan.structure));
  if (session.plan.prerequisites.length) {summary.append(el('div','section-label','必要前置知识'));for (const p of session.plan.prerequisites) summary.append(el('p','prerequisite',p));}
  summary.append(el('p','coverage','覆盖范围：'+session.plan.coverage));
  $('knowledgePoints').replaceChildren();
  session.plan.points.forEach((point,index) => {
    const record = session.records[point.id];
    const detail = el('details','point-card'+(index===session.current && !session.ended ? ' current':''));
    detail.open = index===session.current && !session.ended;
    const head = el('summary'); const name = el('span','point-name');name.append(el('small','',String(index+1).padStart(2,'0')),document.createTextNode(point.title));
    head.append(name,el('span','mastery'+statusClass(record.status),record.status));
    const body = el('div','point-body');body.append(el('p','',point.claim));
    for (const [label,key] of [['价值','why'],['条件','conditions'],['易错点','pitfall']]) {const line = el('div','point-detail');line.append(el('b','',label+'  '),document.createTextNode(point[key]));body.append(line);}
    const refs = el('div','refs');refs.append(el('span','kind-tag',point.kind));
    point.refs.forEach(ref => {const seg = session.segments.find(s=>s.id===ref);const b=el('button','ref-button',seg?.start ? seg.start : ref);b.title='查看原文 '+ref;b.addEventListener('click',()=>showSource(ref));refs.append(b);});
    body.append(refs);
    if (record.evidence.length) {const evidence = el('details','point-detail');evidence.append(el('summary','','掌握证据 · '+record.evidence.length+' 条'));record.evidence.slice(-4).forEach(e=>evidence.append(el('p','',`${e.assisted ? '有提示' : '无提示'}：${e.reason}`)));body.append(evidence);}
    if (record.skipped) body.append(el('p','point-detail','曾跳过，未计入掌握。'));
    detail.append(head,body);$('knowledgePoints').append(detail);
  });
  $('sourceSegments').replaceChildren();
  for (const seg of session.segments) {const node=el('div','source-segment');node.id='source-'+seg.id;node.append(el('strong','',seg.id+(seg.start ? ' · '+seg.start+'–'+(seg.end||'') : ' · 原文段落')),el('p','',seg.text));$('sourceSegments').append(node);}
  $('currentTopic').textContent = session.ended ? '本轮结束 · 可继续薄弱点' : `正在检验：${session.plan.points[session.current].title} · ${session.stage === 'apply' ? '迁移应用' : '理解与解释'}`;
  $('chat').replaceChildren();$('currentExchange').replaceChildren();
  session.messages.forEach((m,i)=>{const node = el('div','chat-message '+m.role);node.append(el('div','message-label',m.role==='user' ? '我的思考' : '知帧教练'),el('div','message-text',m.text));if(m.question)node.append(el('div','question-box',m.question));(i===session.messages.length-1 ? $('currentExchange') : $('chat')).append(node);});
  $('historyLabel').textContent='之前的对话 · '+Math.max(0,session.messages.length-1)+' 条';
  $('conversationHistory').classList.toggle('hidden',session.messages.length<=1);
  $('composer').classList.toggle('hidden',session.ended);
  $('endedCard').classList.toggle('hidden',!session.ended);
  const verified = session.plan.points.filter(p=>session.records[p.id].status==='可迁移应用').length;
  const explained = session.plan.points.filter(p=>session.records[p.id].status==='可独立解释').length;
  $('progressText').textContent=`${verified} / ${session.plan.points.length} 个知识点已验证应用`;
  $('progressNote').textContent=session.demo ? '演示只体验流程，回答不会计入掌握程度。' : `${explained} 个可独立解释 · 其余继续检验，不把浏览或跳过算作掌握`;
  $('masteryProgress').max=session.plan.points.length;$('masteryProgress').value=verified;
  $('endedSummary').textContent = session.demo ? '演示回答已保存，未进行正确性判断。配置模型后，可用自己的材料开始正式学习。' : `${verified} / ${session.plan.points.length} 个知识点已有迁移证据。实践任务：用一个新情境说明某个核心观点的用途、条件与反例。`;
  $('resumeBtn').classList.toggle('hidden',verified===session.plan.points.length);
}
async function turn(action) {
  if (!session || busy) return;
  const answer = $('answer').value;
  if ((action==='answer'||action==='ask') && !answer.trim()) {$('answer').focus();return;}
  await operation(action==='answer' ? '正在分析你的理解' : '正在准备下一步',async()=>{
    const previousDraft=activeDraftKey;
    session=await api('/api/turn',{id:session.id,version:session.updated,action,answer});
    if(action==='answer'||action==='ask')storage.remove(previousDraft);
    if(action==='hint'||action==='explain'||action==='end')storage.set(answerKey(session),answer);
    renderSession();await refreshSessions();if(!session.ended)$('answer').focus();
  });
}
async function openSettings() {
  try {config=await api('/api/config');$('baseUrl').value=config.base_url;$('modelName').value=config.model;$('apiKey').value='';$('clearKey').checked=false;$('keyStatus').textContent=config.has_key ? '同一服务留空可保留密钥；更换服务地址会清除旧密钥。重启后需重新配置。' : '密钥不会写入笔记、数据库或浏览器存储。';$('settingsDialog').showModal();}catch(error){toast(error.message,true);}
}
$('settingsForm').addEventListener('submit',async e=>{
  e.preventDefault();
  try {config=await api('/api/config',{base_url:$('baseUrl').value,model:$('modelName').value,api_key:$('apiKey').value,clear_key:$('clearKey').checked});$('apiKey').value='';const continueStart=pendingStart;pendingStart=false;$('settingsDialog').close();updateReadiness();toast('设置已保存。连接将在开始学习时验证。');if(continueStart)$('startStudy').click();}catch(error){toast(error.message,true);}
});
$('settingsDialog').addEventListener('close',()=>{pendingStart=false;$('apiKey').value='';});
$('closeSettings').addEventListener('click',()=>$('settingsDialog').close());
$('settingsBtn').addEventListener('click',openSettings);$('topSettings').addEventListener('click',openSettings);
$('setupShortcut').addEventListener('click',openSettings);
$('navSettings').addEventListener('click',openSettings);
$('navMaterial').addEventListener('click',()=>{home();$('transcript').focus();});
$('navDemo').addEventListener('click',()=>$('demoBtn').click());
$('quickVideo').addEventListener('click',()=>{home();$('videoUrl').focus();});
$('quickFile').addEventListener('click',()=>{
  $('editTitle').value=session ? session.title : $('studyTitle').value;
  $('editUrl').value=session ? session.url : $('videoUrl').value;
  $('editText').value=session ? JSON.stringify({segments:session.segments.map(s=>({text:s.text,start:s.start ? toSeconds(s.start) : null,end:s.end ? toSeconds(s.end) : null}))},null,2) : $('transcript').value;
  updateEditCount();$('editDialog').showModal();
});
function updateEditCount(){$('editCount').textContent=$('editText').value.length.toLocaleString()+' / 55,000 字符';}
$('editText').addEventListener('input',updateEditCount);
$('closeEdit').addEventListener('click',()=>$('editDialog').close());
$('editImport').addEventListener('click',()=>$('editFile').click());
$('editFile').addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>650000)throw new Error('文件过大，请按章节拆分。');$('editText').value=await file.text();$('editTitle').value=file.name.replace(/\.[^.]+$/,'');$('editUrl').value='';updateEditCount();}catch(error){toast(error.message,true);}e.target.value='';});
$('saveEdit').addEventListener('click',()=>{if(!$('editText').value.trim()||$('editText').value.length>55000){toast('请输入 1–55,000 字符的资料。',true);return;}home();$('studyTitle').value=$('editTitle').value;$('videoUrl').value=$('editUrl').value;$('transcript').value=$('editText').value;saveMaterial();$('editDialog').close();toast('资料已保存为新草稿，可点击“总结视频”。');});
$('editDownload').addEventListener('click',()=>{const content=$('editText').value;if(!content.trim()){toast('请先添加资料。',true);return;}let ext='txt';try{JSON.parse(content);ext='json';}catch{if(content.trim().startsWith('WEBVTT'))ext='vtt';else if(content.includes('-->'))ext='srt';}const link=el('a');const url=URL.createObjectURL(new Blob([content],{type:'text/plain;charset=utf-8'}));link.href=url;link.download=($('editTitle').value||'修改后的资料').replace(/[\\/:*?"<>|]/g,'_')+'.'+ext;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('quickBrowse').addEventListener('click',()=>$('browseDialog').showModal());
$('closeBrowse').addEventListener('click',()=>$('browseDialog').close());
function updateSearch(){const url=new URL('https://search.bilibili.com/all');if($('browseQuery').value.trim())url.searchParams.set('keyword',$('browseQuery').value.trim());$('browseSearch').href=url.href;}
$('browseQuery').addEventListener('input',updateSearch);
document.querySelectorAll('[data-search]').forEach(b=>b.addEventListener('click',()=>{$('browseQuery').value=b.dataset.search;updateSearch();}));
$('browseImport').addEventListener('click',()=>{if(!$('browseVideo').value.trim()){toast('请粘贴视频链接或 BV 号。',true);return;}home();$('videoUrl').value=$('browseVideo').value.trim();$('transcript').value='';$('studyTitle').value='';saveMaterial();$('browseDialog').close();$('fetchSubtitle').click();});
$('quickSummary').addEventListener('click',async()=>{
  if(session){setView('map');toast('已打开本次视频的概要、精华和出处。修改材料后可以重新总结。');return;}
  summaryRequested=true;
  if(!$('transcript').value.trim()&&$('videoUrl').value.trim()){
    await operation('正在读取视频字幕',readVideoMaterial);
  }
  if(!$('transcript').value.trim()){summaryRequested=false;toast('请先添加视频链接，或在“修改资料”中导入字幕。',true);$('videoUrl').focus();return;}
  $('startStudy').click();
});
$('closeSource').addEventListener('click',()=>$('sourceDialog').close());
$('practiceView').addEventListener('click',()=>setView('practice'));
$('mapView').addEventListener('click',()=>setView('map'));
$('focusView').addEventListener('click',()=>setView('focus'));
$('answer').addEventListener('input',saveAnswer);
draftFields.forEach(id=>$(id).addEventListener('input',saveMaterial));
$('newStudy').addEventListener('click',home);
$('subtitleFile').addEventListener('change',async e=>{
  const file=e.target.files[0];if(!file)return;
  if(file.size>650000){toast('文件过大，请按章节拆分字幕。',true);e.target.value='';return;}
  try {$('transcript').value=await file.text();if(!$('studyTitle').value)$('studyTitle').value=file.name.replace(/\.[^.]+$/,'');saveMaterial();toast('字幕文件已导入。');}catch(error){toast('无法读取文件：'+error.message,true);}e.target.value='';
});
async function readVideoMaterial(){
  if(window.studyIdentity?.runtime==='pages-personal'){
    const link=$('videoUrl').value.trim();
    if(!link)throw new Error('请先粘贴视频链接。');
    $('homeError').classList.add('hidden');
    location.assign('http://127.0.0.1:8766/#video='+encodeURIComponent(link));
    return;
  }
  let data;
  if(window.studyIdentity?.multi_user || window.studyIdentity?.runtime==='pages-personal'){
    data=await api('/api/import',{url:$('videoUrl').value});
  }else{
    const job=await api('/api/video/start',{url:$('videoUrl').value});
    sessionStorage.setItem('bili-video-job',job.id);
    data=await waitVideo(job.id);
  }
  fillVideo(data);
}
async function waitVideo(id){
  while(true){const job=await api('/api/video/status?id='+encodeURIComponent(id));$('importStatus').textContent=job.message||'正在处理…';$('busyText').textContent=job.message||'正在处理…';
    if(job.state==='done'){sessionStorage.removeItem('bili-video-job');return job.result;}
    if(job.state==='error'){sessionStorage.removeItem('bili-video-job');throw new Error(job.error);}
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
}
function fillVideo(data){
  if(data.source==='asr'&&data.segments?.at(-1)?.end)data={...data,duration:toSeconds(data.segments.at(-1).end)};
  $('studyTitle').value=data.title;$('videoUrl').value=data.url;
  $('transcript').value=JSON.stringify({segments:data.segments.map(s=>({text:s.text,start:s.start ? toSeconds(s.start) : null,end:s.end ? toSeconds(s.end) : null}))});
  storage.set('videoSource', {...data,segments:undefined});renderVideoSource(data);$('sourceEditor').open=false;
  $('transcript').dispatchEvent(new Event('input'));
  $('importStatus').textContent='已读取 '+data.subtitle+' · '+data.segments.length+' 段字幕';
}
$('fetchSubtitle').addEventListener('click',()=>operation('正在提取视频内容（字幕优先，无字幕尝试本机转写）',readVideoMaterial));
window.accountReady.then(ready=>{if(ready&&!window.studyIdentity?.multi_user&&!window.studyIdentity?.runtime){const id=sessionStorage.getItem('bili-video-job');if(id)operation('恢复视频提取任务',async()=>fillVideo(await waitVideo(id)));}});
function toSeconds(t){return t.split(':').reduce((n,v)=>n*60+Number(v),0);}
$('startStudy').addEventListener('click',async()=>{
  if(!$('transcript').value.trim()){toast('请先读取或导入字幕。',true);$('transcript').focus();return;}
  if(!config.model){pendingStart=true;await openSettings();return;}
  await operation('正在提炼概要与核心知识',async()=>{session=await api('/api/start',{title:$('studyTitle').value||'未命名学习',url:$('videoUrl').value,transcript:$('transcript').value,goal:$('goal').value||'理解并应用核心知识',level:$('level').value,minutes:$('minutes').value});setView(summaryRequested ? 'map' : 'practice');summaryRequested=false;renderSession();await refreshSessions();window.scrollTo({top:0});});
});
$('demoBtn').addEventListener('click',()=>operation('正在打开演示课程',async()=>{session=await api('/api/start',{demo:true,goal:'理解如何用主动回忆检验学习'});setView('practice');renderSession();await refreshSessions();window.scrollTo({top:0});}));
$('sendAnswer').addEventListener('click',()=>turn('answer'));
$('answer').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!e.isComposing){e.preventDefault();turn('answer');}});
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>turn(b.dataset.action)));
$('resumeBtn').addEventListener('click',()=>operation('正在继续薄弱点',async()=>{session=await api('/api/resume',{id:session.id,version:session.updated});renderSession();await refreshSessions();}));
$('exportBtn').addEventListener('click',async()=>{
  if(!session)return;
  try {const data=await api('/api/export?id='+encodeURIComponent(session.id));const blob=new Blob([data.markdown],{type:'text/markdown;charset=utf-8'});const url=URL.createObjectURL(blob);const a=el('a');a.href=url;a.download=session.title.replace(/[\\/:*?"<>|]/g,'_')+'-学习笔记.md';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('学习笔记已导出。');}catch(error){toast(error.message,true);}
});
async function init(){
  if(!await window.accountReady)return;
  const draft=storage.get('material');if(draft)draftFields.forEach(id=>{if(typeof draft[id]==='string')$(id).value=draft[id];});
  const savedVideo=storage.get('videoSource');if(savedVideo&&savedVideo.url===$('videoUrl').value&&$('transcript').value)renderVideoSource(savedVideo);
  updateReadiness();
  try{config=await api('/api/config');updateReadiness();const active=storage.get('active');if(active){try{session=await api('/api/session?id='+encodeURIComponent(active));renderSession();}catch{storage.remove('active');toast('上次的学习无法恢复，可从学习记录重新选择。',true);}}await refreshSessions();}catch(error){toast('连接本地服务失败：'+error.message,true);}
  if(!window.studyIdentity?.multi_user&&!window.studyIdentity?.runtime&&location.hash.startsWith('#video=')){
    const link=new URLSearchParams(location.hash.slice(1)).get('video');
    home();$('videoUrl').value=link||'';saveMaterial();history.replaceState(null,'',location.pathname);
    $('importStatus').textContent='视频链接已带入，点击「读取字幕」开始自动提取。';
  }
  if(!window.studyIdentity?.multi_user&&!window.studyIdentity?.runtime&&location.hash.startsWith('#job=')){
    const id=new URLSearchParams(location.hash.slice(1)).get('job');
    history.replaceState(null,'',location.pathname);home();
    if(/^[a-f0-9]{32}$/.test(id||'')){sessionStorage.setItem('bili-video-job',id);await operation('恢复视频提取任务',async()=>fillVideo(await waitVideo(id)));}
  }
}
init();

function materialLength(raw){try{const d=JSON.parse(raw);const rows=Array.isArray(d)?d:d.segments||d.body;if(Array.isArray(rows))return rows.reduce((n,s)=>n+String(s.text??s.content??'').length,0);}catch{}return raw.length;}
function renderVideoSource(data){
 const panel=$('videoSource');panel.replaceChildren();panel.classList.remove('hidden');panel.append(el('h3','','视频来源'));
 const card=el('article','video-source-card'),cover=el('div','video-cover');cover.append(el('span','','▷'));
 try{const u=new URL(String(data.cover||'').replace(/^http:/,'https:'));if(u.protocol==='https:'&&u.hostname.endsWith('.hdslb.com')){const img=el('img');img.src=u.href;img.alt='视频封面';img.referrerPolicy='no-referrer';img.addEventListener('error',()=>img.remove());cover.append(img);}}catch{}
 if(data.duration)cover.append(el('small','duration',Math.floor(data.duration/60)+':'+String(Math.floor(data.duration%60)).padStart(2,'0')));
 const info=el('div','video-info');info.append(el('h3','',data.title||'B 站视频'));
 const meta=[data.uploader?'UP '+data.uploader:'',data.views!=null?Number(data.views).toLocaleString()+' 次播放':'',data.published?new Date(data.published*1000).toLocaleDateString('zh-CN'):''].filter(Boolean);info.append(el('p','',meta.join(' · ')),el('span','source-state','✓ 内容已准备好 · 可以开始学习'));
 const actions=el('div','source-actions');const open=el('a','secondary','在 B 站观看 ↗');try{const u=new URL(data.url);if(u.protocol==='https:'&&['www.bilibili.com','bilibili.com'].includes(u.hostname)){open.href=u.href;open.target='_blank';open.rel='noopener noreferrer';actions.append(open);}}catch{}
 const edit=el('button','secondary','查看原文');edit.type='button';edit.onclick=()=>{$('sourceEditor').open=true;$('sourceEditor').scrollIntoView({behavior:'smooth',block:'center'});};actions.append(edit);card.append(cover,info,actions);panel.append(card);
}
$('videoUrl').addEventListener('input',()=>{$('videoSource').classList.add('hidden');});

$('askQuestion').addEventListener('click',()=>turn('ask'));
