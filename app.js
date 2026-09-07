const { $, el, name, color } = FrontendDom;
const S = Schedule;
let rows = [], selected = [], semester = '2026.2', dragging = null, dragMode = null, busy = false;
let viewingShared = false, isAuthenticated = false, homeSemester = semester;
const planStore = PlanStore.createPlanStore({ key: S.key });
function status(message,error=false){$('#status').textContent=message;$('#status').classList.toggle('error',error);}
function save(){if(!planStore.save(semester,selected))$('#save-note').textContent=PlanStore.SAVE_ERROR;}
function loadPlan(){selected=planStore.load(semester);}
function authenticated(value){isAuthenticated=value;if(sharing.active){$('#logout').hidden=!value;sharing.refresh();return;}$('#login-panel').hidden=value;$('#query-panel').hidden=!value;$('#logout').hidden=!value;if(value)loadPlan();else{rows=[];selected=[];}render();}
const api = ApiClient.createApi({ onUnauthorized: () => authenticated(false) }).request;
function remove(key){selected=selected.filter(r=>S.key(r)!==key);save();render();status('Item removido da grade.');}
function add(key){const row=rows.find(r=>S.key(r)===key);if(!row||selected.some(r=>S.key(r)===key))return;if(row.periodo!==semester||S.parse(row.horario).errors.length){status('Confira o horário e o período desta turma.',true);return;}selected.push(row);save();render();const hits=S.conflicts(selected).filter(c=>S.key(c.a)===key||S.key(c.b)===key);status(hits.length?'Turma adicionada com choque. Confira os detalhes abaixo da grade.':'Turma adicionada: '+S.describe(row.horario),!!hits.length);}
function renderCatalog(){
 const visible=CourseFilter.filter(rows,$('#filter').value,$('#shift-filter').value,S);
 $('#count').textContent=`${visible.length} turma${visible.length===1?' disponível':'s disponíveis'}`;
 $('#empty').hidden=!!visible.length;$('#empty').textContent=busy?'Consultando turmas…':$('#filter').value||$('#shift-filter').value?'Nenhuma turma corresponde aos filtros.':'Nenhuma turma encontrada nesta consulta.';
 $('#courses').replaceChildren(...visible.map(row=>{
  const key=S.key(row),active=selected.some(r=>S.key(r)===key),parsed=S.parse(row.horario),card=el('article',undefined,'course '+color(row));
  card.draggable=!active&&!parsed.errors.length;card.classList.toggle('in-plan',active);
  card.append(el('h3',name(row)),el('p',row.turma+' · '+row.docente,'course-meta'),el('p',S.describe(row.horario),'readable-time'));
  const info=el('div',undefined,'course-footer');info.append(el('span',row.horario+' · '+row.vagas,'course-meta'));
  const button=el('button',active?'Remover':'Adicionar',active?'secondary':'');button.type='button';button.disabled=!!parsed.errors.length;button.setAttribute('aria-label',(active?'Remover ':'Adicionar ')+name(row)+' · '+S.label(row));button.addEventListener('click',()=>active?remove(key):add(key));info.append(button);card.append(info);
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
   block.draggable=!viewingShared&&!event.preview;
   block.addEventListener('dragstart',e=>{dragging=S.key(row);dragMode='remove';e.dataTransfer.setData('text/plain',dragging);e.dataTransfer.effectAllowed='move';document.body.classList.add('removing-course');status('Solte fora da grade para remover este item. Esc cancela.');});
   block.addEventListener('dragend',()=>{if(dragMode==='remove')status('Item mantido na grade.');finishDrag();});
   block.style.top=((event.start-420)/920*100)+'%';block.style.height=((event.end-event.start)/920*100)+'%';block.style.left=`calc(${event.lane/event.lanes*100}% + 2px)`;block.style.width=`calc(${100/event.lanes}% - 4px)`;
   block.append(el('strong',name(row)),el('span',S.label(row)+' · '+S.time(event.start)+'–'+S.time(event.end)));if(clash)block.append(el('b','Choque','clash-label'));
   block.title=`${name(row)} · ${S.label(row)}\n${S.DAYS[day]} ${S.time(event.start)}–${S.time(event.end)}\n${row.docente||''}\n${row.local||''}${clash?'\nChoque de horário':''}\nClique para ver detalhes.`;block.setAttribute('aria-label',block.title);
   block.addEventListener('click',()=>{$('#selected-details').open=true;const target=[...$('#selected-list').children].find(e=>e.dataset.key===S.key(row));if(target){target.scrollIntoView({block:'nearest'});(target.querySelector('button')||target).focus({preventScroll:true});}});column.append(block);
  }
  calendar.append(column);
 }
 $('#plan-title').textContent=(viewingShared?'Semana compartilhada · ':'Minha semana · ')+semester;$('#share-plan').disabled=!selected.length;$('#plan-count').textContent=S.counts(selected);$('#clear-plan').disabled=!selected.length;$('#export-plan').disabled=!selected.length;
 const unknown=selected.filter(r=>S.parse(r.horario).errors.length),warning=!!conflicts.length||!!unknown.length;
 $('#conflict-status').classList.toggle('has-conflicts',warning);$('#conflict-status').classList.toggle('no-conflicts',!!selected.length&&!warning);
 $('#conflict-status').textContent=unknown.length?'Há horários não reconhecidos. Revise as turmas selecionadas.':conflicts.length?`${conflicts.length} ${conflicts.length===1?'par de atividades com choque':'pares de atividades com choque'} · blocos em vermelho`:selected.length?'Sem choques de horário na sua grade':'Adicione uma turma ou compromisso para começar.';
 $('#conflict-details').hidden=!conflicts.length;$('#conflict-summary').textContent=`Ver ${conflicts.length===1?'o choque de horário':`os ${conflicts.length} choques de horário`}`;
 $('#conflict-list').replaceChildren(...conflicts.map(c=>{const li=el('li');li.append(el('strong',`${name(c.a)} (${S.label(c.a)}) × ${name(c.b)} (${S.label(c.b)})`),el('p',c.hits.map(h=>`${S.DAYS[h.day]} ${S.time(h.start)}–${S.time(h.end)}`).join(' / ')));return li;}));
}
function renderSelected(){
 $('#selected-summary').textContent=`Itens na grade (${S.counts(selected)}) · ${viewingShared?'detalhes':'detalhes e remoção'}`;
 $('#selected-list').replaceChildren(...selected.map(row=>{const item=el('article',undefined,'selected-course '+color(row));item.dataset.key=S.key(row);item.tabIndex=-1;const text=el('div');text.append(el('h3',name(row)+' · '+S.label(row)),el('p',S.describe(row.horario)),el('p',row.type==='commitment'?'Toda semana':`${row.docente} · ${row.local}`,'course-meta'),el('p',row.horario,'course-meta'));if(row.type!=='commitment')text.append(el('p',`Período ${row.periodo} · ${row.tipo||''} · ${row.forma||''}`,'course-meta'));if(viewingShared){item.append(text);return item;}const button=el('button','Remover','secondary');button.setAttribute('aria-label','Remover '+name(row)+' '+S.label(row));button.addEventListener('click',()=>remove(S.key(row)));item.append(text);if(row.type==='commitment'){const edit=el('button','Editar','secondary');edit.setAttribute('aria-label','Editar '+name(row));edit.addEventListener('click',()=>openCommitment(row));item.append(edit);}item.append(button);return item;}));
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
$('#calendar-drop').addEventListener('drop',event=>{event.preventDefault();event.stopPropagation();const key=dragging,mode=dragMode;finishDrag();if(key&&mode==='add')add(key);else if(key)status('Item mantido no horário original.');});
document.addEventListener('dragover',event=>{if(dragMode==='remove'&&!event.target.closest('#calendar-drop')){event.preventDefault();event.dataTransfer.dropEffect='move';}});
document.addEventListener('drop',event=>{if(dragMode==='remove'&&!event.target.closest('#calendar-drop')){event.preventDefault();const key=dragging;finishDrag();remove(key);}});
$('#clear-plan').addEventListener('click',()=>{selected=[];save();render();status('Grade limpa. Adicione turmas ou compromissos.');});
$('#login-form').addEventListener('submit',async event=>{event.preventDefault();const button=$('#login-form button');button.disabled=true;status('Entrando no SIGAA…');try{await api('/api/login',Object.fromEntries(new FormData(event.target)));$('[name="password"]').value='';authenticated(true);if(sharing.active)await sharing.afterLogin();else await loadUnits();}catch(error){status(error.message,true);}finally{$('[name="password"]').value='';button.disabled=false;}});
$('#query-form').addEventListener('submit',event=>{event.preventDefault();consult();});$('#filter').addEventListener('input',renderCatalog);$('#shift-filter').addEventListener('change',renderCatalog);
$('#logout').addEventListener('click',async()=>{try{await api('/api/logout',{});authenticated(false);status('Você saiu. Sua grade permanece salva neste navegador.');}catch(error){status(error.message,true);}});


async function loadUnits(){try{const result=await api('/api/units',{});const select=$('[name=unit]');select.replaceChildren(new Option('Todos os departamentos',''),...result.units.filter(u=>u.value&&u.value!=='0').map(u=>new Option(u.label,u.value)));$('#empty').textContent='Busque por disciplina ou professor para encontrar turmas.';status('Informe os nomes acima e clique em Consultar.');}catch(error){status(error.message,true);}}

$('#export-plan').addEventListener('click',async()=>{
 const button=$('#export-plan');if(!selected.length)return;button.disabled=true;
 try{await document.fonts.ready;const canvas=GradeImage.render([...selected],semester);const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error()),'image/png'));const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`minha-grade-ufpb-${semester}.png`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);status('Imagem PNG gerada. Confira os downloads do navegador.');}
 catch{status('Não foi possível gerar a imagem. Tente novamente.',true);}
 finally{button.disabled=!selected.length;}
});

