/* Fonte: https://www.ufpb.br/aci/alteracao-de-plano-de-estudos/ */
(function(root) {
  const TIMES={M:[[420,480],[480,530],[530,580],[580,640],[640,690],[690,740]],T:[[780,840],[840,890],[890,940],[940,1000],[1000,1050],[1050,1100]],N:[[1140,1190],[1190,1240],[1240,1290],[1290,1340]]};
  const DAYS={1:'Domingo',2:'Segunda',3:'Terça',4:'Quarta',5:'Quinta',6:'Sexta',7:'Sábado'};
  const time=m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;
  function date(value) {
    const [d,m,y]=value.split('/').map(Number), utc=Date.UTC(y,m-1,d), check=new Date(utc);
    if(check.getUTCFullYear()!==y||check.getUTCMonth()!==m-1||check.getUTCDate()!==d)throw new Error('Data inválida');
    return utc;
  }
  function parse(code) {
    const meetings=[],errors=[],source=String(code||'').trim().toUpperCase();
    const pattern=/([1-7]+)([MTN])([1-6]+)(?:\s*\((\d{2}\/\d{2}\/\d{4})\s*-\s*(\d{2}\/\d{2}\/\d{4})\))?/g;
    let match,end=0;
    while((match=pattern.exec(source))) {
      if(source.slice(end,match.index).replace(/[\s,;]+/g,''))errors.push('Trecho de horário não reconhecido');
      end=pattern.lastIndex;
      const [,days,shift,slots,from,to]=match;
      let startDate=null,endDate=null;
      try{if(from){startDate=date(from);endDate=date(to);if(startDate>endDate)throw new Error();}}
      catch{errors.push('Período de datas inválido');continue;}
      const numbers=[...new Set([...slots].map(Number))].sort((a,b)=>a-b);
      if(numbers.some(n=>!TIMES[shift][n-1])){errors.push('Horário fora da tabela da UFPB');continue;}
      const ranges=[];
      for(const n of numbers){const [start,finish]=TIMES[shift][n-1],previous=ranges.at(-1);if(previous&&previous.end===start)previous.end=finish;else ranges.push({start,end:finish});}
      for(const day of new Set([...days].map(Number)))for(const range of ranges)meetings.push({day,...range,startDate,endDate});
    }
    if(source.slice(end).replace(/[\s,;]+/g,''))errors.push('Trecho de horário não reconhecido');
    if(!meetings.length)errors.push('Horário não informado ou não reconhecido');
    return{meetings:errors.length?[]:[...new Map(meetings.map(m=>[JSON.stringify(m),m])).values()],errors:[...new Set(errors)]};
  }
  function overlap(a,b) {
    if(a.day!==b.day||a.start>=b.end||b.start>=a.end)return false;
    const start=Math.max(a.startDate??-Infinity,b.startDate??-Infinity),end=Math.min(a.endDate??Infinity,b.endDate??Infinity);
    if(start>end)return false;
    if(Number.isFinite(start)&&Number.isFinite(end)) {
      const weekday=new Date(start).getUTCDay()+1;
      if(start+((a.day-weekday+7)%7)*86400000>end)return false;
    }
    return true;
  }
  function conflicts(courses) {
    const result=[];
    for(let i=0;i<courses.length;i++)for(let j=i+1;j<courses.length;j++) {
      const hits=[];
      for(const a of parse(courses[i].horario).meetings)for(const b of parse(courses[j].horario).meetings)if(overlap(a,b))hits.push({day:a.day,start:Math.max(a.start,b.start),end:Math.min(a.end,b.end)});
      if(hits.length)result.push({a:courses[i],b:courses[j],hits:[...new Map(hits.map(h=>[JSON.stringify(h),h])).values()]});
    }
    return result;
  }
  const key=r=>JSON.stringify([r.periodo,r.disciplina,r.turma,r.horario]);
  function describe(code) {
    const parsed=parse(code);if(parsed.errors.length)return 'Horário a conferir: '+code;
    const groups=new Map();
    for(const m of parsed.meetings){const k=JSON.stringify([m.start,m.end,m.startDate,m.endDate]);if(!groups.has(k))groups.set(k,{...m,days:[]});groups.get(k).days.push(DAYS[m.day]);}
    return [...groups.values()].map(m=>`${m.days.join(' e ')} · ${time(m.start)}–${time(m.end)}`).join(' / ');
  }
  // Blocos coincidentes aparecem lado a lado; nenhum encobre outro.
  function layout(events) {
    const sorted=events.map(e=>({...e})).sort((a,b)=>a.start-b.start||b.end-a.end),groups=[];
    for(const event of sorted){let group=groups.at(-1);if(!group||event.start>=group.end){group={end:event.end,events:[]};groups.push(group);}group.events.push(event);group.end=Math.max(group.end,event.end);}
    for(const group of groups){const ends=[];for(const event of group.events){let lane=ends.findIndex(end=>end<=event.start);if(lane<0)lane=ends.length;ends[lane]=event.end;event.lane=lane;}for(const event of group.events)event.lanes=ends.length;}
    return sorted;
  }
  const api={TIMES,DAYS,time,parse,overlap,conflicts,key,describe,layout};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.Schedule=api;
})(globalThis);
