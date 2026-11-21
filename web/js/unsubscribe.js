const T=new URLSearchParams(location.search).get('t')||'';
function draw(i){$('#main').classList.remove('hide');const f=(k,id,to)=>{$(id).innerHTML=i.channels[k]?'<span class="pill">on</span> '+esc(to):'<span class="pill low">off</span>'};f('email','#se',i.email);f('sms','#ss',i.phone);f('whatsapp','#sw',i.phone);
 document.querySelectorAll('.off').forEach(b=>{const k=b.dataset.w;b.disabled=k==='all'?!(i.channels.email||i.channels.sms||i.channels.whatsapp):!i.channels[k]})}
(async()=>{try{draw(await api('/api/unsub/info',{t:T}))}catch(e){$('#bad').classList.remove('hide')}})();
document.addEventListener('click',async e=>{const b=e.target.closest('.off');if(!b)return;try{await api('/api/unsub/set',{t:T,what:b.dataset.w});draw(await api('/api/unsub/info',{t:T}));show($('#msg'),'ok','Done - you will not get those messages any more.')}catch(err){show($('#msg'),'err',err.message)}});
