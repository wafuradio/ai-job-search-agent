'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name=review-token]').content;
let data = null, current = null;
let sources = null, importDraft = null;
const el = (tag, text, cls) => {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
async function request(url, options={}) {const response=await fetch(url,options);const value=await response.json();if(!response.ok)throw new Error(value.error || 'Could not load the dashboard');return value;}
function error(message) {$('error').hidden=!message;$('error').textContent=message;}
function post(url,body){return request(url,{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify({candidate_id:data.candidate_id,...body})});}
async function section(name){
  for(const key of ['jobs','add','sources']){$('panel-'+key).hidden=key!==name;$('tab-'+key).classList.toggle('primary',key===name);$('tab-'+key).setAttribute('aria-pressed',String(key===name));}
  error('');if(name==='sources')await loadSources();
}
for(const name of ['jobs','add','sources'])$('tab-'+name).addEventListener('click',()=>section(name));
async function loadSources(){
  try{const [settings,searches]=await Promise.all([request('/api/sources'),request('/api/searches')]);sources=settings;
    $('source-list').replaceChildren();
    for(const source of settings.sources){
      const card=el('article');card.append(el('h3',source.company),el('span',source.mode==='automatic'?(source.active?'Automatic · enabled':'Automatic · paused / disabled'):(source.enabled?'Assisted search':'Assisted search · paused'),'badge'),el('p',source.description));
      const actions=el('div',undefined,'source-actions'),link=el('a','Open source ↗');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';actions.append(link);
      if(source.editable){const button=el('button',source.enabled?'Pause source':'Enable source');button.addEventListener('click',async()=>{button.disabled=true;try{await post('/api/sources',{version:sources.version,source_id:source.id,enabled:!source.enabled});await loadSources();}catch(e){error(e.message);button.disabled=false;}});actions.append(button);}card.append(actions);$('source-list').append(card);
    }
    $('search-links').replaceChildren();const groups=new Map();
    for(const item of searches.links){if(!groups.has(item.group)){const box=el('section'),list=el('ul');box.append(el('h3',item.group),list);groups.set(item.group,list);$('search-links').append(box);}const li=el('li'),link=el('a',item.term);link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';li.append(link);groups.get(item.group).append(li);}
  }catch(e){error(e.message);}
}
$('employer-form').addEventListener('submit',async event=>{event.preventDefault();if(!data||!sources)return;
  $('save-employer').disabled=true;$('employer-message').textContent='Saving source…';
  try{const result=await post('/api/sources',{version:sources.version,company:$('employer-name').value,url:$('employer-url').value});
    const name=$('employer-name').value;const added=result.sources.find(s=>s.company===name.trim());
    $('employer-message').textContent=added?.mode==='automatic'?'Source saved for scheduled discovery. No postings fetched yet.':'Assisted source saved. Use its searches, then add selected postings.';
    $('employer-form').reset();await loadSources();
  }catch(e){$('employer-message').textContent=e.message;}finally{$('save-employer').disabled=false;}
});
function postingFields(){return {company:$('add-company').value,title:$('add-title').value,job_url:$('add-url').value,copied_from:$('add-origin').value,location_text:$('add-location').value||null,remote_status:$('add-work').value||null,employment_type:$('add-employment').value||null,compensation_text:$('add-compensation').value||null,raw_description:$('add-description').value};}
$('posting-form').addEventListener('input',()=>{importDraft=null;$('import-preview').hidden=true;$('confirm-import').checked=false;$('save-posting').disabled=true;});
$('posting-form').addEventListener('submit',async event=>{event.preventDefault();if(!data)return;
  $('preview-posting').disabled=true;$('import-message').textContent='Preparing preview…';
  try{const job=postingFields(),result=await post('/api/import/preview',{job});
    importDraft={job,preview:result.existing?{is_new:false,revision:result.existing.revision,updated_at:result.existing.updated_at}:{is_new:true}};
    $('import-summary').replaceChildren(el('p',result.job.company+' · '+result.job.title),el('p','Saved link: '+result.job.job_url),el('p',result.screening.accepted?'Passes initial screening; ready for your review.':'Screened out: '+result.screening.reasons.join(' ')),el('p','Relevance: '+result.screening.score+' (not an AI fit score)'));
    for(const flag of result.screening.flags)$('import-summary').append(el('p',flag));
    if(result.existing)$('import-summary').append(el('p',`This updates saved job #${result.existing.id} (${result.existing.status}). Its review history is preserved. Material changes revoke approval and require reevaluation.`));
    $('import-preview').hidden=false;$('confirm-import').checked=false;$('save-posting').disabled=true;$('import-message').textContent='Preview ready. Nothing has been saved yet.';
  }catch(e){$('import-message').textContent=e.message;}finally{$('preview-posting').disabled=false;}
});
$('confirm-import').addEventListener('change',()=>$('save-posting').disabled=!$('confirm-import').checked||!importDraft);
$('save-posting').addEventListener('click',async()=>{if(!importDraft||!$('confirm-import').checked)return;$('save-posting').disabled=true;
  try{const result=await post('/api/import',{...importDraft,confirmed:true});
    importDraft=null;$('import-preview').hidden=true;$('posting-form').reset();
    $('import-message').textContent=`Saved job #${result.job_id} · ${result.status}. `+(result.accepted?'Available in your review queue.':'Saved under All saved postings; it did not pass initial screening.')+(result.needs_reevaluation?' Reevaluation is required.':'');
    await load();await openJob(result.job_id);
  }catch(e){$('import-message').textContent=e.message+' Preview again before saving.';}
});
async function load() {
  $('refresh').disabled=true;error('');
  try {data=await request('/api/jobs');$('candidate').textContent=`${data.candidate_name} · private local review`;
    $('stats').replaceChildren();
    for(const [label,value] of [['Saved postings',data.jobs.length],['Screening survivors',data.jobs.filter(j=>j.screening.accepted).length],['Interested',data.jobs.filter(j=>j.status==='Interested').length],['Need reevaluation',data.jobs.filter(j=>j.needs_reevaluation).length]]) {
      const box=el('div',undefined,'stat');box.append(el('strong',String(value)),el('span',label));$('stats').append(box);
    }render();
  } catch(e){error(e.message);}finally{$('refresh').disabled=false;}
}
function render() {
  if(!data)return;
  const query=$('search').value.trim().toLowerCase(), status=$('status').value, work=$('work').value;
  const rows=data.jobs.filter(j=>($('scope').value==='all'||(j.screening.accepted && j.status!=='Rejected'))&&(!status||j.status===status)&&(!work||j.work_model.toLowerCase().includes(work))&&(!$('changed').checked||j.needs_reevaluation)&&(!query||`${j.company} ${j.title} ${j.location} ${j.source}`.toLowerCase().includes(query)));
  $('count').textContent=`${rows.length} opportunities shown · ${data.jobs.length} saved`;
  $('jobs').replaceChildren();
  for(const job of rows){
    const card=el('article'),top=el('div',undefined,'card-top');
    top.append(el('span',job.company,'company'),el('span',job.status,'badge'+(job.status==='Interested'?' interested':'')));
    card.append(top,el('h2',job.title),el('p',`${job.location} · ${job.work_model}`,'meta'),el('p',job.compensation,'meta'),el('p',`${job.source} · relevance ${job.screening.score}`,'meta'));
    if(job.dates.length)card.append(el('p',job.dates[0].trim(),'meta'));
    const priority=job.screening.priority || {};
    if(priority.band && priority.band!=='unconfigured')card.append(el('span',priority.band.replaceAll('_',' '),'badge'));
    card.append(el('p',job.needs_reevaluation?'Posting changed—reevaluation required.':(priority.reason||job.screening.reasons.join(' ')||'Ready for your review.'),'evidence'));
    const bottom=el('div',undefined,'card-bottom'),button=el('button','Review opportunity','primary');button.addEventListener('click',()=>openJob(job.id));bottom.append(button);card.append(bottom);$('jobs').append(card);
  }
  if(!rows.length)$('jobs').append(el('p','No opportunities match these filters. Try All saved postings or clear a filter.','empty'));
}
async function openJob(id,keepMessage=false){
  try {const record=await request('/api/jobs/'+id);current=record;
    const listRow=data.jobs.find(j=>j.id===id);
    $('detail-title').textContent=record.job.title;$('detail-company').textContent=record.job.company+' · '+(record.job.location_text||'Location unknown');
    $('detail-source').textContent=record.job.source;$('detail-status').textContent='Review: '+record.status;
    $('detail-dates').textContent=record.dates.map(x=>x.trim()).join('\n');$('reevaluation').hidden=!record.needs_reevaluation;
    $('description').textContent=record.job.raw_description||'Description not supplied';
    $('notes').value='';if(!keepMessage)$('save-message').textContent='';
    const url=new URL(record.job.job_url,location.origin);$('posting').hidden=!['https:','http:'].includes(url.protocol);$('posting').href=$('posting').hidden?'#':url.href;
    $('evidence').replaceChildren();
    if(listRow){const screen=listRow.screening;for(const text of [...screen.reasons,...screen.flags,...(screen.priority?.questions||[])])$('evidence').append(el('p',text));const matches=[...(screen.matches.role_terms||[]),...(screen.matches.positive_signals||[])];$('evidence').prepend(el('p','Matched signals: '+(matches.join(', ')||'None')));}
    $('history').replaceChildren();
    for(const event of record.history.slice().reverse()){
      let text=event.event.replaceAll('_',' ');
      if(event.details.status)text+=' → '+event.details.status;
      if(event.details.approval_revoked)text+=' · previous approval revoked';
      if(event.details.notes)text+='\n'+event.details.notes;
      $('history').append(el('li',event.created_at+' · '+text));
    }
    if(!$('detail').open)$('detail').showModal();
  }catch(e){error(e.message);}
}
async function save(action,status){
  if(!current)return;
  const buttons=[...document.querySelectorAll('.actions button')];buttons.forEach(b=>b.disabled=true);
  $('save-message').textContent='Saving…';
  try {
    await request('/api/review',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify({candidate_id:data.candidate_id,job_id:current.id,revision:current.revision,updated_at:current.updated_at,action,status,notes:$('notes').value})});
    $('save-message').textContent=action==='note'?'Note saved. Review status preserved.':'Review decision saved.';
    await load();await openJob(current.id,true);
  }catch(e){$('save-message').textContent=e.message+' Your unsaved note is still here. Close and reopen the job to reload.';}
  finally{buttons.forEach(b=>b.disabled=false);}
}
for(const id of ['search','scope','status','work','changed'])$(id).addEventListener('input',()=>{if(id==='status'&&['Rejected','Interested','Approved to Apply'].includes($('status').value))$('scope').value='all';render();});
$('refresh').addEventListener('click',()=>{if($('detail').open)$('detail').close();load();});
$('close').addEventListener('click',()=>$('detail').close());
$('interested').addEventListener('click',()=>save('status','Interested'));
$('rejected').addEventListener('click',()=>save('status','Rejected'));
$('reset').addEventListener('click',()=>save('status','New'));
$('save-note').addEventListener('click',()=>save('note'));
load();