let editingCommitment = null;
function commitmentBlock(codes = []) {
 const group = el('fieldset');
 group.append(el('legend', 'Horário semanal'));
 const days = el('div', undefined, 'commitment-choices');
 for (const day of [2,3,4,5,6,7,1]) {
  const label = el('label'), input = el('input');
  input.type = 'checkbox'; input.name = 'day'; input.value = day;
  input.checked = codes.some(code => code[0] === String(day));
  label.append(input, document.createTextNode(S.DAYS[day])); days.append(label);
 }
 group.append(days);
 for (const [shift, slots] of Object.entries(S.TIMES)) {
  const choices = el('div', undefined, 'commitment-choices');
  slots.forEach(([start,end], index) => {
   const label = el('label'), input = el('input'), slot = shift + (index+1);
   input.type = 'checkbox'; input.name = 'slot'; input.value = slot;
   input.checked = codes.some(code => code.slice(1) === slot);
   label.append(input, document.createTextNode(`${slot} · ${S.time(start)}–${S.time(end)}`)); choices.append(label);
  });
  group.append(choices);
 }
 const remove = el('button','Remover horário','secondary'); remove.type = 'button';
 remove.addEventListener('click',()=>group.remove()); group.append(remove);
 $('#commitment-blocks').append(group);
}
function openCommitment(row) {
 editingCommitment = row || null;
 $('#commitment-form').reset(); $('#commitment-error').textContent = '';
 $('#commitment-title').textContent = row ? 'Editar compromisso pessoal' : 'Novo compromisso pessoal';
 $('#commitment-semester').textContent = semester;
 $('#commitment-name').value = row?.nome || '';
 $('#commitment-blocks').replaceChildren();
 if (row) {
  const byDay = new Map();
  for (const code of row.horario.split(' ')) {
   if (!byDay.has(code[0])) byDay.set(code[0], []);
   byDay.get(code[0]).push(code);
  }
  for (const codes of byDay.values()) commitmentBlock(codes);
 } else commitmentBlock();
 $('#commitment-dialog').showModal(); $('#commitment-name').focus();
}
$('#new-commitment').addEventListener('click',()=>openCommitment());
$('#add-commitment-block').addEventListener('click',()=>commitmentBlock());
$('#cancel-commitment').addEventListener('click',()=>$('#commitment-dialog').close());
$('#commitment-form').addEventListener('submit',event=>{
 event.preventDefault();
 const nome = $('#commitment-name').value.trim(), codes = new Set();
 let incomplete = false;
 for (const group of $('#commitment-blocks').children) {
  const days = [...group.querySelectorAll('[name=day]:checked')];
  const slots = [...group.querySelectorAll('[name=slot]:checked')];
  if (!days.length || !slots.length) incomplete = true;
  for (const day of days) for (const slot of slots) codes.add(day.value + slot.value);
 }
 if (!nome || !codes.size || incomplete) {
  $('#commitment-error').textContent = 'Informe um nome e selecione dias e blocos em cada horário.'; return;
 }
 const row = {type:'commitment', id:editingCommitment?.id || crypto.randomUUID(), nome, periodo:semester, horario:[...codes].sort().join(' ')};
 selected = editingCommitment ? selected.map(item=>S.key(item)===S.key(editingCommitment)?row:item) : [...selected,row];
 save(); render(); $('#commitment-dialog').close();
 const clash = S.conflicts(selected).some(c=>c.a===row||c.b===row);
 status(clash?'Compromisso salvo com choque. Confira os detalhes abaixo da grade.':'Compromisso salvo.',clash);
});

