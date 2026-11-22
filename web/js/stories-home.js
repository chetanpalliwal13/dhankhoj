(async()=>{const box=document.getElementById('stories');if(!box)return;
 try{const r=await api('/api/testimonials');if(!r.stories||!r.stories.length)return;
  const q=s=>'<figure class="st"><div class="stars-ro">'+'&#9733;'.repeat(s.rating||0)+'<span class="off">'+'&#9733;'.repeat(5-(s.rating||0))+'</span></div><blockquote>'+esc(s.quote.length>220?s.quote.slice(0,217)+'...':s.quote)+'</blockquote><figcaption><b>'+esc(s.name)+'</b>'+(s.city?', '+esc(s.city):'')+(s.recovered?' <span class="pill">Recovered '+esc(s.recovered)+'</span>':'')+'</figcaption></figure>';
  box.querySelector('.stgrid').innerHTML=r.stories.slice(0,3).map(q).join('');box.classList.remove('hide')}catch(e){}})();
