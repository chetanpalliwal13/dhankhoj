const m=$('#msg');
let D=null;
const TXT={pan:'Add your PAN in your profile first',ids:'Add a DP-Client ID or folio in your profile first',address:'Add your address and PIN in your profile first'};
function left(d){if(d==null)return '-';if(d<=0)return '<span class="pill warn">date passed - may be with IEPF</span>';const y=Math.floor(d/365),mo=Math.floor((d%365)/30);
 const t=y>=1?y+' yr'+(y>1?'s':'')+(mo?' '+mo+' mo':''):(d>=30?Math.floor(d/30)+' mo '+(d%30)+' d':d+' days');return '<span class="pill'+(d<180?' warn':d<365?' low':'')+'">'+t+' left</span>'}
function row(i){const via=(i.via||[]).map(v=>'<span class="chip">'+esc(v)+'</span>').join('')||'<span class="mut">-</span>';
 return `<tr><td><input type="checkbox" class="pick" value="${esc(i.id)}" aria-label="select"></td><td><b>${esc(i.company)}</b></td><td>${esc(i.fy||'-')}<br><small class="mut">${esc(i.dtype||'')}</small></td><td class="mono">${esc(i.folio)}</td><td>${esc(i.holder||'')}</td><td class="addr">${i.address?esc(i.address)+(i.pincode?' - '+esc(i.pincode):''):'<span class="mut">hidden until confirmed'+(i.pincode?' (PIN '+esc(i.pincode)+')':'')+'</span>'}</td><td class="num">${esc(i.holding??'')}</td><td class="num"><b>${inr(i.amount)}</b></td><td>${via}</td><td>${i.deadline_est?left(i.days_left)+'<br><small class="mut">by '+esc(i.deadline_est)+'</small>':'-'}</td></tr>`}
function sorted(list){const s=$('#sort').value,a=[...list];if(s==='amt')a.sort((x,y)=>(y.amount||0)-(x.amount||0));else if(s==='due')a.sort((x,y)=>(x.days_left??1e9)-(y.days_left??1e9));else a.sort((x,y)=>x.company.localeCompare(y.company));return a}
function table(){if(!D)return;const L=sorted(D.likely);$('#rows').innerHTML=L.map(row).join('')||'<tr><td colspan="10" class="mut">No likely match to show. Try ticking more search options (name, address) or add your IDs in Profile. We also alert you when a new list adds you.</td></tr>';
 $('#foot').innerHTML=L.length?`<tr><td colspan="7" class="num"><b>Total you can likely claim</b></td><td class="num"><b>${inr(D.total_likely)}</b></td><td colspan="2"></td></tr>`:''}
function claims(d){const c=d.claims||[];$('#myclaims').classList.toggle('hide',!c.length);
 $('#claimlist').innerHTML=c.map(x=>`<div class="expert"><div><b>Request #${x.id}</b> - ${x.count} entr${x.count>1?'ies':'y'}<br><span class="mut">${esc(x.status_text)}</span>${x.expert?`<br><span class="mut">Expert: ${esc(x.expert.name)}, ${esc(x.expert.profession)}, ${esc(x.expert.city)} (membership no. ${esc(x.expert.membership_no)})</span>`:''}${x.quote_amount!=null?`<br><b>Quote: ${inr(x.quote_amount)}</b> <span class="mut">${esc(x.quote_note||'')}</span>`:''}</div>
 <div>${x.status==='quoted'?`<button data-a="1" data-id="${x.id}" class="rsp">Accept quote</button> `:''}${['new','quoted','accepted','assigned','in_progress'].includes(x.status)?`<button data-a="0" data-id="${x.id}" class="rsp ghost">Cancel</button>`:''}</div></div>`).join('')}
