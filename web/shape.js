const el=id=>document.getElementById(id);
const safe=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let model, selected='';
async function request(change){
  const response=await fetch('/api/shape',change?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(change)}:{});
  const body=await response.json();
  if(!response.ok)throw Error(body.error||'Unable to save.');
  model=body;el('msg').textContent='';draw();
}
function profile(field){
  const count=model.domains.filter(d=>d[field]>=4).length;
  return count===0?'Building breadth':count===1?'T-shaped':count===2?'π-shaped':'Comb-shaped';
}
function openGoal(d){
  const form=el('goal');form.domain.value=d?.domain||'';form.domain.readOnly=!!d;form.elements.namedItem('target').value=d?.target||3;el('editor').showModal();
}
function draw(){
  el('profile').textContent='Current · '+profile('current')+'     /     Target · '+profile('target');
  el('chart').innerHTML=model.domains.map((d,i)=>'<div class="row"><button data-index="'+i+'">'+safe(d.domain)+'</button>'+[1,2,3,4,5].map(n=>'<span aria-hidden="true" class="cell '+(n<=d.current?'':n<=d.target?'planned':'blank')+'"></span>').join('')+'<small>L'+d.current+' / L'+d.target+'</small></div>').join('')||'<p>Add a domain to start your map. Indexed domains also appear here automatically.</p>';
  const d=model.domains.find(d=>d.domain===selected)||model.domains[0];
  const path=el('path');
  if(!d){path.hidden=true;return}path.hidden=false;selected=d.domain;
  const next=d.current+1,goalMet=next>d.target;
  path.innerHTML='<div class="bar"><h2>'+safe(d.domain)+'</h2><button id="edit">Edit target</button></div><ol>'+model.levels.slice(0,d.target).map(([title,prompt],i)=>'<li><strong>'+safe(title)+'</strong> · '+(i<d.current?'Assessed':i+1===next?'Next assessment':'Upcoming')+'<br>'+safe(d.lessons[i+1]?.task||prompt)+(d.lessons[i+1]?' · <a href="/api/original?id='+encodeURIComponent(d.lessons[i+1].document)+'#page='+encodeURIComponent(d.lessons[i+1].label.replace(/^Page /,''))+'">'+safe(d.lessons[i+1].label)+'</a>':'')+'</li>').join('')+'</ol>'+
    (goalMet?'<p>You have met this target.</p>':'<form id="assessment"><label>Evidence for L'+next+' · '+safe(model.levels[next-1][0])+'<textarea required name="response" placeholder="Use a source, worked example, or case decision."></textarea></label><label>Self-assessment<select name="result"><option value="review">Needs another attempt</option><option value="pass">My evidence meets the criterion</option></select></label><button>Save assessment</button></form>')+
    (d.history.length?'<details><summary>Assessment history ('+d.history.length+')</summary>'+d.history.map(h=>'<p><b>L'+h.level+' · '+(h.passed?'Met':'Review')+'</b><br>'+safe(h.response)+'</p>').join('')+'</details>':'');
  el('edit').onclick=()=>openGoal(d);
  if(!goalMet)el('assessment').onsubmit=async e=>{
    e.preventDefault();const f=e.target;f.querySelector('button').disabled=true;
    try{await request({action:'assess',domain:d.domain,level:next,passed:f.result.value==='pass',response:f.response.value})}catch(err){alert(err.message);f.querySelector('button').disabled=false}
  };
}
el('chart').onclick=e=>{const b=e.target.closest('[data-index]');if(b){selected=model.domains[Number(b.dataset.index)].domain;draw();el('path').scrollIntoView({behavior:'smooth'})}};
el('add').onclick=()=>openGoal();el('cancel').onclick=()=>el('editor').close();
el('goal').onsubmit=async e=>{e.preventDefault();const f=e.target;try{selected=f.domain.value.trim();await request({action:'goal',domain:selected,target:Number(f.elements.namedItem('target').value)});el('editor').close()}catch(err){alert(err.message)}};
request().catch(err=>el('msg').textContent=err.message);
