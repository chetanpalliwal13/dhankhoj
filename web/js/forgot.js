$('#ff').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg'),b=$('#bf');m.classList.add('hide');b.disabled=true;
 try{const r=await api('/api/auth/forgot',{email:$('#em').value});
  show(m,'ok','If an account exists for that email, a reset link is on its way. Check your inbox and spam folder.');if(r.dev_link)show($('#dev'),'ok','DEV MODE - reset link: '+r.dev_link)}
 catch(err){show(m,'err',err.message)}b.disabled=false});
