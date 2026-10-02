// Run against an isolated local Wrangler DB, never a production address.
import assert from 'node:assert/strict';
const base='http://127.0.0.1:8770';
async function call(path,data,cookie='',extra={}){const r=await fetch(base+path,{method:data===undefined?'GET':'POST',headers:{...(data===undefined?{}:{'Content-Type':'application/json'}),Cookie:cookie,...extra},body:data===undefined?undefined:JSON.stringify(data)});return {status:r.status,data:await r.json(),cookie:r.headers.get('set-cookie')?.split(';')[0]};}
const suffix=Date.now().toString(36),password='test-only-password-123';
assert.equal((await call('/api/sessions')).status,401);
const a=await call('/api/auth/register',{username:'a_'+suffix,password,invite:'local-worker-test'});
const b=await call('/api/auth/register',{username:'b_'+suffix,password,invite:'local-worker-test'});
assert.equal(a.status,200,JSON.stringify(a.data));assert.equal(b.status,200);
assert.equal((await call('/api/auth/me',undefined,a.cookie)).data.runtime,'cloudflare');
assert.equal((await call('/api/start',{demo:true},a.cookie,{Origin:'https://evil.example'})).status,403);
const start=await call('/api/start',{demo:true},a.cookie);assert.equal(start.status,200,JSON.stringify(start.data));const s=start.data;
assert.equal((await call('/api/session?id='+s.id,undefined,b.cookie)).status,404);
const answers=await Promise.all([1,2].map(i=>call('/api/turn',{id:s.id,version:s.updated,action:'answer',answer:'回答'+i},a.cookie)));assert.deepEqual(answers.map(r=>r.status).sort(),[200,409]);
assert.equal((await call('/api/export?id='+s.id,undefined,a.cookie)).status,200);
await call('/api/workspace/save',{kind:'material',id:'same',title:'A',content:'private A'},a.cookie);
await call('/api/workspace/save',{kind:'material',id:'same',title:'B',content:'private B'},b.cookie);
assert.equal((await call('/api/workspace/list',{kind:'material'},a.cookie)).data[0].content,'private A');
assert.equal((await call('/api/workspace/list',{kind:'material'},b.cookie)).data[0].content,'private B');
assert.equal((await call('/api/config',{base_url:'http://localhost',model:'x',api_key:'test-key'},a.cookie)).status,400);
assert.equal((await call('/api/config',{base_url:'https://api.openai.com/v1',model:'test',api_key:'test-key-not-persisted'},a.cookie)).status,200);
assert.equal((await call('/api/config',undefined,a.cookie)).data.has_key,false);
assert.equal((await call('/api/auth/logout',{},a.cookie)).status,200);
assert.equal((await call('/api/sessions',undefined,a.cookie)).status,401);
const logged=await call('/api/auth/login',{username:'a_'+suffix,password});assert.equal(logged.status,200);
assert.equal((await call('/api/sessions',undefined,logged.cookie)).data.length,1);
await call('/api/auth/logout',{},logged.cookie);await call('/api/auth/logout',{},b.cookie);
const page=await fetch(base);assert.equal(page.status,200);assert.match(await page.text(),/cloud-client.js/);
console.log('PASS: real Workers/D1 registration, login, isolation, CSRF, concurrent writes, export, key non-persistence, logout and static page');
