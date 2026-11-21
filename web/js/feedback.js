(async()=>{
 let I={};try{I=await api('/api/site-info')}catch(e){}
 $('#tp').innerHTML=(I.feedback_topics||['Something else']).map(t=>'<option>'+esc(t)+'</option>').join('');
 let rating=0;const L=['','Poor','Fair','Good','Very good','Excellent'];
 $('#stars').innerHTML=[1,2,3,4,5].map(n=>'<button type="button" class="star" role="radio" aria-checked="false" aria-label="'+n+' of 5: '+L[n]+'" data-n="'+n+'">&#9733;</button>').join('');
 const paint=()=>{document.querySelectorAll('.star').forEach(s=>{const on=+s.dataset.n<=rating;s.classList.toggle('on',on);s.setAttribute('aria-checked',+s.dataset.n===rating?'true':'false')});$('#rl').textContent=L[rating]};
 $('#stars').addEventListener('click',e=>{const s=e.target.closest('.star');if(s){rating=+s.dataset.n;paint()}});
 const u=await session();if(u)$('#nm').value=u.name||'';
 $('#f').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg'),b=$('#send');m.classList.add('hide');b.disabled=true;
  try{const r=await api('/api/feedback',{name:$('#nm').value,email:$('#em').value,topic:$('#tp').value,message:$('#ms').value,rating:rating||'',website:$('#wb').value});
   $('#ref').textContent=r.ref;$('#f').classList.add('hide');$('#done').classList.remove('hide');window.scrollTo(0,0)}
  catch(err){show(m,'err',err.message);b.disabled=false}})
})();
