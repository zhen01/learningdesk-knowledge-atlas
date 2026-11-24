/* Deterministic non-overlapping domain lanes, plus a one-hop focus view. */
let graphDomain='',graphFocus=null,graphCross=false,graphLinked=false;
function layoutGraph(nodes,domainFor,getName){
  const groups=new Map();
  for(const n of nodes){const d=domainFor(n.id)||'other';if(!groups.has(d))groups.set(d,[]);groups.get(d).push(n)}
  const points=new Map(),panels=[];let y=28;const cols=Math.min(3,Math.max(1,Math.ceil(Math.sqrt(nodes.length/2)))),w=cols*258+28;
  for(const [id,list] of groups){
    list.sort((a,b)=>a.name.localeCompare(b.name));const height=68+Math.ceil(list.length/cols)*83;
    panels.push({id,name:getName(id)||'Other concepts',x:24,y,w,h:height});
    list.forEach((n,i)=>points.set(n.id,{x:42+(i%cols)*258,y:y+51+Math.floor(i/cols)*83,w:232,h:60,domain:id}));
    y+=height+24;
  }
  return {points,panels,width:w+48,height:y};
}
function wrapGraphLabel(name,max=28){
  const words=name.split(/\s+/),lines=[];let line='';
  for(const word of words){if(line&&line.length+word.length+1>max){lines.push(line);line=''}if(word.length>max){if(line){lines.push(line);line=''}for(let i=0;i<word.length;i+=max)lines.push(word.slice(i,i+max))}else line+=(line?' ':'')+word}
  if(line)lines.push(line);if(lines.length>2)return [lines[0],lines[1].slice(0,max-1)+'…'];return lines;
}
graph=function(){
  const allEdges=data.connections.filter(e=>node(e.a)&&node(e.b));
  let eligible=allEdges.filter(e=>!graphCross||root(e.a)!==root(e.b));
  if(graphFocus)eligible=eligible.filter(e=>e.a===graphFocus||e.b===graphFocus);
  const linked=new Set(eligible.flatMap(e=>[e.a,e.b]));
  const ns=concepts().filter(n=>matches(n)&&(!graphFocus||n.id===graphFocus||linked.has(n.id))&&(!graphDomain||graphFocus||root(n.id)===graphDomain)&&(!(graphLinked||graphCross)||linked.has(n.id)||n.id===graphFocus));
  const ids=new Set(ns.map(n=>n.id));const edges=eligible.filter(e=>ids.has(e.a)&&ids.has(e.b));
  $('content').innerHTML=intro('KNOWLEDGE CONNECTIONS','Where ideas meet.','Browse color-coded domain groups or focus on one concept and its immediate connections.')+
    '<div class="graph-toolbar"><label>Domain <select id="graphDomain"><option value="">All domains</option>'+domains().map(d=>'<option value="'+d.id+'" '+(d.id===graphDomain?'selected':'')+'>'+esc(d.name)+'</option>').join('')+'</select></label><label><input id="graphCross" type="checkbox" '+(graphCross?'checked':'')+'> Cross-domain only</label><label><input id="graphLinked" type="checkbox" '+(graphLinked?'checked':'')+'> Connected only</label><button id="graphFocus" '+(!selected?'disabled':'')+'>'+(graphFocus?'Clear focus':'Focus selected concept')+'</button></div><p class="muted">'+ns.length+' concepts · '+edges.length+' visible relationships '+(graphFocus?'· Focusing on '+esc(node(graphFocus)?.name):'')+'</p>'+
    (ns.length?'<div class="graph new-graph"><svg id="svg" aria-label="Interactive grouped concept graph"><g id="network"></g></svg><div class="graph-controls"><button data-zoom="1.25">+</button><button data-zoom=".8">−</button><button data-reset>Fit</button></div></div><p class="muted">Drag to pan · Scroll to zoom · Click a card or relationship line. Use Focus to isolate neighbors.</p>':'<div class="empty">No concepts match these filters.</div>');
  $('graphDomain').onchange=e=>{graphDomain=e.target.value;graphFocus=null;graph()};
  $('graphCross').onchange=e=>{graphCross=e.target.checked;graph()};$('graphLinked').onchange=e=>{graphLinked=e.target.checked;graph()};
  $('graphFocus').onclick=()=>{graphFocus=graphFocus?null:selected;graphDomain='';graph()};
  if(!ns.length)return;
  const {points,panels,width,height}=layoutGraph(ns,root,id=>node(id)?.name);
  const panelsMarkup=panels.map(p=>'<g><rect class="domain-panel" x="'+p.x+'" y="'+p.y+'" width="'+p.w+'" height="'+p.h+'" rx="13" fill="'+color(p.id)+'" fill-opacity=".08" stroke="'+color(p.id)+'" stroke-opacity=".32"/><text x="'+(p.x+17)+'" y="'+(p.y+30)+'" class="graph-domain-label" fill="'+color(p.id)+'">'+esc(p.name)+'</text></g>').join('');
  const lines=edges.map(e=>{const a=points.get(e.a),b=points.get(e.b),ax=a.x+a.w/2,ay=a.y+a.h/2,bx=b.x+b.w/2,by=b.y+b.h/2;return '<line x1="'+ax+'" y1="'+ay+'" x2="'+bx+'" y2="'+by+'" stroke="'+(a.domain===b.domain?'#abbdb0':'#9d7caf')+'" stroke-opacity="'+(selected&&(e.a===selected||e.b===selected)?'1':'.65')+'" stroke-width="'+(selected&&(e.a===selected||e.b===selected)?'3':'1.8')+'" data-edge="'+esc(e.id)+'"><title>'+esc(e.kind+': '+e.explanation)+'</title></line>'}).join('');
  const cards=ns.map(n=>{const p=points.get(n.id),lines=wrapGraphLabel(n.name);return '<g class="graph-card '+(selected===n.id?'selected':'')+'" data-concept="'+esc(n.id)+'" tabindex="0" role="button" aria-label="'+esc(n.name)+'"><rect x="'+p.x+'" y="'+p.y+'" width="'+p.w+'" height="'+p.h+'" rx="8" fill="#fff" stroke="'+color(p.domain)+'" stroke-opacity=".65"/><circle cx="'+(p.x+14)+'" cy="'+(p.y+30)+'" r="5" fill="'+color(p.domain)+'"/><text x="'+(p.x+29)+'" y="'+(p.y+(lines.length>1?24:35))+'">'+lines.map((l,i)=>'<tspan x="'+(p.x+29)+'" dy="'+(i?16:0)+'">'+esc(l)+'</tspan>').join('')+'</text><title>'+esc(n.name)+'</title></g>'}).join('');
  $('network').innerHTML=panelsMarkup+lines+cards;
  const svg=$('svg');let drag=null;const fit=[0,0,width,height];let box=height>850?[0,0,width,Math.min(height,Math.max(560,width*.75))]:[...fit];
  function redraw(){svg.setAttribute('viewBox',box.join(' '))}function zoom(f){const w=Math.max(240,Math.min(width*4,box[2]/f)),h=box[3]*w/box[2];box=[box[0]+(box[2]-w)/2,box[1]+(box[3]-h)/2,w,h];redraw()}redraw();
  document.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>zoom(+b.dataset.zoom));document.querySelector('[data-reset]').onclick=()=>{box=[...fit];redraw()};
  svg.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.12:.89)},{passive:false});
  svg.onpointerdown=e=>{if(e.target.closest('[data-concept],[data-edge]'))return;drag={x:e.clientX,y:e.clientY};svg.setPointerCapture(e.pointerId)};
  svg.onpointermove=e=>{if(!drag)return;const scale=Math.max(box[2]/svg.clientWidth,box[3]/svg.clientHeight);box[0]-=(e.clientX-drag.x)*scale;box[1]-=(e.clientY-drag.y)*scale;drag={x:e.clientX,y:e.clientY};redraw()};svg.onpointerup=svg.onpointercancel=()=>drag=null;
  svg.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.dataset.concept)choose(e.target.dataset.concept)});
};
const chooseGraphOriginal=choose;
choose=function(id){chooseGraphOriginal(id);if(view==='graph'&&$('graphFocus'))$('graphFocus').disabled=false};
