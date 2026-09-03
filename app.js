const $ = s => document.querySelector(s);
const S = Schedule;
let rows = [], selected = [], semester = '2026.2', dragging = null, dragMode = null, busy = false;
const el = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const name = r => r.disciplina.replace(/\s*\(GRADUAÇÃO\)\s*$/i,'');
const color = r => 'color-'+([...r.disciplina].reduce((n,c)=>(n*31+c.charCodeAt(0))>>>0,0)%6);
function status(message,error=false){$('#status').textContent=message;$('#status').classList.toggle('error',error);}
function save(){try{localStorage.setItem('ufpb-plan:'+semester,JSON.stringify(selected));}catch{$('#save-note').textContent='Não foi possível salvar. Mantenha esta aba aberta.';}}
function loadPlan(){try{const data=JSON.parse(localStorage.getItem('ufpb-plan:'+semester)||'[]');selected=Array.isArray(data)?data.filter(r=>r&&r.periodo===semester&&['disciplina','turma','horario'].every(k=>typeof r[k]==='string')):[];selected=[...new Map(selected.map(r=>[S.key(r),r])).values()];}catch{selected=[];}}
function authenticated(value){$('#login-panel').hidden=value;$('#query-panel').hidden=!value;$('#logout').hidden=!value;if(value)loadPlan();else{rows=[];selected=[];}render();}
async function api(path,data){const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok){if(response.status===401)authenticated(false);throw new Error(result.error||'Não foi possível concluir.');}return result;}
function remove(key){selected=selected.filter(r=>S.key(r)!==key);save();render();status('Turma removida da grade.');}
function add(key){const row=rows.find(r=>S.key(r)===key);if(!row||selected.some(r=>S.key(r)===key))return;if(row.periodo!==semester||S.parse(row.horario).errors.length){status('Confira o horário e o período desta turma.',true);return;}selected.push(row);save();render();const hits=S.conflicts(selected).filter(c=>S.key(c.a)===key||S.key(c.b)===key);status(hits.length?'Turma adicionada com choque. Confira os detalhes abaixo da grade.':'Turma adicionada: '+S.describe(row.horario),!!hits.length);}
function renderCatalog(){
 const normalize=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase(),term=normalize($('#filter').value);
 const visible=rows.filter(r=>normalize(Object.values(r).join(' ')).includes(term));
 $('#count').textContent=`${visible.length} turma${visible.length===1?' disponível':'s disponíveis'}`;
 $('#empty').hidden=!!visible.length;$('#empty').textContent=busy?'Consultando turmas…':term?'Nenhuma turma corresponde à busca.':'Nenhuma turma encontrada nesta consulta.';
 $('#courses').replaceChildren(...visible.map(row=>{
  const key=S.key(row),active=selected.some(r=>S.key(r)===key),parsed=S.parse(row.horario),card=el('article',undefined,'course '+color(row));
  card.draggable=!active&&!parsed.errors.length;card.classList.toggle('in-plan',active);
  card.append(el('h3',name(row)),el('p',row.turma+' · '+row.docente,'course-meta'),el('p',S.describe(row.horario),'readable-time'));
  const info=el('div',undefined,'course-footer');info.append(el('span',row.horario+' · '+row.vagas,'course-meta'));
  const button=el('button',active?'Remover':'Adicionar',active?'secondary':'');button.type='button';button.disabled=!!parsed.errors.length;button.setAttribute('aria-label',(active?'Remover ':'Adicionar ')+name(row)+' · '+row.turma);button.addEventListener('click',()=>active?remove(key):add(key));info.append(button);card.append(info);
  if(parsed.errors.length)card.append(el('p','Horário não reconhecido. Confira no SIGAA.','warning'));
  else if(!active&&S.conflicts([...selected,row]).some(c=>S.key(c.b)===key))card.append(el('p','Choque com sua grade','warning'));
  else if(active)card.append(el('p','Na sua grade','added-label'));
  card.addEventListener('dragstart',event=>{dragging=key;dragMode='add';event.dataTransfer.setData('text/plain',key);event.dataTransfer.effectAllowed='copy';$('#calendar-drop').classList.add('dragging');renderCalendar(row);});card.addEventListener('dragend',finishDrag);
  return card;
 }));
}
function finishDrag(){dragging=null;dragMode=null;document.body.classList.remove('removing-course');$('#calendar-drop').classList.remove('dragging');renderCalendar();}
function renderCalendar(preview){
 const conflicts=S.conflicts(selected),all=preview?[...selected,preview]:selected,days=[2,3,4,5,6,7];
 if(all.some(r=>S.parse(r.horario).meetings.some(m=>m.day===1)))days.push(1);
 const calendar=$('#calendar');calendar.replaceChildren();calendar.style.setProperty('--day-count',days.length);calendar.append(el('div','Horário','calendar-corner'));
 days.forEach(day=>calendar.append(el('div',S.DAYS[day],'day-heading')));
 const axis=el('div',undefined,'time-axis');
 for(let m=420;m<=1320;m+=60){const tick=el('span',S.time(m),'time-tick');tick.style.top=((m-420)/920*100)+'%';axis.append(tick);}calendar.append(axis);
 for(const day of days){
  const column=el('div',undefined,'day-column');column.setAttribute('aria-label',S.DAYS[day]);
  for(let m=420;m<=1320;m+=60){const line=el('div',undefined,'hour-line');line.style.top=((m-420)/920*100)+'%';column.append(line);}
  const events=all.flatMap(row=>S.parse(row.horario).meetings.filter(m=>m.day===day).map(m=>({...m,row,preview:row===preview})));
  for(const event of S.layout(events)){
   const {row}=event,clash=selected.some(other=>S.key(other)!==S.key(row)&&S.parse(other.horario).meetings.some(n=>S.overlap(event,n)));
   const block=el('button',undefined,'class-block '+color(row)+(clash?' clash':'')+(event.preview?' preview':''));block.type='button';
   block.draggable=!event.preview;
   block.addEventListener('dragstart',e=>{dragging=S.key(row);dragMode='remove';e.dataTransfer.setData('text/plain',dragging);e.dataTransfer.effectAllowed='move';document.body.classList.add('removing-course');status('Solte fora da grade para remover esta turma. Esc cancela.');});
   block.addEventListener('dragend',()=>{if(dragMode==='remove')status('Turma mantida na grade.');finishDrag();});
   block.style.top=((event.start-420)/920*100)+'%';block.style.height=((event.end-event.start)/920*100)+'%';block.style.left=`calc(${event.lane/event.lanes*100}% + 2px)`;block.style.width=`calc(${100/event.lanes}% - 4px)`;
   block.append(el('strong',name(row)),el('span',row.turma+' · '+S.time(event.start)+'–'+S.time(event.end)));if(clash)block.append(el('b','Choque','clash-label'));
   block.title=`${name(row)} · ${row.turma}\n${S.DAYS[day]} ${S.time(event.start)}–${S.time(event.end)}\n${row.docente}\n${row.local}${clash?'\nChoque de horário':''}\nClique para ver detalhes.`;block.setAttribute('aria-label',block.title);
   block.addEventListener('click',()=>{$('#selected-details').open=true;const target=[...$('#selected-list').children].find(e=>e.dataset.key===S.key(row));if(target){target.scrollIntoView({block:'nearest'});target.querySelector('button').focus({preventScroll:true});}});column.append(block);
  }
  calendar.append(column);
 }
 $('#plan-title').textContent='Minha semana · '+semester;$('#plan-count').textContent=`${selected.length} turma${selected.length===1?' selecionada':'s selecionadas'}`;$('#clear-plan').disabled=!selected.length;$('#export-plan').disabled=!selected.length;
 const unknown=selected.filter(r=>S.parse(r.horario).errors.length),warning=!!conflicts.length||!!unknown.length;
 $('#conflict-status').classList.toggle('has-conflicts',warning);$('#conflict-status').classList.toggle('no-conflicts',!!selected.length&&!warning);
 $('#conflict-status').textContent=unknown.length?'Há horários não reconhecidos. Revise as turmas selecionadas.':conflicts.length?`${conflicts.length} ${conflicts.length===1?'par de turmas com choque':'pares de turmas com choque'} · blocos em vermelho`:selected.length?'Sem choques de horário na sua grade':'Arraste uma turma para a grade ou use o botão Adicionar.';
 $('#conflict-details').hidden=!conflicts.length;$('#conflict-summary').textContent=`Ver ${conflicts.length===1?'o choque de horário':`os ${conflicts.length} choques de horário`}`;
 $('#conflict-list').replaceChildren(...conflicts.map(c=>{const li=el('li');li.append(el('strong',`${name(c.a)} (${c.a.turma}) × ${name(c.b)} (${c.b.turma})`),el('p',c.hits.map(h=>`${S.DAYS[h.day]} ${S.time(h.start)}–${S.time(h.end)}`).join(' / ')));return li;}));
}
function renderSelected(){
 $('#selected-summary').textContent=`Turmas na grade (${selected.length}) · detalhes e remoção`;
 $('#selected-list').replaceChildren(...selected.map(row=>{const item=el('article',undefined,'selected-course '+color(row));item.dataset.key=S.key(row);const text=el('div');text.append(el('h3',name(row)+' · '+row.turma),el('p',S.describe(row.horario)),el('p',`${row.docente} · ${row.local}`,'course-meta'),el('p',row.horario,'course-meta'));const button=el('button','Remover','secondary');button.setAttribute('aria-label','Remover '+name(row)+' '+row.turma);button.addEventListener('click',()=>remove(S.key(row)));item.append(text,button);return item;}));
}
function render(){renderCatalog();renderCalendar();renderSelected();}
async function consult(){
 if(busy)return;busy=true;const filters=Object.fromEntries(new FormData($('#query-form'))),next=filters.year+'.'+filters.period;
 if(next!==semester){semester=next;loadPlan();}
 $('#query-form button').disabled=true;status('Consultando o SIGAA…');rows=[];render();
 try{const result=await api('/api/turmas',filters);rows=result.rows;if(result.units.length){const select=$('[name="unit"]');select.replaceChildren(new Option('Todos os departamentos',''),...result.units.filter(u=>u.value&&u.value!=='0').map(u=>new Option(u.label,u.value)));select.value=filters.unit;}status(`Consulta concluída · ${filters.year}.${filters.period}. Sua grade foi mantida.`);}
 catch(error){status(error.message,true);}
 finally{busy=false;$('#query-form button').disabled=false;render();}
}
$('#calendar-drop').addEventListener('dragover',event=>{if(dragging){event.preventDefault();event.dataTransfer.dropEffect=dragMode==='remove'?'move':'copy';}});
$('#calendar-drop').addEventListener('drop',event=>{event.preventDefault();event.stopPropagation();const key=dragging,mode=dragMode;finishDrag();if(key&&mode==='add')add(key);else if(key)status('Turma mantida no horário original.');});
document.addEventListener('dragover',event=>{if(dragMode==='remove'&&!event.target.closest('#calendar-drop')){event.preventDefault();event.dataTransfer.dropEffect='move';}});
document.addEventListener('drop',event=>{if(dragMode==='remove'&&!event.target.closest('#calendar-drop')){event.preventDefault();const key=dragging;finishDrag();remove(key);}});
$('#clear-plan').addEventListener('click',()=>{selected=[];save();render();status('Grade limpa. Adicione as turmas que quiser.');});
$('#login-form').addEventListener('submit',async event=>{event.preventDefault();const button=$('#login-form button');button.disabled=true;status('Entrando no SIGAA…');try{await api('/api/login',Object.fromEntries(new FormData(event.target)));$('[name="password"]').value='';authenticated(true);await loadUnits();}catch(error){status(error.message,true);}finally{$('[name="password"]').value='';button.disabled=false;}});
$('#query-form').addEventListener('submit',event=>{event.preventDefault();consult();});$('#filter').addEventListener('input',renderCatalog);
$('#logout').addEventListener('click',async()=>{try{await api('/api/logout',{});authenticated(false);status('Você saiu. Sua grade permanece salva neste navegador.');}catch(error){status(error.message,true);}});
api('/api/session').then(async result=>{authenticated(result.authenticated);if(result.authenticated)await loadUnits();}).catch(error=>status(error.message,true));

