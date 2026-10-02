export function compactMaterial(material){
  const result=structuredClone(material);
  if(result.segments){let segments=result.segments;const point=result.point;
    if(point){const refs=new Set(point.refs||[]),selected=new Set();segments.forEach((s,i)=>{if(refs.has(s.id))selected.add(i);});let size=[...selected].reduce((n,i)=>n+segments[i].text.length,0);
      if(result.action==='ask'){const query=(result.answer||'').toLowerCase(),terms=new Set((query.match(/[a-z0-9_+]+/g)||[]).filter(t=>t.length>1));for(let i=0;i<query.length-1;i++)if(/^[\u4e00-\u9fff]{2}$/.test(query.slice(i,i+2)))terms.add(query.slice(i,i+2));const ranks=segments.map((s,i)=>({i,score:[...terms].filter(t=>s.text.toLowerCase().includes(t)).length})).sort((a,b)=>b.score-a.score||a.i-b.i).slice(0,12);for(const {i,score} of ranks)if(score&&!selected.has(i)&&size+segments[i].text.length<=6000){selected.add(i);size+=segments[i].text.length;}}
      for(const i of [...selected].sort((a,b)=>a-b))for(const j of [i-1,i+1,i-2,i+2])if(j>=0&&j<segments.length&&!selected.has(j)&&size+segments[j].text.length<=6000){selected.add(j);size+=segments[j].text.length;}
      if(selected.size)segments=[...selected].sort((a,b)=>a-b).map(i=>segments[i]);result.scope='仅当前知识点引用及邻近片段；不足时明确说明，不猜测未提供内容。';
    }else result.coverage_range={count:segments.length,start:segments[0]?.start??null,end:segments.at(-1)?.end??null};
    result.segments=segments.map(s=>`[${s.id}] ${s.text}`).join('\n');
  }
  if(result.history)result.history=result.history.filter(m=>m.point===result.point?.id).slice(-4).map(({role,text,question})=>({role,text,question}));
  if(result.record)result.record={status:result.record.status,skipped:result.record.skipped||false};
  return result;
}
export const outputBudget=material=>'action' in material?1000:3200;
