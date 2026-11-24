/* Personal annotations are stored separately from immutable source evidence. */
const studyRecord=id=>(data.study_materials||[]).find(x=>x.document===id)||{};
const percent=record=>record.completed?100:Math.round((record.progress||0)*100);
const byName=id=>studyRecord(id).title||data.documents.find(d=>d.id===id)?.name||'Material';
async function saveStudy(id,fields){
  const record=await readerRequest('/api/study',{document:id,...fields});
  data.study_materials=(data.study_materials||[]).filter(x=>x.document!==id).concat(record);
  if(book?.document.id===id)book.study=record;
  return record;
}
const originalCard=libraryCard;
libraryCard=function(d){
  const record=studyRecord(d.id),html=originalCard(d);
  const wrapper=document.createElement('div');wrapper.innerHTML=html;
  const card=wrapper.firstElementChild,info=card.querySelector('.info');
  info.querySelector('strong').textContent=record.title||d.name;
  if(record.title){const original=document.createElement('small');original.textContent=d.name;info.querySelector('strong').after(original)}
  const extra=document.createElement('div');extra.className='study-meta';
  extra.innerHTML='<div class="study-progress"><progress max="100" value="'+percent(record)+'"></progress><span>'+percent(record)+'%</span></div><button data-study-edit="'+d.id+'">Rename / notes</button><button data-study-done="'+d.id+'">'+(record.completed?'✓ Finished · Undo':'Mark finished')+'</button>';
  info.append(extra);return card.outerHTML;
};
const previousLibrary=library;
library=function(){
  previousLibrary();
  const input=$('libraryQuery');
  if(input)input.placeholder='Search material names';
};
// Title search includes the custom display title without changing the original.
let deck='',cardIndex=0,reveal=false,reviewAll=false;
document.querySelector('nav').insertAdjacentHTML('beforeend','<button data-view="flashcards">◇ &nbsp; Flashcards</button>');
const studyRender=render;
render=function(){
  if(view!=='flashcards'){studyRender();return}
  stopSpeech();$('content').classList.remove('reader-content');document.body.classList.remove('reader-full');
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view==='flashcards'));
  $('crumb').textContent='Workspace / Flashcards';
  const decks=data.decks||[],cards=(data.cards||[]).filter(c=>c.deck===deck);
  const available=cards.filter(c=>reviewAll||!c.known);
  if(cardIndex>=available.length)cardIndex=0;
  const c=available[cardIndex],d=decks.find(x=>x.id===deck);
  $('content').innerHTML=intro('FLASHCARDS','Practice recall.','Import your own question-and-answer decks, then flip each card and mark the ones you know.')+
  '<div class="flash-decks">'+decks.map(x=>{const all=(data.cards||[]).filter(c=>c.deck===x.id);return '<button data-deck="'+x.id+'" class="'+(x.id===deck?'chosen':'')+'"><strong>'+esc(x.name)+'</strong><small>'+all.filter(c=>c.known).length+' / '+all.length+' known</small></button>'}).join('')+'<button id="importDeck">+ Import deck</button><input type="file" accept=".csv,.tsv,.json" id="deckFile" hidden></div>'+
  (d?'<div class="flash-head"><h2>'+esc(d.name)+'</h2><label><input type="checkbox" id="reviewAll" '+(reviewAll?'checked':'')+'> Include known cards</label></div><progress max="'+Math.max(1,cards.length)+'" value="'+cards.filter(c=>c.known).length+'"></progress>'+
  (c?'<div class="flash-card" id="flipCard" role="button" tabindex="0"><div class="eyebrow">'+(reveal?'ANSWER':'QUESTION')+' · '+(cardIndex+1)+' / '+available.length+'</div><div class="flash-text">'+esc(reveal?c.back:c.front)+'</div><small>Click to '+(reveal?'see question':'reveal answer')+'</small></div><div class="flash-controls"><button id="prevCard">‹ Previous</button><button id="againCard">Review again</button><button class="primary" id="knowCard">✓ Know it</button><button id="nextCard">Next ›</button></div>':'<div class="empty"><h2>Deck complete.</h2><p>Enable “Include known cards” to practice again.</p></div>'):'<div class="empty"><h2>Bring your own flashcards.</h2><p>CSV / TSV with two columns (Front, Back), or JSON objects with front and back fields.</p></div>');
  $('detail').innerHTML='<div class="eyebrow">RECALL</div><h2>Less rereading, more remembering.</h2><p class="muted">Imported decks and review status are saved locally. Reimporting identical cards does not erase your progress.</p>';
  document.querySelectorAll('[data-deck]').forEach(b=>b.onclick=()=>{deck=b.dataset.deck;cardIndex=0;reveal=false;render()});
  $('importDeck').onclick=()=>$('deckFile').click();
  $('deckFile').onchange=async e=>{const f=e.target.files[0];if(!f)return;const name=prompt('Deck name',f.name.replace(/\.[^.]+$/,''));if(!name)return;try{const result=await readerRequest('/api/flashcards',{action:'import',name,format:f.name.split('.').pop().toLowerCase(),text:await f.text()});deck=result.id;cardIndex=0;reveal=false;await refresh();notify(result.added+' new cards imported')}catch(err){notify(err.message)}};
  if($('reviewAll'))$('reviewAll').onchange=e=>{reviewAll=e.target.checked;cardIndex=0;reveal=false;render()};
  if(c){const move=n=>{cardIndex=(cardIndex+n+available.length)%available.length;reveal=false;render()};$('flipCard').onclick=()=>{reveal=!reveal;render()};$('flipCard').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();reveal=!reveal;render()}};$('prevCard').onclick=()=>move(-1);$('nextCard').onclick=()=>move(1);const review=async known=>{try{await readerRequest('/api/flashcards',{action:'review',id:c.id,known});c.known=known;if(!known||reviewAll)cardIndex++;reveal=false;render()}catch(e){notify(e.message)}};$('knowCard').onclick=()=>review(true);$('againCard').onclick=()=>review(false)}
};
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-study-edit],[data-study-done]');if(!b)return;
  const id=b.dataset.studyEdit||b.dataset.studyDone,record=studyRecord(id);
  if(b.dataset.studyDone){try{await saveStudy(id,{completed:!record.completed});library();notify(record.completed?'Marked unfinished':'Marked finished')}catch(err){notify(err.message)}return}
  const modal=document.createElement('dialog');modal.className='study-dialog';
  modal.innerHTML='<form><h2>Material details</h2><label>Display name<input id="materialTitle" maxlength="300" value="'+esc(record.title||byName(id))+'"></label><label>Notes<textarea id="materialNote" rows="8" placeholder="What did you learn?">'+esc(record.note||'')+'</textarea></label><div class="flash-controls"><button type="button" id="cancelMaterial">Cancel</button><button class="primary" type="submit">Save</button></div></form>';
  document.body.append(modal);modal.showModal();modal.onclose=()=>modal.remove();modal.querySelector('#cancelMaterial').onclick=()=>modal.close();modal.querySelector('form').onsubmit=async ev=>{ev.preventDefault();try{await saveStudy(id,{title:modal.querySelector('#materialTitle').value.trim(),note:modal.querySelector('#materialNote').value});modal.close();if(view==='library')library();else drawReader();notify('Material details saved')}catch(err){notify(err.message)}};
});
const existingDraw=drawReader;
let continuous=false,readerObserver=null,progressTimer=null,readerGen=0;
const openStudyReader=openReader;
openReader=function(id,label){continuous=false;readerGen++;return openStudyReader(id,label)};
const viewBeforeStudy=setView;
setView=function(v){if(v!=='reader'){readerObserver?.disconnect();clearTimeout(progressTimer);document.body.classList.remove('reader-full')}viewBeforeStudy(v)};
function readerProgress(doc,progress,location){
  const generation=readerGen;clearTimeout(progressTimer);progressTimer=setTimeout(()=>{if(generation!==readerGen)return;saveStudy(doc,{progress:Math.max(0,Math.min(1,progress)),location}).then(x=>{const bar=$('readerProgress');if(bar){bar.value=percent(x);$('readerPercent').textContent=percent(x)+'%'}}).catch(()=>{})},450)
}
function enterFull(){
  document.body.classList.toggle('reader-full');
  const button=$('fullReader');if(button)button.textContent=document.body.classList.contains('reader-full')?'Exit focus':'Full screen / focus';
}
drawReader=function(){
  if(!book)return;readerObserver?.disconnect();clearTimeout(progressTimer);
  const doc=book.document,record=book.study||studyRecord(doc.id),type=mediaType(doc.name),isMedia=['video','audio','image'].includes(type);
  const isDocx=doc.name.toLowerCase().endsWith('.docx'),isPdf=doc.name.toLowerCase().endsWith('.pdf'),isSlides=doc.name.toLowerCase().endsWith('.pptx');
  if(isDocx&&!book.docModeSet){continuous=true;book.docModeSet=true}
  existingDraw();
  const h=$('content').querySelector('.reader-title');if(h)h.textContent=record.title||doc.name;
  const tools=$('content').querySelector('.reader-tools');
  tools.insertAdjacentHTML('afterbegin','<button id="fullReader">Full screen / focus</button>'+(isPdf?'<button id="fullPdf">Full-page PDF</button>':'')+(!isMedia&&book.sections.length?'<button id="continuousMode">'+(continuous?'Single section':'Continuous reading')+'</button>':''));
  tools.insertAdjacentHTML('afterend','<div class="reader-status"><progress id="readerProgress" max="100" value="'+percent(record)+'"></progress><span id="readerPercent">'+percent(record)+'%</span><button id="finishReader">'+(record.completed?'✓ Finished · Undo':'Mark finished')+'</button><button data-study-edit="'+doc.id+'">Rename / notes</button></div>');
  $('fullReader').onclick=enterFull;
  $('finishReader').onclick=async()=>{try{await saveStudy(doc.id,{completed:!record.completed});drawReader()}catch(e){notify(e.message)}};
  if(isPdf)$('fullPdf').onclick=()=>{const panel=document.createElement('dialog');panel.className='pdf-full';panel.innerHTML='<div><strong>'+esc(record.title||doc.name)+'</strong><button type="button">Close PDF</button></div><iframe title="Full-page PDF" src="'+originalSourceLink(doc.id,section()?.label)+'"></iframe>';document.body.append(panel);panel.showModal();panel.querySelector('button').onclick=()=>panel.close();panel.onclose=()=>panel.remove()};
  if(isSlides){$('content').querySelector('.reader-status').insertAdjacentHTML('afterend','<div class="hint">Slide text view · Open the original PPTX in PowerPoint or Keynote to see its visual layout.</div>')}
  if($('continuousMode'))$('continuousMode').onclick=()=>{stopSpeech();continuous=!continuous;drawReader()};
  const player=$('mediaPlayer');if(player){let last=-10;const persist=()=>{if(Number.isFinite(player.duration)&&player.duration>0){last=player.currentTime;readerProgress(doc.id,player.currentTime/player.duration,String(player.currentTime))}};player.addEventListener('timeupdate',()=>{if(Math.abs(player.currentTime-last)>5)persist()});player.addEventListener('pause',persist);player.addEventListener('seeked',persist)}
  if(isMedia||!book.sections.length)return;
  if(!continuous){readerProgress(doc.id,currentSection/Math.max(1,book.sections.length),section().label);return}
  const saved=currentSection,article=$('readingText');if(!article)return;
  article.innerHTML=book.sections.map((s,i)=>'<section class="continuous-section" data-section-index="'+i+'"><span class="section-marker">'+esc(s.label)+'</span><div class="section-text">'+markedText(s.text,book.highlights.filter(m=>m.label===s.label))+'</div></section>').join('');
  article.onmouseup=()=>{const sel=window.getSelection();if(!sel||sel.isCollapsed||!sel.rangeCount)return;const range=sel.getRangeAt(0),a=range.startContainer.parentElement?.closest('.section-text'),b=range.endContainer.parentElement?.closest('.section-text');if(!a||a!==b){selection=null;return notify('Select within one paragraph or source section.')}const parent=a.closest('[data-section-index]');currentSection=+parent.dataset.sectionIndex;const before=document.createRange();before.selectNodeContents(a);before.setEnd(range.startContainer,range.startOffset);const start=Array.from(before.toString()).length;selection={start,end:start+Array.from(range.toString()).length,quote:range.toString()};};
  document.querySelectorAll('[data-hl]').forEach(b=>b.onclick=async()=>{if(!selection)return notify('Select a passage first.');try{const m=await readerRequest('/api/highlight',{document:doc.id,label:section().label,...selection,color:b.dataset.hl});book.highlights=book.highlights.filter(x=>x.id!==m.id).concat(m);selection=null;drawReader();notify('Highlight saved')}catch(e){notify(e.message)}});
  $('listen').onclick=()=>startSpeech(book.sections.slice(currentSection).map(s=>s.text).join('\n\n'));
  requestAnimationFrame(()=>{if(view!=='reader'||!article.isConnected)return;const target=article.querySelector('[data-section-index="'+saved+'"]');if(target&&saved>0)target.scrollIntoView({block:'start'});readerObserver=new IntersectionObserver(entries=>{if(view!=='reader'||!continuous)return;const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top);if(!visible.length)return;currentSection=+visible[0].target.dataset.sectionIndex;const s=section();if(!s)return;readerProgress(doc.id,currentSection/Math.max(1,book.sections.length),s.label);savePosition()},{rootMargin:'-90px 0px -55% 0px'});article.querySelectorAll('[data-section-index]').forEach(x=>readerObserver.observe(x))});
};
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('reader-full'))enterFull()});
