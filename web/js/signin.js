(async()=>{if(await session())location.replace(safeNext())})();
$('#fli').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg'),b=$('#bli');m.classList.add('hide');b.disabled=true;
 try{await api('/api/auth/login',{email:$('#em').value,password:$('#pw').value});location.href=safeNext()}
 catch(err){show(m,'err',err.message);b.disabled=false}});

googleError($('#msg'));
