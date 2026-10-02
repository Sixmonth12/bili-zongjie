import {mkdir,readFile,writeFile,copyFile,cp} from 'node:fs/promises';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const out=new URL('./public/',import.meta.url);
await mkdir(out,{recursive:true});
for(const name of ['index.html','app.js','auth.js','workspace.js','style.css']){
  let text=await readFile(new URL('../static/'+name,import.meta.url),'utf8');
  if(name==='index.html')text=text.replace('<script src="/auth.js">','<script src="/cloud-client.js"></script>\n<script src="/auth.js">').replaceAll('学习记录保存在本机','学习记录保存在云端账号中').replaceAll('密钥只保存在当前服务进程内','密钥只保存在当前页面内存中').replaceAll('本地无鉴权模型可留空','刷新后需重新填写 API Key');
  if(name==='app.js')text=text.replaceAll('重启后需重新配置。','刷新或退出后需重新配置。').replaceAll('本地 App 已启动','网站部署正常').replaceAll('连接本地服务失败','连接网站服务失败');
  if(name==='style.css')text=text.replace(/url\("data:image\/jpeg;base64,[^"]+"\)/g,'none');
  await writeFile(new URL(name,out),text);
}
await copyFile(new URL('./client.js',import.meta.url),new URL('cloud-client.js',out));
await build({entryPoints:['node_modules/pdfjs-dist/build/pdf.mjs'],outfile:fileURLToPath(new URL('pdf.mjs',out)),bundle:true,format:'esm',platform:'browser',external:['/pdf.worker.mjs']});
await copyFile('node_modules/pdfjs-dist/build/pdf.worker.mjs',new URL('pdf.worker.mjs',out));
for(const name of ['cmaps','standard_fonts','wasm'])await cp('node_modules/pdfjs-dist/'+name,new URL(name+'/',out),{recursive:true});
console.log('Cloudflare 静态资源构建完成（未包含参考插画）。');
