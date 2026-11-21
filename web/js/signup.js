(async()=>{if(await session())location.replace('/dashboard.html')})();
let EMAIL='';
$('#sp').addEventListener('change',e=>{$('#pw').type=e.target.checked?'text':'password'});
$('#fsu').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg'),b=$('#bsu');m.classList.add('hide');
 if(!$('#co').checked)return show(m,'err','Please confirm you are 18+ and accept the Terms and Privacy Notice.');
 b.disabled=true;
 try{EMAIL=$('#em').value.trim();
  const r=await api('/api/auth/signup',{first_name:$('#fn').value,last_name:$('#ln').value,mobile:$('#mo').value,email:EMAIL,password:$('#pw').value,consent:true});
  $('#boxform').classList.add('hide');$('#done').classList.remove('hide');$('#demail').textContent=r.email;
  if(r.dev_link)show($('#dev'),'ok','DEV MODE - confirmation link: '+r.dev_link);window.scrollTo(0,0)}
 catch(err){show(m,'err',err.message)}b.disabled=false});
$('#bres').addEventListener('click',async()=>{const m=$('#dmsg');try{const r=await api('/api/auth/resend-verification',{email:EMAIL});show(m,'ok','If that address still needs confirming, a new link is on its way.');if(r.dev_link)show($('#dev'),'ok','DEV MODE - confirmation link: '+r.dev_link)}catch(err){show(m,'err',err.message)}});
