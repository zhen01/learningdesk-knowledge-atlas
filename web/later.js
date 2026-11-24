/* Capture learning intentions without turning them into a project plan. */
let shelfTab='materials',laterItems=null,laterFetch=null,laterShowArchived=false;
const renderGallery=library;
function shelfTabs(){
 return '<nav class="shelf-nav" aria-label="Library views">'+[['materials','My library'],['reading','Reading list'],['research','To be added']].map(([id,label])=>'<button data-shelf-tab="'+id+'" class="'+(shelfTab===id?'chosen':'')+'">'+label+(id!=='materials'&&laterItems?'<small>'+laterItems.filter(x=>x.kind===id&&x.status!=='archived'&&x.status!=='finished'&&x.status!=='added').length+'</small>':'')+'</button>').join('')+'</nav>';
}
async function loadLater(){if(!laterFetch)laterFetch=readerRequest('/api/later').then(x=>laterItems=x).finally(()=>laterFetch=null);return laterFetch}
function bindShelf(){document.querySelectorAll('[data-shelf-tab]').forEach(b=>b.onclick=()=>{shelfTab=b.dataset.shelfTab;library()})}
library=function(){
 if(shelfTab==='materials'){
  renderGallery();
  $('content').querySelector('.gallery-heading')?.insertAdjacentHTML('afterend',shelfTabs());bindShelf();return
 }
 document.body.classList.add('library-gallery-view');
 if(!laterItems){$('content').innerHTML='<div class="gallery-page">'+shelfTabs()+'<p>Opening your saved list…</p></div>';bindShelf();loadLater().then(()=>{if(view==='library'&&shelfTab!=='materials')library()}).catch(e=>notify(e.message));return}
 drawLater();
};
const laterLabels={saved:'Want to read',reading:'Reading',finished:'Finished',queued:'To research',researching:'Researching',added:'Added',archived:'Archived'};
const laterStatuses={reading:['saved','reading','finished','archived'],research:['queued','researching','added','archived']};
function linkAllowed(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password}catch{return false}}
function externalLink(url,label,cls=''){return linkAllowed(url)?'<a class="'+cls+'" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' <span aria-hidden="true">↗</span></a>':''}
function laterCard(item,i){
 const palette=galleryPalette[i%galleryPalette.length],reading=item.kind==='reading',progress=item.status==='finished'||item.status==='added',doc=data.documents.find(d=>d.id===item.document);
 return '<article class="later-card '+(progress?'later-finished':'')+'">'+(reading?'<div class="later-cover cover-'+palette+'"><div class="later-book"><span>'+esc(item.category||'Reading list')+'</span><strong>'+esc(item.title)+'</strong><small>'+esc(item.author)+'</small></div><span class="later-book-type">'+(item.category==='Engineering Fundamentals'?'COURSE':'READING')+'</span></div>':'')+
 '<div class="later-body"><div class="later-card-heading"><h3>'+esc(item.title)+'</h3><button class="later-edit" data-edit-later="'+esc(item.id)+'" aria-label="Edit '+esc(item.title)+'" title="Edit">···</button></div><div class="later-meta"><span class="gallery-tag tag-'+palette+'">'+esc(item.category||'Unsorted')+'</span><span class="later-status '+(progress?'complete':'')+'">'+esc(laterLabels[item.status])+'</span></div>'+(item.author?'<p class="later-author">'+esc(item.author)+'</p>':'')+'<p class="later-note">'+esc(item.note||'')+'</p>'+
 (item.access?'<p class="later-access">'+esc(item.access)+'</p>':'')+
 '<div class="later-links">'+externalLink(item.url,reading?'Open resource':'Open reference','later-primary-link')+externalLink(item.alt_url,item.alt_label||'More resources','later-secondary-link')+(doc?'<a class="later-secondary-link" href="'+sourceLink(doc.id,'')+'">Open in library</a>':'')+'</div>'+
 '<div class="later-footer"><select data-later-status="'+esc(item.id)+'" aria-label="Change status">'+laterStatuses[item.kind].map(s=>'<option value="'+s+'" '+(s===item.status?'selected':'')+'>'+laterLabels[s]+'</option>').join('')+'</select>'+(!reading&&!doc?'<button data-edit-later="'+esc(item.id)+'">Link material</button>':'')+'</div></div></article>';
}
function drawLater(){
 const reading=shelfTab==='reading',items=laterItems.filter(x=>x.kind===shelfTab&&(laterShowArchived||x.status!=='archived'));
 $('content').innerHTML='<div class="gallery-page"><div class="gallery-heading"><div><div class="eyebrow">PERSONAL KNOWLEDGE LIBRARY</div><h1>Library<span>.</span></h1><p>Everything worth keeping, in one place.</p></div><button id="addLater" class="primary gallery-add">＋ '+(reading?'Add reading':'Save an idea')+'</button></div>'+shelfTabs()+
 '<div class="later-intro"><div><h2>'+(reading?'Reading list':'Materials to be added')+'</h2><p>'+(reading?'Books, courses and articles worth coming back to.':'Capture a topic now. Research or create the material when you have time.')+'</p></div><label><input type="checkbox" id="laterArchived" '+(laterShowArchived?'checked':'')+'> Show archived</label></div>'+
 (items.length?'<div class="later-grid '+(reading?'reading-grid':'research-grid')+'">'+items.map(laterCard).join('')+'</div>':'<div class="gallery-empty"><h2>'+(reading?'Nothing on your reading list yet.':'No ideas waiting.')+'</h2><p>'+(reading?'Save a book or free course to read later.':'Write down the topic before you forget it.')+'</p><button id="emptyLater" class="primary">＋ Add item</button></div>')+'</div>';
 bindShelf();$('addLater').onclick=()=>editLater(null);if($('emptyLater'))$('emptyLater').onclick=()=>editLater(null);
 $('laterArchived').onchange=e=>{laterShowArchived=e.target.checked;drawLater()};
 document.querySelectorAll('[data-edit-later]').forEach(b=>b.onclick=()=>editLater(laterItems.find(x=>x.id===b.dataset.editLater)));
 document.querySelectorAll('[data-later-status]').forEach(s=>s.onchange=async()=>{try{await readerRequest('/api/later',{id:s.dataset.laterStatus,status:s.value});await loadLater();drawLater()}catch(e){notify(e.message)}});
}
function editLater(item){
 const reading=shelfTab==='reading',dialog=document.createElement('dialog');dialog.className='later-dialog';
 dialog.innerHTML='<form><div class="eyebrow">'+(reading?'READING LIST':'MATERIALS TO BE ADDED')+'</div><h2>'+(item?'Edit item':reading?'Save something to read':'Capture a learning idea')+'</h2><label>Title<input name="title" required maxlength="300" placeholder="'+(reading?'Book, article or course':'What do you want to learn?')+'" value="'+esc(item?.title||'')+'"></label><div class="later-form-row"><label>Category<input name="category" maxlength="100" placeholder="e.g. Data & Systems" value="'+esc(item?.category||'')+'"></label>'+(reading?'<label>Author / source<input name="author" maxlength="200" value="'+esc(item?.author||'')+'"></label>':'')+'</div><label>'+(reading?'Why read it?':'What should the future material cover?')+'<textarea name="note" rows="4" placeholder="A few notes are enough." maxlength="15000">'+esc(item?.note||'')+'</textarea></label><label>Resource link (optional)<input name="url" type="url" placeholder="https://..." value="'+esc(item?.url||'')+'"></label>'+(reading?'<label>Access note<input name="access" placeholder="Free, preview, paid, etc." maxlength="200" value="'+esc(item?.access||'')+'"></label><details><summary>Additional link</summary><label>Link<input name="alt_url" type="url" value="'+esc(item?.alt_url||'')+'"></label><label>Link label<input name="alt_label" maxlength="100" value="'+esc(item?.alt_label||'')+'"></label></details>':'')+'<label>Link an imported material (optional)<select name="document"><option value="">No linked material</option>'+data.documents.map(d=>'<option value="'+esc(d.id)+'" '+(d.id===item?.document?'selected':'')+'>'+esc(galleryTitle(d))+'</option>').join('')+'</select></label><div class="later-dialog-actions"><button type="button" id="laterCancel">Cancel</button><button type="submit" class="primary">Save</button></div></form>';
 document.body.append(dialog);dialog.showModal();dialog.onclose=()=>dialog.remove();dialog.querySelector('#laterCancel').onclick=()=>dialog.close();
 dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();const fields=Object.fromEntries(new FormData(e.target).entries());try{const payload={...fields,...(item?{id:item.id}:{kind:shelfTab})};if(!reading&&fields.document)payload.status='added';await readerRequest('/api/later',payload);await loadLater();dialog.close();drawLater();notify('Saved')}catch(err){notify(err.message)}};
}
$('files').addEventListener('change',()=>{shelfTab='materials'},true);
