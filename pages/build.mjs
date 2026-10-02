import {mkdir,readFile,writeFile,copyFile,cp} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
const out=new URL('../dist/pages/',import.meta.url);await mkdir(out,{recursive:true});
for(const name of ['index.html','app.js','auth.js','workspace.js','style.css']){
 let text=await readFile(new URL('../static/'+name,import.meta.url),'utf8');
 if(name==='index.html')text=text.replace('<script src="/auth.js">','<script src="./personal.js"></script><script src="/auth.js">').replaceAll('src="/','src="./').replaceAll('href="/','href="./').replaceAll('学习记录保存在本机','学习记录仅保存在当前浏览器，清理网站数据会删除记录').replaceAll('密钥只保存在当前服务进程内','密钥仅存当前页面，刷新后重填').replaceAll('本地无鉴权模型可留空','模型服务需支持浏览器 CORS').replace('<body>','<body><p class="field-note" style="padding:12px">个人网页版 · 无需注册 · 数据只在此浏览器保存，其他访客无法看到。请手动导入字幕；模型需支持浏览器跨域调用。</p>');
 if(name==='index.html')text=text.replaceAll('读取 B 站字幕','在电脑 App 中提取').replaceAll('读取字幕 ↗','用电脑 App 提取 ↗').replaceAll('自动读取可访问字幕；无字幕或受限时，请导入文件。','先启动电脑上的「自动视频学习」。点击右侧按钮会带上链接打开本机 App；也可在下方直接导入文字。');
 if(name==='index.html')text=text.replace('<body>','<body><div class="field-note" style="padding:12px">只想粘贴视频链接？先启动电脑上的「自动视频学习」，再 <a href="http://127.0.0.1:8766/" target="_blank" rel="noopener">打开本机自动提取版</a>。<a href="https://github.com/Sixmonth12/bili-zongjie/blob/main/VIDEO-LOCAL.md" target="_blank" rel="noopener">安装与使用说明</a></div>');
 if(name==='app.js')text=text.replaceAll('重启后需重新配置。','刷新后需重新配置。').replaceAll('服务响应异常，请确认本地 App 已启动。','处理失败，请刷新网页重试。').replaceAll('连接本地服务失败：','读取个人数据失败：');
 if(name==='style.css')text=text.replace(/url\("data:image\/jpeg;base64,[^"]+"\)/g,'none');
 await writeFile(new URL(name,out),text);
}
await build({entryPoints:['pages/client.js'],outfile:fileURLToPath(new URL('personal.js',out)),bundle:true,format:'iife',external:['./pdf.mjs']});
await copyFile('node_modules/pdfjs-dist/build/pdf.mjs',new URL('pdf.mjs',out));await copyFile('node_modules/pdfjs-dist/build/pdf.worker.mjs',new URL('pdf.worker.mjs',out));
for(const name of ['cmaps','standard_fonts','wasm'])await cp('node_modules/pdfjs-dist/'+name,new URL(name+'/',out),{recursive:true});
await writeFile(new URL('.nojekyll',out),'');console.log('Personal Pages build ready: dist/pages');
await copyFile(new URL('../static/background.jpg',import.meta.url),new URL('background.jpg',out));
