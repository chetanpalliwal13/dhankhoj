(async()=>{
 let I={};try{I=await api('/api/site-info')}catch(e){}
 const ch=[];if(I.email)ch.push(['Email','<a href="mailto:'+esc(I.email)+'">'+esc(I.email)+'</a>','Best for account and payment questions']);
 if(I.phone)ch.push(['Phone','<a href="tel:'+esc(I.phone.replace(/[^\d+]/g,''))+'">'+esc(I.phone)+'</a>',esc(I.hours||'')]);
 if(I.whatsapp)ch.push(['WhatsApp','<a href="https://wa.me/'+esc(I.whatsapp)+'" rel="noopener">Chat with us</a>','Quick questions']);
 if(I.address)ch.push(['Office',esc(I.address),'By appointment']);
 ch.push(['Support hours',esc(I.hours||'Mon-Sat, 10:00 to 18:00 IST'),'We reply to every message']);
 $('#chan').innerHTML=ch.map(c=>'<div class="card"><h3>'+c[0]+'</h3><p>'+c[1]+'</p><span class="mut">'+c[2]+'</span></div>').join('');
 $('#tp').innerHTML=(I.topics||['Something else']).map(t=>'<option>'+esc(t)+'</option>').join('');
 const u=await session();if(u){$('#nm').value=u.name||'';}
 $('#f').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg'),b=$('#send');m.classList.add('hide');b.disabled=true;
  try{const r=await api('/api/contact',{name:$('#nm').value,email:$('#em').value,phone:$('#ph').value,topic:$('#tp').value,message:$('#ms').value,website:$('#wb').value});
   $('#ref').textContent=r.ref;$('#f').classList.add('hide');$('#done').classList.remove('hide');window.scrollTo(0,0)}
  catch(err){show(m,'err',err.message);b.disabled=false}})
})();
