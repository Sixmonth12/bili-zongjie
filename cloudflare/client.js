// Only the Cloudflare build loads this module. Credentials never enter storage.
let modelConfig={base_url:'https://api.openai.com/v1',model:'',api_key:''};
const nativeFetch=window.fetch.bind(window);
window.fetch=async function(input,init={}){
  const path=typeof input==='string'?input:'';
  if(path==='/api/config'){
    if(init.method==='POST'){
      const data=JSON.parse(init.body);const next={base_url:data.base_url.replace(/\/+$/,''),model:data.model,api_key:data.clear_key?'':data.api_key||(data.base_url.replace(/\/+$/,'')===modelConfig.base_url?modelConfig.api_key:'')};
      if(next.api_key){const response=await nativeFetch(path,{...init,body:JSON.stringify(next)});if(!response.ok)return response;}
      else if(!window.studyIdentity?.providers.includes(next.base_url)||!next.model.trim())return Response.json({error:'请选择允许的服务商并填写模型名称。'},{status:400});
      modelConfig=next;
    }
    return Response.json({base_url:modelConfig.base_url,model:modelConfig.model,has_key:!!modelConfig.api_key});
  }
  if(path==='/api/auth/logout')modelConfig={base_url:'https://api.openai.com/v1',model:'',api_key:''};
  if(path==='/api/pdf/extract'){
    try{
      const {getDocument,GlobalWorkerOptions}=await import('/pdf.mjs');GlobalWorkerOptions.workerSrc='/pdf.worker.mjs';
      const data=JSON.parse(init.body),binary=atob(data.file);if(binary.length>8000000)throw new Error('PDF 超过 8 MB');
      const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));const task=getDocument({data:bytes,isEvalSupported:false,useSystemFonts:true,cMapUrl:'/cmaps/',cMapPacked:true,standardFontDataUrl:'/standard_fonts/',wasmUrl:'/wasm/'});
      task.onPassword=()=>{task.destroy();};
      let doc;try{doc=await task.promise;if(doc.numPages>150)throw new Error('PDF 超过 150 页，请拆分。');let count=0;const pages=[];
        for(let page=1;page<=doc.numPages;page++){const p=await doc.getPage(page);const content=await p.getTextContent();const text=content.items.map(i=>(i.str||'')+(i.hasEOL?'\n':' ')).join('');count+=text.length;if(count>55000)throw new Error('PDF 文本超过 55,000 字符，请拆分。');pages.push({page,text});p.cleanup();}
        if(!pages.some(p=>p.text.trim()))throw new Error('未找到文字层，扫描件需先 OCR。');return Response.json({pages,empty_pages:pages.filter(p=>!p.text.trim()).map(p=>p.page)});
      }finally{if(doc)await doc.destroy();else await task.destroy();}
    }catch(e){return Response.json({error:'PDF 提取失败：'+e.message+'；加密文件请先解密。'},{status:400});}
  }
  if(['/api/start','/api/turn','/api/pdf/review'].includes(path)&&init.method==='POST')init={...init,body:JSON.stringify({...JSON.parse(init.body),_model:modelConfig})};
  return nativeFetch(input,init);
};
