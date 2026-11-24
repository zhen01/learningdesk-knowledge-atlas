/* The reader works against immutable extracted sections; annotation offsets
   refer to Unicode code points rather than the browser's UTF-16 units. */
let book=null, currentSection=0, selection=null, reading=false, paused=false, readGeneration=0;
const originalSourceLink=sourceLink;
sourceLink=(id,label)=>'/#read='+encodeURIComponent(id)+'&label='+encodeURIComponent(label||'');
const originalRender=render;
render=function(){
  if(view==='reader'){drawReader();return}
  stopSpeech();
  $('content').classList.remove('reader-content');
  originalRender();
};
const originalSetView=setView;
setView=function(v){if(location.hash.startsWith('#read='))history.replaceState(null,'','/');originalSetView(v)};
library=function(){
  $('content').innerHTML=intro('SOURCE LIBRARY','Your materials','Read, listen to and annotate your original learning materials. Every highlight is saved on this computer.')+
  '<div class="hint"><strong>Incremental indexing</strong><br>Codex indexes only pending sections. Previously extracted knowledge, references, and your annotations are retained.</div>'+
  (!data.documents.length?empty('A library of your own.','PDF, DOCX, Markdown and TXT are supported.'):'<div>'+data.documents.map(d=>'<div class="doc"><div class="doc-icon">'+esc(d.name.split('.').pop().toUpperCase())+'</div><div class="info"><strong>'+esc(d.name)+'</strong><small>'+esc(d.status==='complete'?'Indexed':d.status==='error'?'Parsing failed':'Ready for Codex')+' · '+d.indexed+'/'+d.sections+' sections indexed</small>'+(d.error?'<small>'+esc(d.error)+'</small>':'')+'</div><a class="reader-open" href="'+sourceLink(d.id,'')+'">Read</a><a href="'+originalSourceLink(d.id,'')+'" target="_blank" rel="noopener">Original ↗</a></div>').join('')+'</div>')+'<button data-refresh>↻ Refresh library</button>';
};
async function readerRequest(path,payload){
  const r=await fetch(path,payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:undefined);
  const j=await r.json();if(!r.ok)throw Error(j.error||'Reader request failed');return j;
}
async function openReader(id,label){
  stopSpeech();selection=null;view='reader';book=null;
  $('content').innerHTML='<p>Opening document…</p>';
  try{
    const loadedBook=await readerRequest('/api/reader?id='+encodeURIComponent(id));
    if(view!=='reader')return;
    book=loadedBook;
    currentSection=Math.max(0,book.sections.findIndex(s=>s.label===(label||book.position)));
    drawReader(); if(book.sections.length)savePosition();
  }catch(e){notify(e.message);setView('library')}
}
function openHash(){
  if(!location.hash.startsWith('#read='))return;
  const p=new URLSearchParams(location.hash.slice(1));openReader(p.get('read'),p.get('label'));
}
window.addEventListener('hashchange',openHash);
document.addEventListener('click',e=>{
  const link=e.target.closest('a[href^="/#read="]');
  if(link&&!e.metaKey&&!e.ctrlKey&&e.button===0){e.preventDefault();const hash=new URL(link.href).hash;if(location.hash===hash)openHash();else location.hash=hash}
},true);
function section(){return book?.sections[currentSection]}
function savePosition(){const s=section();if(s)readerRequest('/api/position',{document:book.document.id,label:s.label}).catch(e=>notify(e.message))}
function changeSection(i){if(!book||i<0||i>=book.sections.length)return;stopSpeech();selection=null;currentSection=i;drawReader();savePosition();$('readingText')?.scrollIntoView({block:'start',behavior:'smooth'})}
function markedText(text,marks){
  const chars=Array.from(text);const boundaries=[...new Set([0,chars.length,...marks.flatMap(m=>[m.start,m.end])])].sort((a,b)=>a-b);
  return boundaries.slice(0,-1).map((start,i)=>{const end=boundaries[i+1],value=esc(chars.slice(start,end).join('')),m=marks.find(m=>m.start<=start&&m.end>=end);return m?'<mark class="hl-'+esc(m.color)+'">'+value+'</mark>':value}).join('');
}
function drawReader(){
  if(!book)return;
  const s=section(),doc=book.document,marks=book.highlights.filter(m=>m.label===s?.label);
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view==='library'));
  $('crumb').textContent='Library / Reader';$('content').classList.add('reader-content');
  const pdf=doc.name.toLowerCase().endsWith('.pdf');
  $('content').innerHTML='<button class="reader-back" data-view="library">‹ Back to library</button><div class="eyebrow">DOCUMENT READER</div><h1 class="reader-title">'+esc(doc.name)+'</h1><div class="reader-tools"><a href="'+originalSourceLink(doc.id,s?.label)+'" target="_blank" rel="noopener">Open original ↗</a>'+(pdf?'<button id="pdfToggle">Show PDF page</button>':'')+'<button id="listen">▶ Listen</button><button id="pauseSpeech">Pause</button><button id="stopSpeech">Stop</button><label>Speed <select id="speechRate"><option>.8</option><option selected>1.0</option><option>1.25</option><option>1.5</option><option>2.0</option></select></label><label>Voice <select id="speechVoice"><option value="">System default</option></select></label></div>'+
  (s?'<div class="reader-pager"><button id="prevSection" '+(currentSection===0?'disabled':'')+'>‹ Previous</button><select id="sectionSelect" aria-label="Source section">'+book.sections.map((x,i)=>'<option value="'+i+'" '+(i===currentSection?'selected':'')+'>'+esc(x.label)+'</option>').join('')+'</select><span>'+ (currentSection+1)+' / '+book.sections.length+'</span><button id="nextSection" '+(currentSection>=book.sections.length-1?'disabled':'')+'>Next ›</button></div><div id="pdfPane" hidden></div><div class="highlight-tools"><span>Select text, then choose a highlight color:</span>'+['yellow','green','blue','pink'].map(c=>'<button class="swatch hl-'+c+'" data-hl="'+c+'" title="Highlight '+c+'" aria-label="Highlight '+c+'"></button>').join('')+'</div><article id="readingText" class="reading-text">'+markedText(s.text,marks)+'</article>':'<div class="empty">No readable extracted text. Open the original file to view it.</div>');
  $('detail').innerHTML='<div class="eyebrow">ANNOTATIONS</div><h2>Your highlights</h2><p class="muted">'+book.highlights.length+' saved in this document</p>'+ (book.highlights.length?[...book.highlights].map(m=>'<div class="annotation"><button class="annotation-jump" data-jump="'+esc(m.id)+'">'+esc(m.label)+'</button><blockquote class="hl-'+esc(m.color)+'">'+esc(m.quote)+'</blockquote><textarea data-note="'+esc(m.id)+'" placeholder="Add a note…">'+esc(m.note)+'</textarea><div class="annotation-actions"><button data-save-note="'+esc(m.id)+'">Save note</button><button data-remove-note="'+esc(m.id)+'">Remove</button></div></div>').join(''):'<p class="muted">Select any passage to create your first annotation.</p>');
  fillVoices();
  if(!s)return;
  $('prevSection').onclick=()=>changeSection(currentSection-1);$('nextSection').onclick=()=>changeSection(currentSection+1);$('sectionSelect').onchange=e=>changeSection(+e.target.value);
  const capture=()=>{const sel=window.getSelection();if(!sel||sel.isCollapsed||!sel.rangeCount)return;const range=sel.getRangeAt(0),article=$('readingText');if(!article.contains(range.startContainer)||!article.contains(range.endContainer))return;const before=document.createRange();before.selectNodeContents(article);before.setEnd(range.startContainer,range.startOffset);const start=Array.from(before.toString()).length,end=start+Array.from(range.toString()).length;selection={start,end,quote:range.toString()}};
  $('readingText').addEventListener('mouseup',capture);$('readingText').addEventListener('keyup',capture);
  document.querySelectorAll('[data-hl]').forEach(b=>{b.onmousedown=e=>e.preventDefault();b.onclick=async()=>{if(!selection)return notify('Select a passage first.');try{const m=await readerRequest('/api/highlight',{document:doc.id,label:s.label,...selection,color:b.dataset.hl});book.highlights=book.highlights.filter(x=>x.id!==m.id).concat(m);selection=null;drawReader();notify('Highlight saved')}catch(e){notify(e.message)}}});
  if(pdf)$('pdfToggle').onclick=()=>{const pane=$('pdfPane');pane.hidden=!pane.hidden;pane.innerHTML=pane.hidden?'':'<iframe title="Original PDF page" src="'+originalSourceLink(doc.id,s.label)+'"></iframe>';$('pdfToggle').textContent=pane.hidden?'Show PDF page':'Hide PDF page'};
  $('listen').onclick=()=>startSpeech(s.text);$('pauseSpeech').onclick=()=>{if(!reading)return;const engine=window.speechSynthesis;if(paused){engine.resume();paused=false;$('pauseSpeech').textContent='Pause'}else{engine.pause();paused=true;$('pauseSpeech').textContent='Resume'}};$('stopSpeech').onclick=stopSpeech;
}
function fillVoices(){
  const select=$('speechVoice');if(!select||!window.speechSynthesis)return;
  const voices=speechSynthesis.getVoices().filter(v=>v.localService);
  select.innerHTML=voices.length?voices.map(v=>'<option value="'+esc(v.voiceURI)+'">'+esc(v.name+' · '+v.lang)+'</option>').join(''):'<option value="">No local voice available</option>';
  const en=voices.find(v=>v.lang==='en-US');if(en)select.value=en.voiceURI;
}
if(window.speechSynthesis)speechSynthesis.addEventListener('voiceschanged',fillVoices);
function stopSpeech(){readGeneration++;if(window.speechSynthesis)window.speechSynthesis.cancel();reading=false;paused=false;if($('listen'))$('listen').textContent='▶ Listen';if($('pauseSpeech'))$('pauseSpeech').textContent='Pause'}
function startSpeech(text){
  if(!window.speechSynthesis)return notify('This browser does not support text to speech.');
  const voice=speechSynthesis.getVoices().find(v=>v.localService&&v.voiceURI===$('speechVoice').value);
  if(!voice)return notify('No local system voice available. Install a macOS voice or try Safari.');
  const rate=Number($('speechRate').value),parts=text.match(/[^.!?。！？\n]+[.!?。！？\n]?/g)||[text],chunks=[];let chunk='';
  for(const p of parts){if(chunk.length+p.length>350&&chunk){chunks.push(chunk);chunk=''}chunk+=p;while(chunk.length>500){chunks.push(chunk.slice(0,500));chunk=chunk.slice(500)}}if(chunk)chunks.push(chunk);
  stopSpeech();const generation=readGeneration;reading=true;$('listen').textContent='Playing…';let i=0;
  function next(){if(generation!==readGeneration)return;if(i>=chunks.length){stopSpeech();return}const utterance=new SpeechSynthesisUtterance(chunks[i++]);utterance.voice=voice;utterance.rate=rate;utterance.onend=next;utterance.onerror=()=>{if(generation===readGeneration){stopSpeech();notify('Speech stopped. Try another local voice.')}};speechSynthesis.speak(utterance)}
  next();
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-jump],[data-save-note],[data-remove-note]');if(!b||!book)return;
  const id=b.dataset.jump||b.dataset.saveNote||b.dataset.removeNote,m=book.highlights.find(x=>x.id===id);if(!m)return;
  if(b.dataset.jump){changeSection(book.sections.findIndex(s=>s.label===m.label));return}
  try{
    if(b.dataset.removeNote){if(!confirm('Remove this saved highlight and its note?'))return;await readerRequest('/api/highlight',{action:'delete',id});book.highlights=book.highlights.filter(x=>x.id!==id)}
    else{m.note=document.querySelector('[data-note="'+id+'"]').value;await readerRequest('/api/highlight',m)}
    drawReader();notify('Annotations saved.');
  }catch(err){notify(err.message)}
});
window.addEventListener('beforeunload',stopSpeech);
openHash();
