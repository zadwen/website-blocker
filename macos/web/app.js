'use strict';
const $ = id => document.getElementById(id);
let key = '', state = null, busy = false;
const dayNames = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
dayNames.forEach((day,i) => { const label=document.createElement('label'), input=document.createElement('input'); input.type='checkbox'; input.value=i; input.checked=i<5; label.append(input,day); $('days').append(label); });
function message(text=''){ $('message').textContent=text; }
async function api(path, body){
  const response=await fetch('/api/'+path, {method:body?'POST':'GET',headers:{Authorization:'Bearer '+key,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000),cache:'no-store'});
  const data=await response.json(); if(!response.ok) throw Error(data.error||'Connection failed'); return data;
}
function render(next){
  state=next; $('login').hidden=true; $('dashboard').hidden=false; $('logout').hidden=false;
  const count=state.rules.filter(r=>r.active).length;
  $('status').textContent=!state.health.ok?'Needs attention':state.paused?'Taking a break':count?'Distractions blocked':'Ready to focus';
  $('health').textContent=state.health.ok?`${count} active rules · Mac time: ${state.timezone} · Connected`:`Protection error: ${state.health.error}`;
  $('pause').textContent=state.paused?'Resume all blocks':'Pause all blocks'; $('count').textContent=state.rules.length+' rules'; $('empty').hidden=state.rules.length>0;
  $('rules').replaceChildren();
  for(const rule of state.rules){
    const item=document.createElement('article'); item.className='rule';
    const title=document.createElement('strong'); title.textContent=rule.domain;
    const detail=document.createElement('p');
    let duration='Until you remove it';
    if(rule.mode==='timer') duration=rule.expires<=state.now?'Timer expired':Math.ceil((rule.expires-state.now)/60)+' min remaining';
    if(rule.mode==='schedule') duration=`${rule.start}–${rule.end} · ${rule.days.map(d=>dayNames[d]).join(', ')} (${state.timezone})`;
    detail.textContent=`${rule.active?'Blocking':state.paused||!rule.enabled?'Paused':'Inactive'} · ${duration}`;
    const actions=document.createElement('div'); actions.className='actions';
    const toggle=document.createElement('button'); toggle.className='quiet'; toggle.textContent=rule.enabled?'Pause':'Enable'; toggle.addEventListener('click',()=>mutate('toggle',{id:rule.id,enabled:!rule.enabled}));
    const remove=document.createElement('button'); remove.className='quiet'; remove.textContent='Remove'; remove.addEventListener('click',()=>mutate('remove',{id:rule.id}));
    actions.append(toggle,remove); item.append(title,detail,actions); $('rules').append(item);
  }
}
async function mutate(path,body){
  if(busy)return; busy=true; message(); document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try {render(await api(path,body));}catch(error){message(error.message+' — refresh status before retrying if the connection was lost.');}
  finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
$('connect').addEventListener('submit',async e=>{e.preventDefault();key=$('key').value.trim();message();try{render(await api('status'));$('key').value='';}catch(error){key='';message(error.message);}});
$('logout').addEventListener('click',()=>{key='';state=null;$('dashboard').hidden=true;$('login').hidden=false;$('logout').hidden=true;message();});
$('mode').addEventListener('change',()=>{$('timer-fields').hidden=$('mode').value!=='timer';$('schedule-fields').hidden=$('mode').value!=='schedule';});
$('add').addEventListener('submit',e=>{e.preventDefault();const body={domain:$('domain').value,mode:$('mode').value};if(body.mode==='timer')body.minutes=Number($('minutes').value);if(body.mode==='schedule')Object.assign(body,{start:$('start').value,end:$('end').value,days:[...$('days').querySelectorAll('input:checked')].map(e=>Number(e.value))});mutate('add',body);});
$('pause').addEventListener('click',()=>mutate('pause',{paused:!state.paused}));
document.querySelectorAll('.preset').forEach(button=>button.addEventListener('click',()=>mutate('add',button.dataset.preset?{preset:button.dataset.preset}:{domain:button.dataset.domain})));
setInterval(async()=>{if(!key||busy)return;try{render(await api('status'));message();}catch(error){$('status').textContent='Mac unreachable';$('health').textContent='Status is stale. Existing rules stay on the Mac. Reconnect to confirm changes.';message(error.message);}},10000);
