/* Signed-in dashboard extras: watchlist (kept in this browser for now) and dividend picks. Sample data until real data is connected. */
(function(){
const F=window.dxFmt,E=window.DX,esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function host(){const d=document.getElementById('dstats');if(!d)return null;let h=document.getElementById('mkt');if(!h){d.insertAdjacentHTML('afterend','<section id="mkt" class="mkt"></section>');h=document.getElementById('mkt')}return h}
function mini(t,sub,res,more){return '<div class="dxcard"><h3>'+esc(t)+'</h3><p class="ins-s">'+esc(sub)+'</p><ul>'+res.items.map(x=>'<li><a href="/stock.html?sym='+x.r.sym+'"><b>'+esc(x.r.name)+'</b><small>'+x.r.sym+' · '+esc(x.r.sector)+'</small></a><em>'+res.m.fmt(x.v)+'</em></li>').join('')+'</ul><a class="ins-all" href="'+more+'">See the full ranking</a></div>'}
function paint(rows){const h=host();if(!h)return;const w=E&&window.dkWatch.get().map(s=>rows.find(r=>r.sym===s)).filter(Boolean);
 const wl=w.length?'<ul>'+w.map(r=>'<li><a href="/stock.html?sym='+r.sym+'"><b>'+esc(r.name)+'</b><small>'+r.sym+' · yield '+F.pc(r.yield)+' · next ex-date '+(r.exIn===0?'today':'in '+r.exIn+' days')+'</small></a><button type="button" class="wx" data-s="'+r.sym+'" aria-label="Remove '+esc(r.name)+' from watchlist">Remove</button></li>').join('')+'</ul>':'<p class="mut">You are not following any company yet. Open a company and press “Add to watchlist”, then it shows up here with its next dividend date.</p><a class="btn ghost" style="margin:6px 0 0" href="/insights.html">Browse dividend rankings</a>';
 const q=o=>E.query(rows,Object.assign({n:5},o));
 h.innerHTML='<div class="mkt-h"><h2>Dividend markets</h2><span class="samp">Sample data</span></div><div class="mkt-g"><div class="dxcard mkt-w"><h3>My watchlist</h3>'+wl+'</div>'+
  mini('Next ex-dividend dates','Hold the share before this date to receive the dividend',q({metric:'ex'}),'/insights.html?metric=ex')+
  mini('Highest yield, safe payout','Yield 2% or more, payout 50% or less',q({metric:'yield',min:2,maxPayout:50}),E.link({metric:'yield',min:2,maxPayout:50}))+
  mini('Most consistent payers','Years paid in a row',q({metric:'years'}),'/insights.html?metric=years')+'</div><p class="mut mkt-n">Your watchlist is saved in this browser for now. It will follow your account once the full app is connected. Information only, not investment advice.</p>'}
function init(){const go=()=>{if(!document.getElementById('dstats'))return false;window.dxLoad().then(r=>{paint(r);document.getElementById('mkt').addEventListener('click',e=>{const b=e.target.closest('.wx');if(b){window.dkWatch.toggle(b.dataset.s);paint(r)}})});return true};
 if(!go()){const t=setInterval(()=>{if(go())clearInterval(t)},400);setTimeout(()=>clearInterval(t),15000)}}
init();
})();
