const m=$('#msg');
function row(i){return `<tr><td><input type="checkbox" class="pick" value="${esc(i.id)}" aria-label="select"></td><td>${esc(i.company)}</td><td>${esc(i.dtype||'')} ${esc(i.fy||'')}</td><td>${esc(i.folio)}</td><td class="num">${esc(i.holding??'')}</td><td class="num">${inr(i.amount)}</td><td>${i.deadline_est?esc(i.deadline_est)+'<br>'+dleft(i.days_left):'-'}</td></tr>`}
function claims(d){const c=d.claims||[];$('#myclaims').classList.toggle('hide',!c.length);
 $('#claimlist').innerHTML=c.map(x=>`<div class="expert"><div><b>Request #${x.id}</b> - ${x.count} entr${x.count>1?'ies':'y'}<br><span class="mut">${esc(x.status_text)}</span>${x.expert?`<br><span class="mut">Expert: ${esc(x.expert.name)}, ${esc(x.expert.profession)}, ${esc(x.expert.city)} (membership no. ${esc(x.expert.membership_no)})</span>`:''}${x.quote_amount!=null?`<br><b>Quote: ${inr(x.quote_amount)}</b> <span class="mut">${esc(x.quote_note||'')}</span>`:''}</div>
 <div>${x.status==='quoted'?`<button data-a="1" data-id="${x.id}" class="rsp">Accept quote</button> `:''}${['new','quoted','accepted','assigned','in_progress'].includes(x.status)?`<button data-a="0" data-id="${x.id}" class="rsp ghost">Cancel</button>`:''}</div></div>`).join('')}
function draw(d){claims(d);$('#main').classList.remove('hide');$('#verify').classList.add('hide');$('#tot').textContent=d.needs_pan?'-':inr(d.total_likely);const p=d.profile,pl=d.plan,L=d.locked;
 $('#who').textContent=`${p.name} - ${p.email} - ${p.phone}`;
 $('#needpan').classList.toggle('hide',!d.needs_pan);$('#results').classList.toggle('hide',d.needs_pan);$('#tip').classList.toggle('hide',d.dp_count>0);
 const cap=pl.companies;
 if(pl.active){const pc=cap?Math.min(100,Math.round(pl.used/cap*100)):0;
  $('#planbox').innerHTML=`<span class="pill">${esc(pl.label)} plan - active until ${esc(pl.until)}</span> <span class="mut">${cap?pl.used+' of '+cap+' companies shown in full':'Every matched company is unlocked.'}</span>`+(cap?`<div class="bar"><i style="width:${pc}%"></i></div>`:'')}
 else{const pc=Math.min(100,Math.round(pl.used/pl.free_companies*100));$('#planbox').innerHTML=`<div class="mut"><b>Free plan:</b> ${pl.used} of ${pl.free_companies} companies shown in full</div><div class="bar"><i style="width:${pc}%"></i></div>`+(pl.expired_on?`<div class="mut">Your membership ended on ${esc(pl.expired_on)}.</div>`:'')}
 const lk=$('#locked');
 if(L.entries>0){lk.classList.remove('hide');lk.innerHTML=`<b>${L.companies} more compan${L.companies>1?'ies':'y'} matched you</b><div class="mut" style="margin:6px 0 10px">${L.entries} entr${L.entries>1?'ies':'y'}${L.amount_band?', roughly '+esc(L.amount_band)+' among the likely ones':''} - hidden on your ${esc(pl.label)} plan (${cap||pl.free_companies} companies).</div><a class="btn" style="margin:0" href="/upgrade.html">${pl.active?'Upgrade your plan':'See Silver, Gold and Platinum plans'}</a>`}else lk.classList.add('hide');
 $('#rows').innerHTML=d.likely.map(row).join('')||'<tr><td colspan="7" class="mut">No likely match to show yet. We will alert you when one appears.</td></tr>';
 $('#rows2').innerHTML=d.possible.map(i=>`<tr><td>${esc(i.company)}</td><td>${esc(i.fy||'')}</td><td>${esc(i.folio)}</td></tr>`).join('')||'<tr><td class="mut">None.</td></tr>'}
async function load(){try{draw(await api('/api/dashboard'))}catch(e){
  if(e.need==='login')return location.replace('/signin.html?next=/dashboard.html');
  if(e.need==='verify_email'){$('#verify').classList.remove('hide');return}
  show(m,'err',e.message)}}
(async()=>{const u=await requireLogin();if(!u)return;if(!u.phone_verified)$('#phonebar').classList.remove('hide');load()})();
$('#bresend').addEventListener('click',async()=>{const x=$('#vmsg');try{const r=await api('/api/auth/resend-verification',{});show(x,'ok','If your email still needs confirming, a new link is on its way.');if(r.dev_link)show($('#vdev'),'ok','DEV MODE - confirmation link: '+r.dev_link)}catch(e){show(x,'err',e.message)}});
$('#creq').addEventListener('click',async()=>{const x=$('#cmsg');const ids=[...document.querySelectorAll('.pick:checked')].map(i=>+i.value);
 try{await api('/api/me/claim',{match_ids:ids,notes:$('#cnotes').value,consent:$('#cconsent').checked});show(x,'ok','Request sent. You will get a written quote by email.');load()}catch(e){show(x,'err',e.message)}});
document.addEventListener('click',async e=>{const b=e.target.closest('.rsp');if(!b)return;if(b.dataset.a==='0'&&!confirm('Cancel this request?'))return;
 try{await api('/api/me/claim/respond',{id:+b.dataset.id,accept:b.dataset.a==='1'});load()}catch(err){show(m,'err',err.message)}});
