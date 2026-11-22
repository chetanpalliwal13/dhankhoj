(function(){
const $=id=>document.getElementById(id),esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])),F=window.dxFmt,E=window.DX;
const G={
 'Size':[
  {t:'Largest companies that pay dividends',q:{metric:'mcap',cap:'Large'}},
  {t:'Best mid-size dividend payers',q:{metric:'yield',cap:'Mid'},s:'By yield'},
  {t:'Best small-company dividend payers',q:{metric:'yield',cap:'Small'},s:'By yield'}],
 'Dividend yield':[
  {t:'Highest dividend yield',q:{metric:'yield'}},
  {t:'High yield, with a safe payout',q:{metric:'yield',maxPayout:50,min:2},s:'Yield 2% or more, payout 50% or less'},
  {t:'High yield but a stretched payout',q:{metric:'yield',min:3,dir:'desc'},w:1,s:'Yield 3% or more. Check the payout before relying on it'}],
 'Consistency':[
  {t:'Most consistent: years paid in a row',q:{metric:'years'}},
  {t:'Most dividend payouts in 10 years',q:{metric:'pays'}},
  {t:'Fastest dividend growth',q:{metric:'growth',years:5}},
  {t:'Safest payers: lowest payout ratio',q:{metric:'payout',years:8}}],
 'Dividends received':['1m','3m','6m',1,3,5,10].map(p=>({t:'Best dividend return, '+E.PL[E.pk(p)],q:{metric:'divret',period:p},s:'Dividends received as a share of the starting price'})),
 'Total return':['1m','3m','6m',1,3,5,10].map(p=>({t:'Best total return of dividend payers, '+E.PL[E.pk(p)],q:{metric:'totalret',period:p},s:'Price change plus dividends'})),
 'Payment pattern':['Quarterly','Half-yearly','Annual'].map(f=>({t:'Best '+f.toLowerCase()+' payers, dividend return in 1 year',q:{metric:'divret',period:'1y',freq:f},s:f+' payers ranked by dividends received'})),
 'Upcoming':[
  {t:'Next ex-dividend dates',q:{metric:'ex'}},
  {t:'Quarterly payers with the highest yield',q:{metric:'yield',freq:'Quarterly'}}]
};
let rows=[],cur='Dividend yield';
function card(b){const o=Object.assign({n:5},b.q),res=E.query(rows,o),per=res.m.per?res.period:0;
 return '<article class="dxcard ins-card'+(b.w?' warn':'')+'"><h3>'+esc(b.t)+'</h3>'+(b.s?'<p class="ins-s">'+esc(b.s)+'</p>':'')+'<ol>'+res.items.map(x=>'<li><a href="/stock.html?sym='+x.r.sym+'"><b>'+esc(x.r.name)+'</b><small>'+x.r.sym+' · '+esc(x.r.sector)+' · yield '+F.pc(x.r.yield)+'</small></a><em>'+res.m.fmt(x.v)+'</em></li>').join('')+'</ol>'+(res.items.length?'':'<p class="mut">No company matches.</p>')+'<a class="ins-all" href="'+E.link(Object.assign({n:20},b.q))+'" data-q=\''+esc(JSON.stringify(b.q))+'\'>See the full list</a></article>'}
function tabs(){$('grp').innerHTML=Object.keys(G).map(k=>'<button type="button" role="tab" class="'+(k===cur?'on':'')+'" aria-selected="'+(k===cur)+'" data-g="'+esc(k)+'">'+esc(k)+'</button>').join('');
 $('boards').innerHTML=G[cur].map(card).join('')}
function ctl(){const o={metric:$('c-metric').value,period:$('c-per').value,freq:$('c-freq').value,cap:$('c-cap').value,sector:$('c-sec').value,min:$('c-min').value,years:$('c-yrs').value,n:+$('c-n').value};
 const m=E.M[o.metric];$('c-per-w').style.display=m.per?'':'none';
 const r=E.query(rows,o);$('c-vh').textContent=m.per?m.label.split(' (')[0]+' · '+String(E.pk(r.period)).replace(/^(\d+)$/,'$1y').toUpperCase():m.label.replace(/ \(.*/,'');
 $('c-note').textContent=m.note+'. '+r.total+' of '+rows.length+' companies match.';
 $('c-body').innerHTML=r.items.length?r.items.map((x,i)=>'<tr><td>'+(i+1)+'</td><td><a href="/stock.html?sym='+x.r.sym+'"><b>'+esc(x.r.name)+'</b></a><small>'+x.r.sym+'</small></td><td>'+esc(x.r.sector)+'</td><td>'+x.r.cap+'</td><td class="r">'+F.rs(x.r.price)+'</td><td class="r">'+F.pc(x.r.yield)+'</td><td class="r"><b>'+m.fmt(x.v)+'</b></td><td class="r">'+x.r.years+'</td></tr>').join(''):'<tr><td colspan="8" class="mut">No company matches these filters. Lower the minimum yield or years.</td></tr>'}
function setCtl(q){q=q||{};$('c-metric').value=q.metric||'yield';$('c-per').value=String(E.pk(q.period||'5y')).replace(/^(\d+)$/,'$1y');$('c-freq').value=q.freq||'';$('c-cap').value=q.cap||'';$('c-sec').value=q.sector||'';$('c-min').value=q.min||'';$('c-yrs').value=q.years||'';$('c-n').value=[10,20,38].indexOf(+q.n)>=0?q.n:10;ctl()}
window.dxLoad().then(r=>{rows=r;
 $('c-metric').innerHTML=Object.keys(E.M).map(k=>'<option value="'+k+'">'+esc(E.M[k].label)+'</option>').join('');
 $('c-sec').insertAdjacentHTML('beforeend',window.DX_SECTORS.map(s=>'<option>'+esc(s)+'</option>').join(''));
 const u=new URLSearchParams(location.search),q={};u.forEach((v,k)=>q[k]=v);
 tabs();setCtl(q);
 if(u.has('metric'))setTimeout(()=>$('table').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'}),60)});
document.addEventListener('click',e=>{const t=e.target.closest('#grp button');if(t){cur=t.dataset.g;tabs();return}
 const a=e.target.closest('.ins-all');if(a){e.preventDefault();const q=JSON.parse(a.dataset.q);q.n=20;setCtl(q);history.replaceState(null,'',a.getAttribute('href').split('#')[0]);$('table').scrollIntoView({behavior:'smooth'});return}
 if(e.target.id==='c-reset'){setCtl({});return}
 if(e.target.id==='askai'&&window.dkAssistant)window.dkAssistant.open()});
['c-metric','c-per','c-freq','c-cap','c-sec','c-min','c-yrs','c-n'].forEach(i=>{const el=$(i);el.addEventListener('input',ctl);el.addEventListener('change',ctl)});
})();
