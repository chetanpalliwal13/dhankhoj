const m=$('#msg');let P=null;
const list=v=>v.split(',').map(s=>s.trim()).filter(Boolean);
function dpRows(vals){const max=P.max_dp,v=vals.length?vals:[''];
 $('#dps').innerHTML=v.map(x=>`<div class="dprow" style="display:flex;gap:8px;align-items:center;margin:6px 0"><input type="text" class="dp" maxlength="30" placeholder="e.g. IN30047610123456" value="${esc(x)}" aria-label="DP-Client ID or folio" style="margin:0;max-width:340px">${v.length>1?'<button type="button" class="rmdp ghost" style="margin:0" aria-label="remove">&times;</button>':''}</div>`).join('');
 $('#adddp').classList.toggle('hide',v.length>=max)}
const dpVals=()=>[...document.querySelectorAll('.dp')].map(i=>i.value.trim()).filter(Boolean);
function fill(p){P=p;$('#fn').value=p.first_name;$('#mn').value=p.middle_name;$('#ln').value=p.last_name;$('#em').value=p.email;$('#mo').value=p.mobile;$('#am').value=p.alt_mobile;
 $('#dob').value=p.dob;$('#fa').value=p.father_name;$('#ad').value=p.address;$('#ci').value=p.city;$('#st').value=p.state;$('#pin').value=p.pincode;$('#lg').value=p.lang;$('#al').value=p.aliases.join(', ');
 $('#maxdp').textContent=p.max_dp;dpRows(p.folios);
 if(p.pan_set){$('#pan').value=p.pan_masked;$('#pan').disabled=true;$('#panhint').innerHTML='<span class="pill">PAN saved</span> It cannot be changed here. If it is wrong, contact support.'}
 else{$('#pan').disabled=false;$('#pan').value='';$('#panhint').textContent='Required to start the search. Check it carefully - once saved it cannot be changed.'}
 $('#emst').innerHTML=p.email_verified?'<span class="pill">email confirmed</span>':'<span class="pill warn">not confirmed yet</span> - use the link we emailed';
 const pl=p.plan;$('#ce').checked=p.channels.email;$('#cs').checked=p.channels.sms;$('#cw').checked=p.channels.whatsapp;$('#lemail').textContent=p.email;
 $('#cs').disabled=!pl.sms&&!p.channels.sms;$('#cw').disabled=!pl.whatsapp&&!p.channels.whatsapp;
 const tag=(on,incl,need)=>!incl?(on?' <span class="pill warn">paused - not in your '+esc(pl.label)+' plan</span>':' <span class="pill paid">'+need+' plan and above</span> <a href="/upgrade.html">Upgrade</a>'):'';
 $('#phonebox').classList.toggle('hide',p.phone_verified);$('#phonetxt').textContent=p.mobile?'Your number +91 '+p.mobile+' is not verified yet. We text a one-time code to it.':'Add your mobile number in the form above and save it. Then you can verify it here to get SMS / WhatsApp alerts.';
 $('#lsms').innerHTML=(p.phone_verified?'To +91 '+p.mobile+' (verified)':'Needs a verified mobile number')+tag(p.channels.sms,pl.sms,'Silver');
 $('#lwa').innerHTML=(p.phone_verified?'To +91 '+p.mobile+' (verified). Sent only if this is on.':'Needs a verified mobile number. Sent only if you switch this on.')+tag(p.channels.whatsapp,pl.whatsapp,'Gold')}
