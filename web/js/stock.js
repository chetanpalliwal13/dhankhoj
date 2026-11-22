(function(){
const root=document.getElementById('st'),F=window.dxFmt,esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
let R=null,rng=60;
function mdate(i,N){const d=new Date();d.setDate(1);d.setMonth(d.getMonth()-(N-1-i));return MN[d.getMonth()]+' '+d.getFullYear()}
function chart(){const all=R.hist,N=all.length,k=Math.min(rng+1,N),px=all.slice(N-k),off=N-k;
 const W=720,H=300,L=52,B=28,T=12,Rr=12,mn=Math.min(...px)*.97,mx=Math.max(...px)*1.03;
 const x=i=>L+i*(W-L-Rr)/(k-1),y=v=>T+(1-(v-mn)/(mx-mn))*(H-T-B);
 const d=px.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join('');
 const up=px[k-1]>=px[0];let g='';for(let i=0;i<=4;i++){const v=mn+(mx-mn)*i/4,yy=y(v);g+='<line x1="'+L+'" x2="'+(W-Rr)+'" y1="'+yy+'" y2="'+yy+'" class="gl"/><text x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end" class="ax">'+Math.round(v).toLocaleString('en-IN')+'</text>'}
 let xl='';const st=Math.max(1,Math.round((k-1)/5));for(let i=0;i<k-1;i+=st)xl+='<text x="'+x(i)+'" y="'+(H-8)+'" text-anchor="middle" class="ax">'+mdate(off+i,N).replace(/ \d\d(\d\d)$/,' ’$1')+'</text>';
 // dividend markers: each payout sits in an evenly spaced month of its year
 let dm='';const now=new Date(),yr=now.getFullYear();
 R.divs.forEach(dv=>{for(let j=0;j<dv.n;j++){const mon=dv.n===1?5:dv.n===2?[4,10][j]:[1,4,7,10][j];const back=(yr-dv.y)*12+(now.getMonth()-mon);const gi=N-1-back;if(back<0||gi<off||gi>=N)continue;const i=gi-off;dm+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(all[gi]).toFixed(1)+'" r="4.5" class="dm"><title>Dividend '+F.rs(dv.dps/dv.n)+' · '+MN[mon]+' '+dv.y+'</title></circle>'}});
 return '<svg viewBox="0 0 '+W+' '+H+'" class="pc" role="img" aria-label="Price chart for '+esc(R.name)+', sample data" id="pcs">'+g+xl+'<path d="'+d+'L'+x(k-1)+' '+(H-B)+'L'+L+' '+(H-B)+'Z" class="pa '+(up?'u':'d')+'"/><path d="'+d+'" class="pl '+(up?'u':'d')+'"/>'+dm+'<line id="pcx" class="cx" y1="'+T+'" y2="'+(H-B)+'" x1="0" x2="0" style="display:none"/><circle id="pcd" r="5" class="cd" style="display:none"/></svg>'}
function render(){const r=R,rt=r.ret;
 const sim=window.DX.query(window.__rows.filter(z=>z.sym!==r.sym&&z.sector===r.sector),{metric:'yield',n:4}).items;
 const rb=p=>rt[p]&&(typeof p==='string'?r.years>=1:r.years>=p)?'<tr><td>'+window.DX.PL[p]+'</td><td class="r">'+F.pct(rt[p].price,0)+'</td><td class="r">'+F.pc(rt[p].div,1)+'</td><td class="r"><b>'+F.pct(rt[p].total,0)+'</b></td><td class="r">'+rt[p].pays+'</td></tr>':'<tr><td>'+p+' year'+(p>1?'s':'')+'</td><td class="r mut" colspan="4">Not enough dividend history</td></tr>';
 const mxd=Math.max(...r.divs.map(d=>d.dps),1);
 const bars=r.divs.slice().reverse().map(d=>'<div class="dvbc"><i style="height:'+Math.max(2,Math.round(d.dps/mxd*140))+'px" class="'+(d.dps?'':'z')+'"></i><span>'+String(d.y).slice(2)+'</span><small>'+(d.dps?F.rs(d.dps):'–')+'</small></div>').join('');
 document.title=r.name+' ('+r.sym+') - DhanKhoj';
 root.innerHTML='<div class="st-h"><div><p class="st-c"><a href="/insights.html">Dividend insights</a> / '+esc(r.sector)+'</p><h1>'+esc(r.name)+' <span>'+r.sym+'</span></h1><p class="mut"><span class="samp">Sample data</span>Made-up company for this preview.</p></div><div class="st-p"><b>'+F.rs(r.price)+'</b><span class="'+(r.chg1>=0?'pos':'neg')+'">'+F.pct(r.chg1,1)+' in 1 year</span></div></div>'+
 '<div class="dxcard st-ch"><div class="dxt" id="rg">'+[[12,'1Y'],[36,'3Y'],[60,'5Y'],[120,'10Y']].map(a=>'<button type="button" class="'+(a[0]===rng?'on':'')+'" data-r="'+a[0]+'">'+a[1]+'</button>').join('')+'</div><div id="chw">'+chart()+'</div><p class="mut st-lg"><i class="lg-l"></i>Price <i class="lg-d"></i>Dividend paid <span id="pcv"></span></p></div>'+
 '<div class="st-stats">'+[['Dividend yield',F.pc(r.yield)],['Yearly dividend',F.rs(r.dps)+' a share'],['Years paid in a row',r.years],['Payout ratio',r.payout+'%'],['Payment pattern',r.freq],['Dividend growth, 5Y a year',F.pc(r.cagr,0)],['Market cap',F.cr(r.mcap)],['Next ex-dividend date',r.exIn===0?'Today':'in '+r.exIn+' days']].map(a=>'<div class="dxcard"><small>'+a[0]+'</small><b>'+a[1]+'</b></div>').join('')+'</div>'+
 '<div class="st-two"><div class="dxcard"><h3>What you would have earned</h3><div class="ins-tw st-tw"><table class="ins-t"><thead><tr><th>Period</th><th class="r">Price</th><th class="r">Dividends</th><th class="r">Total</th><th class="r">Payouts</th></tr></thead><tbody>'+['1m','3m','6m',1,3,5,10].map(rb).join('')+'</tbody></table></div></div>'+
 '<div class="dxcard"><h3>Dividend a share, by year</h3><div class="dvb">'+bars+'</div></div></div>'+
 (sim.length?'<div class="dxcard"><h3>Other '+esc(r.sector)+' dividend payers</h3><ul>'+sim.map(x=>'<li><a href="/stock.html?sym='+x.r.sym+'"><b>'+esc(x.r.name)+'</b><small>'+x.r.sym+'</small></a><em>'+F.pc(x.r.yield)+'</em></li>').join('')+'</ul></div>':'')+
 '<p class="st-ask"><button type="button" class="btn" id="askst">Ask the assistant about '+esc(r.name)+'</button></p><p class="mut st-note">Figures and chart use sample data and are for information only, not investment advice. Past dividends do not promise future ones.</p>';
 bind()}
function bind(){const s=document.getElementById('pcs');if(!s)return;const px=R.hist,N=px.length,k=Math.min(rng+1,N),off=N-k,W=720,L=52,Rr=12;
 const cx=document.getElementById('pcx'),cd=document.getElementById('pcd'),v=document.getElementById('pcv');
 const mn=Math.min(...px.slice(off))*.97,mx=Math.max(...px.slice(off))*1.03,H=300,T=12,B=28;
 function mv(e){const b=s.getBoundingClientRect(),X=(e.clientX-b.left)/b.width*W;let i=Math.round((X-L)/(W-L-Rr)*(k-1));i=Math.max(0,Math.min(k-1,i));const xx=L+i*(W-L-Rr)/(k-1),yy=T+(1-(px[off+i]-mn)/(mx-mn))*(H-T-B);
  cx.setAttribute('x1',xx);cx.setAttribute('x2',xx);cx.style.display='';cd.setAttribute('cx',xx);cd.setAttribute('cy',yy);cd.style.display='';v.textContent=mdate(off+i,N)+': '+F.rs(px[off+i])}
 s.addEventListener('pointermove',mv);s.addEventListener('pointerleave',()=>{cx.style.display='none';cd.style.display='none';v.textContent=''})}
document.addEventListener('click',e=>{const b=e.target.closest('#rg button');if(b&&R){rng=+b.dataset.r;document.querySelectorAll('#rg button').forEach(x=>x.classList.toggle('on',x===b));document.getElementById('chw').innerHTML=chart();bind();return}
 if(e.target.id==='askst'&&window.dkAssistant)window.dkAssistant.open('Tell me about '+R.name)});
window.dxLoad().then(rows=>{window.__rows=rows;const sym=(new URLSearchParams(location.search).get('sym')||'').toUpperCase();R=window.DX_BY[sym];
 if(!R){root.innerHTML='<h1>Company not found</h1><p>We could not find “'+esc(sym||'')+'” in the sample data. Use the search at the top, or <a href="/insights.html">browse the rankings</a>.</p>';return}
 render()});
})();
