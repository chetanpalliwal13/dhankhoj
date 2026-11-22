(async()=>{const root=document.getElementById('dx');if(!root)return;
 const rows=await dxLoad();let sort={k:'yield',d:-1},shown=10,tab='all';
 const $$=s=>root.querySelector(s),inr0=n=>'₹'+Number(n).toLocaleString('en-IN',{maximumFractionDigits:2}),fmtD=d=>d.toLocaleDateString('en-IN',{day:'numeric',month:'short'});
 $$('#dx-sector').innerHTML='<option value="">All sectors</option>'+DX_SECTORS.map(s=>'<option>'+esc(s)+'</option>').join('');
 const F=()=>({q:$$('#dx-q').value.trim().toLowerCase(),sector:$$('#dx-sector').value,cap:$$('#dx-cap').value,yld:+$$('#dx-yield').value,yrs:+$$('#dx-years').value,pay:+$$('#dx-pay').value||999,freq:$$('#dx-freq').value,cagr:+$$('#dx-cagr').value,exd:+$$('#dx-ex').value||9999});
 const PRE={all:{},high:{'dx-yield':3},steady:{'dx-years':10},growth:{'dx-cagr':10},soon:{'dx-ex':30}};
 function filtered(){const f=F();return rows.filter(r=>(!f.q||r.name.toLowerCase().includes(f.q)||r.sym.toLowerCase().includes(f.q))&&(!f.sector||r.sector===f.sector)&&(!f.cap||r.cap===f.cap)&&r.yield>=f.yld&&r.years>=f.yrs&&r.payout<=f.pay&&(!f.freq||r.freq===f.freq)&&r.cagr>=f.cagr&&r.exIn<=f.exd).sort((a,b)=>{const x=a[sort.k],y=b[sort.k];return(typeof x==='string'?x.localeCompare(y):x-y)*sort.d})}
 function render(){const L=filtered(),v=L.slice(0,shown);
  $$('#dx-count').textContent=L.length+' of '+rows.length+' companies';
  $$('#dx-body').innerHTML=v.length?v.map(r=>'<tr><td class="dxn"><b>'+esc(r.name)+'</b><small>'+esc(r.sym)+' <span class="pill">'+esc(r.sector)+'</span></small></td><td>'+inr0(r.price)+'</td><td>'+inr0(r.dps)+'</td><td><span class="dxy"><i style="width:'+Math.min(100,r.yield*10)+'%"></i></span><b>'+r.yield.toFixed(2)+'%</b></td><td>'+r.payout+'%</td><td>'+r.years+' yrs</td><td>'+(r.cagr>=0?'+':'')+r.cagr+'%</td><td>'+esc(r.freq)+'</td><td>'+fmtD(r.ex)+'<small>in '+r.exIn+' days</small></td></tr>').join(''):'<tr><td colspan="9" class="dxe">No companies match these filters. Try loosening one.</td></tr>';
  $$('#dx-more').classList.toggle('hide',L.length<=shown);
  root.querySelectorAll('th[data-k]').forEach(t=>{const on=t.dataset.k===sort.k;t.setAttribute('aria-sort',on?(sort.d>0?'ascending':'descending'):'none');t.classList.toggle('on',on)});
  const up=rows.filter(r=>r.exIn<=30).sort((a,b)=>a.exIn-b.exIn).slice(0,5);
  $$('#dx-up').innerHTML=up.map(r=>'<li><span><b>'+esc(r.name)+'</b><small>'+inr0(r.dps)+' / share</small></span><em>'+fmtD(r.ex)+'</em></li>').join('');
  $$('#dx-top').innerHTML=[...rows].sort((a,b)=>b.yield-a.yield).slice(0,5).map(r=>'<li><span><b>'+esc(r.name)+'</b><small>'+esc(r.sector)+'</small></span><em>'+r.yield.toFixed(1)+'%</em></li>').join('');
  $$('#dx-str').innerHTML=[...rows].sort((a,b)=>b.years-a.years).slice(0,5).map(r=>'<li><span><b>'+esc(r.name)+'</b><small>'+esc(r.sector)+'</small></span><em>'+r.years+' yrs</em></li>').join('')}
 const reset=()=>{root.querySelectorAll('.dxf input,.dxf select').forEach(e=>e.value='');shown=10};
 root.addEventListener('input',e=>{if(e.target.closest('.dxf')){shown=10;tab='all';root.querySelectorAll('.dxt button').forEach(b=>b.classList.toggle('on',b.dataset.t==='all'));render()}});
 root.addEventListener('click',e=>{
  const t=e.target.closest('.dxt button');if(t){tab=t.dataset.t;reset();Object.entries(PRE[tab]).forEach(([id,v])=>$$('#'+id).value=v);root.querySelectorAll('.dxt button').forEach(b=>b.classList.toggle('on',b===t));render();return}
  if(e.target.closest('#dx-reset')){reset();tab='all';root.querySelectorAll('.dxt button').forEach(b=>b.classList.toggle('on',b.dataset.t==='all'));render();return}
  if(e.target.closest('#dx-more')){shown+=10;render();return}
  const th=e.target.closest('th[data-k]');if(th){const k=th.dataset.k;sort=sort.k===k?{k,d:-sort.d}:{k,d:k==='name'||k==='freq'?1:-1};render()}});
 root.querySelector('.dxt button[data-t=all]').classList.add('on');render()})();
