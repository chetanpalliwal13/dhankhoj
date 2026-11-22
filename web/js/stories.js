(async()=>{
 const stars=n=>'&#9733;'.repeat(n||0)+'<span class="off">'+'&#9733;'.repeat(5-(n||0))+'</span>';
 try{const r=await api('/api/testimonials');
  if(r.stories&&r.stories.length)$('#list').innerHTML=r.stories.map(s=>'<figure class="st"><div class="stars-ro" aria-label="'+(s.rating||0)+' of 5">'+stars(s.rating)+'</div><blockquote>'+esc(s.quote)+'</blockquote><figcaption><b>'+esc(s.name)+'</b>'+(s.city?', '+esc(s.city):'')+(s.recovered?' <span class="pill">Recovered '+esc(s.recovered)+'</span>':'')+'</figcaption></figure>').join('');
  else $('#empty').classList.remove('hide')}catch(e){$('#empty').classList.remove('hide')}
 let rating=0;
 $('#stars').innerHTML=[1,2,3,4,5].map(n=>'<button type="button" class="star" role="radio" aria-checked="false" aria-label="'+n+' of 5" data-n="'+n+'">&#9733;</button>').join('');
 $('#stars').addEventListener('click',e=>{const s=e.target.closest('.star');if(s){rating=+s.dataset.n;document.querySelectorAll('.star').forEach(x=>{x.classList.toggle('on',+x.dataset.n<=rating);x.setAttribute('aria-checked',+x.dataset.n===rating?'true':'false')})}});
 const u=await session();if(u)$('#nm').value=u.name||'';
 $('#f').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg'),b=$('#send');m.classList.add('hide');b.disabled=true;
  try{const r=await api('/api/story',{name:$('#nm').value,email:$('#em').value,message:$('#ms').value,rating:rating||'',city:$('#ct').value,recovered:$('#rc').value,consent:$('#cs').checked,website:$('#wb').value});
   $('#ref').textContent=r.ref;$('#f').classList.add('hide');$('#done').classList.remove('hide')}
  catch(err){show(m,'err',err.message);b.disabled=false}})
})();
