/* Collections are user-applied labels, independent of the AI knowledge tree. */
let collectionFilter='',libraryQuery='',formatFilter='';
function mediaType(name){
  const ext=name.split('.').pop().toLowerCase();
  if(['mp4','m4v','mov','webm'].includes(ext))return 'video';
  if(['mp3','m4a','wav','ogg','flac','aac'].includes(ext))return 'audio';
  if(['png','jpg','jpeg','webp','gif'].includes(ext))return 'image';
  if(['csv','json','html','htm'].includes(ext))return 'data';
  return 'document';
}
const collections=()=>data.collections||[];
const membership=id=>(data.document_collections||[]).filter(m=>m.document===id).map(m=>m.collection);
function libraryCard(d){
  const type=mediaType(d.name),ids=membership(d.id);
  const status=d.status==='complete'?'Indexed':d.status==='error'?'Parsing failed':d.status==='media'?(type==='image'?'Viewable image':'Ready to play · attach transcript to index'):'Ready for Codex';
  return '<article class="library-item"><div class="doc-icon '+type+'">'+esc(d.name.split('.').pop().toUpperCase())+'</div><div class="info"><strong>'+esc(d.name)+'</strong><small>'+esc(status)+(d.sections?' · '+d.indexed+'/'+d.sections+' sections indexed':'')+'</small>'+(d.error?'<small>'+esc(d.error)+'</small>':'')+'<div class="collection-tags">'+ids.map(id=>'<span class="tag">'+esc(collections().find(c=>c.id===id)?.name)+'</span>').join('')+'</div><details class="collection-picker"><summary>Manage collections</summary><div>'+collections().map(c=>'<label><input type="checkbox" data-assign="'+esc(d.id)+'" data-collection="'+esc(c.id)+'" '+(ids.includes(c.id)?'checked':'')+'>'+esc(c.name)+'</label>').join('')+'</div></details></div><div class="library-actions"><a class="reader-open" href="'+sourceLink(d.id,'')+'">'+(type==='video'?'Watch':type==='audio'?'Listen':type==='image'?'View':'Read')+'</a><a href="'+originalSourceLink(d.id,'')+'" target="_blank" rel="noopener">Original ↗</a></div></article>';
}
library=function(){
  const list=data.documents.filter(d=>(!collectionFilter||(collectionFilter==='unfiled'?!membership(d.id).length:membership(d.id).includes(collectionFilter)))&&(!formatFilter||mediaType(d.name)===formatFilter)&&(!libraryQuery||[d.name,(data.study_materials||[]).find(x=>x.document===d.id)?.title||''].some(n=>n.toLowerCase().includes(libraryQuery.toLowerCase()))));
  const options=[{id:'',name:'All materials'},{id:'unfiled',name:'Unsorted'},...collections()];
  $('content').innerHTML=intro('YOUR PERSONAL LIBRARY','A shelf for everything.','Collect textbooks, career materials, videos, audio, datasets, and the things you read for fun.')+
  '<div class="library-collections">'+options.map(c=>{const count=c.id==='unfiled'?data.documents.filter(d=>!membership(d.id).length).length:c.id?data.documents.filter(d=>membership(d.id).includes(c.id)).length:data.documents.length;return '<button data-collection-filter="'+esc(c.id)+'" class="'+(collectionFilter===c.id?'chosen':'')+'"><strong>'+esc(c.name)+'</strong><small>'+count+' materials</small></button>'}).join('')+'<button id="newCollection" class="add-collection">+ New collection</button></div>'+
  '<div class="library-filter"><input id="libraryQuery" type="search" placeholder="Search materials by filename" value="'+esc(libraryQuery)+'"><select id="formatFilter"><option value="">All formats</option>'+['document','video','audio','image','data'].map(x=>'<option value="'+x+'" '+(formatFilter===x?'selected':'')+'>'+x[0].toUpperCase()+x.slice(1)+'</option>').join('')+'</select><span class="muted">'+list.length+' results</span></div>'+
  '<div class="hint"><strong>Keep your atlas growing</strong><br>Collections organize files. Codex indexes only new readable sections. Attach a transcript to videos or audio before indexing.</div>'+
  (list.length?list.map(libraryCard).join(''):'<div class="empty"><h2>No materials here yet.</h2><p>Import something or assign existing materials to this collection.</p><button class="primary" data-import>Import materials</button></div>');
  document.querySelectorAll('[data-collection-filter]').forEach(b=>b.onclick=()=>{collectionFilter=b.dataset.collectionFilter;library()});
  $('newCollection').onclick=async()=>{const name=prompt('Collection name');if(name===null||!name.trim())return;try{const c=await readerRequest('/api/collection',{action:'create',name});collectionFilter=c.id;await refresh();notify('Collection created')}catch(e){notify(e.message)}};
  $('libraryQuery').oninput=e=>{libraryQuery=e.target.value;const pos=e.target.selectionStart;library();$('libraryQuery').focus();try{$('libraryQuery').setSelectionRange(pos,pos)}catch{}};
  $('formatFilter').onchange=e=>{formatFilter=e.target.value;library()};
  document.querySelectorAll('[data-assign]').forEach(input=>input.onchange=async()=>{try{await readerRequest('/api/collection',{document:input.dataset.assign,collection:input.dataset.collection,assigned:input.checked});const r=await fetch('/api/atlas');data=await r.json();library();const detail=document.querySelector('[data-assign="'+input.dataset.assign+'"]')?.closest('details');if(detail)detail.open=true;notify('Collection saved')}catch(e){input.checked=!input.checked;notify(e.message)}});
};
const oldSearchInput=$('search').oninput;
$('search').oninput=e=>{if(view==='library'){libraryQuery=e.target.value;library()}else oldSearchInput(e)};
/* Play the immutable original media alongside its optional source transcript. */
const plainDrawReader=drawReader;
let mediaState={doc:null,position:0,lastSaved:-1};
const mediaOpenReader=openReader;
let requestedMediaLabel='';
openReader=function(id,label){requestedMediaLabel=label||'';return mediaOpenReader(id,label)};
drawReader=function(){
  if(!book)return;
  const previous=$('mediaPlayer');
  if(previous&&mediaState.doc===book.document.id)mediaState.position=previous.currentTime||0;
  plainDrawReader();
  const doc=book.document,type=mediaType(doc.name),s=section();
  if(!['video','audio','image'].includes(type))return;
  const media=document.createElement('div');media.className='media-reader';
  const src=originalSourceLink(doc.id,'');
  if(type==='image'){
    media.innerHTML='<img class="image-reader" alt="'+esc(doc.name)+'" src="'+src+'"><p class="muted">Original image. Automatic OCR is not included.</p>';
  }else{
    const changed=mediaState.doc!==doc.id;
    if(changed)mediaState={doc:doc.id,position:book.media_position||0,lastSaved:-1};
    const stamp=s?.label.match(/@\s+([\d:.]+)/);
    const seconds=stamp?stamp[1].split(':').reduce((n,x)=>n*60+Number(x),0):null;
    if(seconds!==null&&Number.isFinite(seconds)&&((changed&&requestedMediaLabel)||(!changed&&mediaState.section!==s.label)))mediaState.position=seconds;
    mediaState.section=s?.label;
    media.innerHTML='<'+type+' id="mediaPlayer" controls preload="metadata" src="'+src+'"></'+type+'><div class="transcript-actions"><strong>Transcript</strong><input id="transcriptFile" type="file" accept=".srt,.vtt,.txt,.md" hidden><button id="attachTranscript">+ Attach transcript</button><span class="muted">'+(book.transcripts?.length||0)+' attached</span></div><p class="muted">Text and timestamped subtitles can be indexed by Codex. The original media remains intact.</p>';
  }
  $('content').querySelector('.reader-tools').after(media);
  if(!s){['listen','pauseSpeech','stopSpeech'].forEach(id=>{if($(id))$(id).disabled=true});const empty=$('content').querySelector('.empty');if(empty)empty.textContent=type==='image'?'Image viewer.':'Attach a transcript to read, highlight, cite and index the spoken content.'}
  const player=$('mediaPlayer');
  if(player){
    player.onloadedmetadata=()=>{if(Number.isFinite(mediaState.position))player.currentTime=Math.min(mediaState.position,player.duration||mediaState.position)};
    const persist=()=>{if(!Number.isFinite(player.currentTime))return;mediaState.position=player.currentTime;mediaState.lastSaved=player.currentTime;readerRequest('/api/media-position',{document:doc.id,seconds:player.currentTime}).catch(()=>{})};
    player.ontimeupdate=()=>{if(Math.abs(player.currentTime-mediaState.lastSaved)>5)persist()};player.onpause=persist;player.onseeked=persist;
    $('attachTranscript').onclick=()=>$('transcriptFile').click();
    $('transcriptFile').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>5_000_000)throw Error('Transcript must be 5 MB or smaller.');await readerRequest('/api/transcript',{document:doc.id,name:f.name,text:await f.text()});await openReader(doc.id,'');notify('Transcript saved. Ask Codex to index the new sections.')}catch(err){notify(err.message)}};
  }
};