const weekPanel = $('.week-panel');
const sharing = ShareUI.create({
 getPlan: () => ({ periodo: semester, items: selected }),
 store: planStore, api, notify: status,
 onAuthenticated: authenticated,
 onView(plan, error) {
  if (!viewingShared) homeSemester = semester;
  viewingShared = true;
  $('#commitment-dialog').close(); finishDrag();
  $('#query-panel').hidden = true; $('#login-panel').hidden = true;
  $('#shared-view').hidden = !plan; $('#shared-error').hidden = !!plan;
  $('#shared-error-message').textContent = error || '';
  $('#shared-week').append(weekPanel);
  for (const id of ['new-commitment','share-plan','clear-plan','save-note']) $('#' + id).hidden = true;
  selected = plan ? plan.items.map((item, index) => item.type === 'commitment' ? {...item, id: 'shared-' + index} : item) : [];
  if (plan) semester = plan.periodo;
  render();
 },
 onHome() {
  if (viewingShared) semester = homeSemester;
  viewingShared = false;
  $('#shared-view').hidden = true; $('#shared-error').hidden = true;
  $('.planner').append(weekPanel);
  for (const id of ['new-commitment','share-plan','clear-plan','save-note']) $('#' + id).hidden = false;
  authenticated(isAuthenticated);
 },
 onLogin() {
  $('#shared-view').hidden = true; $('#login-panel').hidden = false;
  status('Entre no SIGAA para revisar a cópia. Sua grade só será alterada após confirmação.');
  $('[name=username]').focus();
 },
 onImported(periodo, items) {
  semester = periodo; selected = items; rows = [];
  const [year, period] = periodo.split('.');
  $('[name=year]').value = year; $('[name=period]').value = period;
  $('#save-note').textContent = 'Sua grade fica salva neste navegador, separada por semestre.';
  render();
 },
});
sharing.start();
api('/api/session').then(async result => {
 authenticated(result.authenticated);
 if (result.authenticated && !sharing.active) await loadUnits();
 else if (result.expired && !sharing.active) status('Sua sessão expirou. Entre novamente.', true);
}).catch(error => status(error.message, true));
