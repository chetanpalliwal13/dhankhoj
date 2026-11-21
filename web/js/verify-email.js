const TK=new URLSearchParams(location.search).get('token')||'';
(async()=>{$('#wait').classList.remove('hide');
 if(!TK){$('#wait').classList.add('hide');$('#bad').classList.remove('hide');$('#badmsg').textContent='Open the link from your confirmation email.';const u=await session();if(u)$('#em').closest('form').querySelector('p').textContent='Signed in - send yourself a fresh link:';return}
 try{await api('/api/auth/verify-email',{token:TK});$('#wait').classList.add('hide');$('#ok').classList.remove('hide')}
 catch(e){$('#wait').classList.add('hide');$('#bad').classList.remove('hide');$('#badmsg').textContent=e.message}})();
$('#fr').addEventListener('submit',async e=>{e.preventDefault();const m=$('#rmsg');try{const r=await api('/api/auth/resend-verification',{email:$('#em').value});
 show(m,'ok','If that address still needs confirming, a new link is on its way.');if(r.dev_link)show($('#dev'),'ok','DEV MODE - confirmation link: '+r.dev_link)}catch(err){show(m,'err',err.message)}});
