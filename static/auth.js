window.studyIdentity=null;
window.accountReady=fetch('/api/auth/me').then(r=>r.json()).then(info=>{
  window.studyIdentity=info;
  if(info.multi_user){const select=document.createElement('datalist');select.id='allowedProviders';info.providers.forEach(url=>{const option=document.createElement('option');option.value=url;select.append(option);});document.body.append(select);document.getElementById('baseUrl')?.setAttribute('list','allowedProviders');}
  if(!info.multi_user)return true;
  const button=document.getElementById('accountButton');button.classList.remove('hidden');
  if(info.user){button.textContent=info.user.name+' · 退出';button.addEventListener('click',async()=>{const response=await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(response.ok)location.reload();});return true;}
  const dialog=document.getElementById('accountDialog');dialog.showModal();dialog.addEventListener('cancel',e=>e.preventDefault());
  async function submit(mode){
    const form=document.getElementById('accountForm');if(!form.reportValidity())return;
    const buttons=Array.from(form.querySelectorAll('button'));buttons.forEach(b=>b.disabled=true);
    try{const response=await fetch('/api/auth/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('accountName').value,password:document.getElementById('accountPassword').value,invite:document.getElementById('accountInvite').value})});const result=await response.json();if(!response.ok)throw new Error(result.error);document.getElementById('accountPassword').value='';location.reload();}catch(e){document.getElementById('accountError').textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}
  }
  document.getElementById('accountForm').addEventListener('submit',e=>{e.preventDefault();submit('login');});
  document.getElementById('registerAccount').addEventListener('click',()=>submit('register'));
  return false;
}).catch(()=>false);