async function loadUnits(){try{const result=await api('/api/units',{});const select=$('[name=unit]');select.replaceChildren(new Option('Todos os departamentos',''),...result.units.filter(u=>u.value&&u.value!=='0').map(u=>new Option(u.label,u.value)));$('#empty').textContent='Busque por disciplina ou professor para encontrar turmas.';status('Informe os nomes acima e clique em Consultar.');}catch(error){status(error.message,true);}}

// Renderização independente da rolagem e do tamanho da janela, sem enviar dados.
function gradeImage(courses, term) {
 const days=[2,3,4,5,6,7];if(courses.some(r=>S.parse(r.horario).meetings.some(m=>m.day===1)))days.push(1);
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
 const width=1500,margin=40,axis=76,top=154,gridHeight=1104,col=(width-2*margin-axis)/days.length;
 const clashes=S.conflicts(courses),unknown=courses.some(r=>S.parse(r.horario).errors.length);
 const font=(size,bold=false)=>{ctx.font=`${bold?'600':'400'} ${size}px Calibri, sans-serif`;};
 function wrap(text,maxWidth){const lines=[];let line='';for(const word of String(text).split(/\s+/)){if(ctx.measureText(line?line+' '+word:word).width>maxWidth&&line){lines.push(line);line='';}for(const character of word){if(ctx.measureText(line+character).width>maxWidth&&line){lines.push(line);line='';}line+=character;}line+=' ';}if(line.trim())lines.push(line.trim());return lines;}
 font(18,true);
 const legends=courses.map((r,i)=>{font(18,true);const title=wrap(`${i+1}. ${name(r)} · ${r.turma}`,width-2*margin-28);font(16);const details=wrap(`${S.describe(r.horario)} · ${r.docente||''} · ${r.local||''} · ${r.horario}`,width-2*margin-28);return{r,title,details,height:title.length*23+details.length*21+24};});
 const conflictLines=[];font(16);
 for(const c of clashes)conflictLines.push(...wrap(`Choque: ${courses.indexOf(c.a)+1} × ${courses.indexOf(c.b)+1} — ${c.hits.map(h=>`${S.DAYS[h.day]} ${S.time(h.start)}–${S.time(h.end)}`).join('; ')}`,width-2*margin));
 const height=top+gridHeight+64+legends.reduce((n,l)=>n+l.height,0)+conflictLines.length*23+60;
 canvas.width=width*2;canvas.height=height*2;ctx.scale(2,2);ctx.fillStyle='#ffffff';ctx.fillRect(0,0,width,height);ctx.textBaseline='top';
 const text=(value,x,y,size=16,bold=false,color='#292524')=>{font(size,bold);ctx.fillStyle=color;ctx.fillText(value,x,y);};
 text('Minha grade · UFPB',margin,30,30,true);text(`${term} · ${courses.length} turmas`,margin,72,19);
 text(unknown?'Há horários não reconhecidos: confira os detalhes abaixo.':clashes.length?`${clashes.length} par(es) de turmas com choque de horário`:'Sem choques de horário',margin,103,16,false,clashes.length||unknown?'#a32620':'#365d3f');
 ctx.fillStyle='#f4f1ec';ctx.fillRect(margin,top-32,width-2*margin,32);
 days.forEach((day,i)=>text(S.DAYS[day],margin+axis+i*col+10,top-25,16,true));
 for(let m=420;m<=1320;m+=60){const y=top+(m-420)/920*gridHeight;ctx.strokeStyle='#e5e0d8';ctx.beginPath();ctx.moveTo(margin+axis,y);ctx.lineTo(width-margin,y);ctx.stroke();text(S.time(m),margin+8,y+3,13);}
 for(let i=0;i<=days.length;i++){const x=margin+axis+i*col;ctx.strokeStyle='#dedbd5';ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+gridHeight);ctx.stroke();}
 const palette=[['#e9efe3','#708450'],['#f4e9d7','#a17b3d'],['#ece5f2','#9477aa'],['#e0efeb','#548c7d'],['#f1e2e8','#a57286'],['#e9e7de','#8a8466']];
 days.forEach((day,di)=>{
  const events=courses.flatMap((r,index)=>S.parse(r.horario).meetings.filter(m=>m.day===day).map(m=>({...m,r,index})));
  for(const event of S.layout(events)){
   const clash=courses.some(r=>S.key(r)!==S.key(event.r)&&S.parse(r.horario).meetings.some(m=>S.overlap(event,m)));
   const [bg,border]=clash?['#ffe5e0','#bc3f35']:palette[Number(color(event.r).slice(-1))];
   const x=margin+axis+di*col+event.lane/event.lanes*col+3,y=top+(event.start-420)/920*gridHeight+2,w=col/event.lanes-6,h=(event.end-event.start)/920*gridHeight-4;
   ctx.fillStyle=bg;ctx.fillRect(x,y,w,h);ctx.strokeStyle=border;ctx.strokeRect(x,y,w,h);
   ctx.save();ctx.beginPath();ctx.rect(x+4,y+3,Math.max(0,w-8),h-6);ctx.clip();
   text(`${event.index+1}${clash?' · CHOQUE':''}`,x+7,y+6,13,true,clash?'#a32620':'#292524');font(14,true);
   const lines=wrap(name(event.r),Math.max(10,w-14));const maxLines=Math.max(1,Math.floor((h-56)/17));
   lines.slice(0,maxLines).forEach((line,i)=>text(line+(i===maxLines-1&&lines.length>maxLines?'…':''),x+7,y+26+i*17,14,true));
   text(`${S.time(event.start)}–${S.time(event.end)}`,x+7,y+h-22,12);ctx.restore();
  }
 });
 let y=top+gridHeight+30;text('Disciplinas e horários',margin,y,22,true);y+=34;
 for(const entry of legends){const [,border]=palette[Number(color(entry.r).slice(-1))];ctx.fillStyle=border;ctx.fillRect(margin,y,4,entry.height-16);for(const line of entry.title){text(line,margin+16,y,18,true);y+=23;}for(const line of entry.details){text(line,margin+16,y,16);y+=21;}y+=24;}
 for(const line of conflictLines){text(line,margin,y,16,false,'#a32620');y+=23;}
 text('Planejamento pessoal · não substitui a matrícula no SIGAA.',margin,y+16,14,false,'#71675d');
 return canvas;
}
$('#export-plan').addEventListener('click',async()=>{
 const button=$('#export-plan');if(!selected.length)return;button.disabled=true;
 try{await document.fonts.ready;const canvas=gradeImage([...selected],semester);const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error()),'image/png'));const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`minha-grade-ufpb-${semester}.png`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);status('Imagem PNG gerada. Confira os downloads do navegador.');}
 catch{status('Não foi possível gerar a imagem. Tente novamente.',true);}
 finally{button.disabled=!selected.length;}
});
