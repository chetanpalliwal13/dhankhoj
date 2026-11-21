const TK=new URLSearchParams(location.search).get('token')||'';
(async()=>{let ok=false;try{ok=TK&&(await api('/api/auth/reset-check',{token:TK})).valid}catch(e){}$(ok?'#fr':'#bad').classList.remove('hide')})();
$('#fr').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg'),b=$('#br');m.classList.add('hide');
 if($('#pw').value!==$('#pw2').value)return show(m,'err','The two passwords do not match.');b.disabled=true;
 try{await api('/api/auth/reset',{token:TK,password:$('#pw').value});$('#fr').classList.add('hide');$('#ok').classList.remove('hide')}
 catch(err){show(m,'err',err.message);if(err.status===410){$('#fr').classList.add('hide');$('#bad').classList.remove('hide')}}b.disabled=false});