async function loadPlan(){const [s,pl,h]=await Promise.all([api('/api/session'),api('/api/plan'),api('/api/account/payments')]);const pn=s.user.plan;
 $('#planinfo').innerHTML=(pn.active?`<p><span class="pill">${esc(pn.label)}</span> active until <b>${esc(pn.until)}</b>. ${pn.companies?'Up to '+pn.companies+' companies in full.':'Every matched company is unlocked.'}</p>`:`<p><b>Free plan</b> - ${pn.free_companies} companies shown in full, email alerts.${pn.expired_on?' Your membership ended on '+esc(pn.expired_on)+'.':''}</p>`)+
  `<a class="btn" style="margin-top:0" href="/upgrade.html">${pn.active?'Extend or change plan':'See Silver, Gold and Platinum plans'}</a>`;
 $('#pays').innerHTML=h.payments.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.item||'')}</td><td>${x.status==='paid'&&x.amount?`<a href="/receipt.html?id=${x.id}">${esc(x.receipt_no||'')}</a>`:esc(x.receipt_no||'-')}</td><td>${x.status==='pending_review'?'<span class="pill low">awaiting confirmation</span>':x.status==='rejected'?'<span class="pill warn">not confirmed</span> <span class="mut">'+esc(x.note||'')+'</span>':'<span class="pill">paid</span>'}</td><td class="num">${x.amount?inr(x.amount):'free grant'}</td></tr>`).join('')||'<tr><td colspan="5" class="mut">No payments yet.</td></tr>'}
(async()=>{const u=await requireLogin();if(!u)return;
 try{const o=await api('/api/form-options');$('#st').insertAdjacentHTML('beforeend',o.states.map(s=>`<option>${esc(s)}</option>`).join(''));$('#lg').insertAdjacentHTML('beforeend',o.langs.map(s=>`<option>${esc(s)}</option>`).join(''));
  fill(await api('/api/account/profile'));$('#main').classList.remove('hide');await loadPlan()}catch(e){show(m,'err',e.message)}
 if(location.hash)document.getElementById(location.hash.slice(1))?.scrollIntoView()})();
const PANRE=/^[A-Z]{3}[ABCFGHJKLPT][A-Z][0-9]{4}[A-Z]$/;
function panCheck(){const v=$('#pan').value,h=$('#panhint');if(P&&P.pan_set)return;if(!v){h.textContent='Required to start the search. Check it carefully - once saved it cannot be changed.';h.className='hint';return}
 if(v.length<10){h.textContent=v.length+' of 10 characters';h.className='hint';return}
 if(PANRE.test(v)){h.textContent='Looks like a valid PAN.';h.className='hint okk';return}
 h.className='hint badd';h.textContent=/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(v)?'The 4th letter must be A, B, C, F, G, H, J, K, L, P or T (P for an individual). Yours is "'+v[3]+'".':'A PAN is 5 letters, 4 digits, then 1 letter.'}
$('#pan').addEventListener('input',e=>{e.target.value=e.target.value.toUpperCase().replace(/[^A-Z0-9]/g,'');$('#imsg').classList.add('hide');panCheck()});
$('#fi').addEventListener('input',()=>$('#imsg').classList.add('hide'));
function goHash(){const id=location.hash.slice(1);const el=id&&document.getElementById(id);if(el){el.scrollIntoView({behavior:'smooth'});el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),1600)}}
window.addEventListener('hashchange',goHash);
$('#adddp').addEventListener('click',()=>{const v=[...document.querySelectorAll('.dp')].map(i=>i.value);if(v.length<P.max_dp){v.push('');dpRows(v);document.querySelectorAll('.dp')[v.length-1].focus()}});
document.addEventListener('click',e=>{const b=e.target.closest('.rmdp');if(!b)return;const rows=[...document.querySelectorAll('.dprow')];const i=rows.indexOf(b.closest('.dprow'));const v=[...document.querySelectorAll('.dp')].map(x=>x.value);v.splice(i,1);dpRows(v)});
$('#fi').addEventListener('submit',async e=>{e.preventDefault();const x=$('#imsg');x.classList.add('hide');const body={folios:dpVals(),aliases:list($('#al').value)};
 if(!P.pan_set&&$('#pan').value){if(!PANRE.test($('#pan').value))return show(x,'err',$('#panhint').textContent||'Check your PAN.');if(!confirm('Save PAN '+$('#pan').value+'? It cannot be changed afterwards.'))return;body.pan=$('#pan').value}
 else if(!P.pan_set)return show(x,'err','Enter your PAN - the search cannot start without it.');
 try{fill(await api('/api/account/profile',body));show(x,'ok','Saved. We are searching the lists with your PAN and IDs - see your dashboard.')}catch(err){show(x,'err',err.message)}});
$('#fp').addEventListener('submit',async e=>{e.preventDefault();const x=$('#pmsg');x.classList.add('hide');
 try{fill(await api('/api/account/profile',{first_name:$('#fn').value,middle_name:$('#mn').value,last_name:$('#ln').value,mobile:$('#mo').value,alt_mobile:$('#am').value,dob:$('#dob').value,father_name:$('#fa').value,address:$('#ad').value,
  city:$('#ci').value,state:$('#st').value,pincode:$('#pin').value,lang:$('#lg').value}));show(x,'ok','Saved. We re-checked the lists with your updated details.')}catch(err){show(x,'err',err.message)}});
for(const k of ['ce','cs','cw'])$('#'+k).addEventListener('change',async()=>{const x=$('#amsg');
 try{const r=await api('/api/account/channels',{channels:{email:$('#ce').checked,sms:$('#cs').checked,whatsapp:$('#cw').checked}});show(x,'ok','Saved: '+Object.entries(r.channels).map(([a,b])=>a+' '+(b?'on':'off')).join(', ')+'.')}
 catch(err){show(x,'err',err.message);const p=await api('/api/account/profile');fill(p);if(err.need==='verify_phone')$('#phonebox').scrollIntoView({behavior:'smooth'})}});
$('#bsend').addEventListener('click',async()=>{const x=$('#omsg');try{const r=await api('/api/account/phone/send-otp',{});$('#phonestep2').classList.remove('hide');show(x,'ok','Code sent. It is valid for 10 minutes.');if(r.dev_otp)show($('#odev'),'ok','DEV MODE code: '+r.dev_otp)}catch(err){show(x,'err',err.message)}});
$('#bvo').addEventListener('click',async()=>{const x=$('#omsg');try{await api('/api/account/phone/verify',{otp:$('#otp').value});fill(await api('/api/account/profile'));show($('#amsg'),'ok','Mobile verified. You can now switch on the alert channels your plan includes.')}catch(err){show(x,'err',err.message)}});
$('#fpw').addEventListener('submit',async e=>{e.preventDefault();const x=$('#wmsg');if($('#np').value!==$('#np2').value)return show(x,'err','The two new passwords do not match.');
 try{await api('/api/account/password',{current:$('#cur').value,new:$('#np').value});show(x,'ok','Password changed. Other devices were signed out.');$('#fpw').reset()}catch(err){show(x,'err',err.message)}});
$('#bdel').addEventListener('click',async()=>{const x=$('#dmsg');if(!confirm('Delete your account and all stored data? This cannot be undone.'))return;
 try{await api('/api/account/delete',{password:$('#dp').value});location.href='/?deleted=1'}catch(err){show(x,'err',err.message)}});