function draw(d){D=d;$('#sampletag').classList.toggle('hide',!d.sample);claims(d);$('#main').classList.remove('hide');$('#verify').classList.add('hide');const p=d.profile,pl=d.plan,L=d.locked;
 $('#pav').textContent=((p.name||'?').split(/\s+/).map(w=>w[0]).slice(0,2).join('')).toUpperCase();$('#pname').textContent=p.name;$('#who').textContent=`${p.email} - ${p.phone}`;
 $('#chips').innerHTML=(p.pan_masked?'<span class="chip">PAN '+esc(p.pan_masked)+'</span>':'<a class="chip warnc" href="/account.html#identity">Add PAN</a>')+(p.ids.length?p.ids.map(x=>'<span class="chip">'+esc(x)+'</span>').join(''):'<a class="chip warnc" href="/account.html#identity">Add DP-Client ID / folio</a>');
 const k=d.likely.length,coN=new Set(d.likely.map(i=>i.company)).size,dl=d.likely.map(i=>i.days_left).filter(x=>x!=null).sort((a,b)=>a-b),strong=d.likely.filter(i=>i.confidence==='high').length;
 $('#tot').textContent=d.needs_pan?'-':inr(d.total_likely);$('#totsub').textContent=k?'across '+coN+' compan'+(coN>1?'ies':'y'):'no likely match yet';
 $('#s_n').textContent=k+d.possible.length;$('#s_c').textContent=k+' likely, '+d.possible.length+' weak';
 $('#s_d').textContent=dl.length?(dl[0]<=0?'passed':dl[0]>=365?Math.round(dl[0]/36.5)/10+' yrs':dl[0]+' days'):'-';$('#s_dd').textContent=dl.length?'earliest of your entries':'';
 $('#s_h').textContent=strong;
 $('#needpan').classList.toggle('hide',!d.needs_pan);$('#results').classList.toggle('hide',d.needs_pan);$('#tip').classList.toggle('hide',d.dp_count>0);
 const has={pan:!!p.pan_masked,ids:p.ids.length>0,name:true,address:!!p.has_address};
 for(const key of ['pan','ids','name','address']){const el=$('#m_'+key),h=$('#h_'+key);el.disabled=!has[key];if(!has[key]){el.checked=false;h.innerHTML=TXT[key]+' - <a href="/account.html#'+(key==='address'?'profile':'identity')+'">open profile</a>'}
  else{h.textContent=key==='pan'?p.pan_masked:key==='ids'?p.ids.join(', '):key==='name'?p.name:'from your profile';if(!SEEN)el.checked=key!=='address'}}
 SEEN=true;
 const cap=pl.companies;
 if(pl.active){$('#planbox').innerHTML=`<span class="pill">${esc(pl.label)} plan - until ${esc(pl.until)}</span> <span class="mut">${cap?pl.used+' of '+cap+' companies in full':'all matched companies unlocked'}</span>`}
 else{$('#planbox').innerHTML=`<span class="pill low">Free plan</span> <span class="mut">${pl.used} of ${pl.free_companies} companies in full</span> <a href="/upgrade.html">Upgrade</a>`}
 const lk=$('#locked');
 if(L.entries>0){lk.classList.remove('hide');lk.innerHTML=`<b>${L.companies} more compan${L.companies>1?'ies':'y'} matched you</b><div class="mut" style="margin:6px 0 10px">${L.entries} entr${L.entries>1?'ies':'y'}${L.amount_band?', roughly '+esc(L.amount_band)+' among the likely ones':''} - hidden on your current plan.</div><a class="btn" style="margin:0" href="/upgrade.html">See plans</a>`}else lk.classList.add('hide');
 table();
 $('#rows2').innerHTML=d.possible.map(i=>`<tr><td>${esc(i.company)}</td><td>${esc(i.fy||'')}</td><td>${esc(i.folio)}</td></tr>`).join('')||'<tr><td class="mut">None.</td></tr>'}
let SEEN=false;
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

$('#sort').addEventListener('change',table);
$('#bsearch').addEventListener('click',async()=>{const x=$('#smsg');x.classList.add('hide');const modes=[...document.querySelectorAll('#srch input:checked')].map(i=>i.value);
 if(!modes.length)return show(x,'err','Tick at least one thing to search with.');const b=$('#bsearch');b.disabled=true;b.textContent='Searching...';
 try{const r=await api('/api/me/search',{modes});draw(r);$('#searchinfo').textContent=r.found+' entr'+(r.found===1?'y':'ies')+' found';document.getElementById('rows').scrollIntoView({behavior:'smooth',block:'nearest'})}catch(e){show(x,'err',e.message)}
 b.disabled=false;b.textContent='Search'});
$('#bcsv').addEventListener('click',()=>{if(!D||!D.likely.length)return;const q=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
 const rows=[['Company','Type','Year','Folio / DP-Client ID','Holder','Shares','Dividend (INR)','Matched by','Estimated IEPF date','Days left']].concat(sorted(D.likely).map(i=>[i.company,i.dtype,i.fy,i.folio,i.holder,i.holding,i.amount,(i.via||[]).join(' + '),i.deadline_est,i.days_left]));
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.map(r=>r.map(q).join(',')).join('\n')],{type:'text/csv'}));a.download='dhankhoj-unclaimed-dividends.csv';document.body.appendChild(a);a.click();a.remove()});
