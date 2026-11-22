const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr=n=>{n=Number(n||0);return '₹'+n.toLocaleString('en-IN',n>=10000?{maximumFractionDigits:0}:{minimumFractionDigits:n%1?2:0,maximumFractionDigits:2})};
async function api(path,body){
  const o=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
  if(window.demoApi)return window.demoApi(path,body);
  if(new URLSearchParams(location.search).get('preview')==='1')try{localStorage.setItem('dk_preview_on','1')}catch(e){}
  let r;try{r=await fetch(path,o)}catch(e){throw new Error('Network problem. Please try again.')}
  if(!(r.headers.get('content-type')||'').includes('json')){
    let on=false;try{on=localStorage.getItem('dk_preview_on')==='1'}catch(e){}
    if(!on&&!path.startsWith('/api/plan')&&!path.startsWith('/api/site-info')&&!path.startsWith('/api/testimonials')&&path!=='/api/auth/login')throw new Error('The full app is not open to the public yet. Please check back soon.');  // no DhanKhoj server behind this address (plain static hosting): switch to the sample-data preview
    if(!window.DEMO_P)window.DEMO_P=new Promise((res,rej)=>{const s=document.createElement('script');s.src='/js/demo.js?v=1795345696';s.onload=res;s.onerror=rej;document.head.appendChild(s)});
    try{await window.DEMO_P;return window.demoApi(path,body)}catch(e){}}
  const j=await r.json().catch(()=>({ok:false,error:'Unexpected response.'}));
  if(!j.ok){const e=new Error(j.error||'Request failed');e.need=j.need;e.status=r.status;throw e}return j;
}
function show(el,type,text){el.className='msg '+type;el.textContent=text;el.classList.remove('hide')}
function dleft(d){if(d==null)return '';if(d<=0)return '<span class="pill warn">estimated IEPF date passed</span>';return '<span class="pill'+(d<180?' warn':'')+'">~'+(d>365?Math.round(d/365*10)/10+' yrs':d+' days')+' left (est.)</span>'}
// ---- session + navigation
const ME={loaded:false,user:null};
async function session(){if(!ME.loaded){try{ME.user=(await api('/api/session')).user}catch(e){ME.user=null}ME.loaded=true}return ME.user}
async function requireLogin(){const u=await session();if(!u){location.replace('/signin.html?next='+encodeURIComponent(location.pathname+location.search));return null}return u}
function safeNext(){const n=new URLSearchParams(location.search).get('next')||'';return /^\/[A-Za-z0-9_\-.\/?=&%]*$/.test(n)&&!n.startsWith('//')?n:'/dashboard.html'}
function initials(n){const p=String(n||'?').trim().split(/\s+/);return ((p[0]||'?')[0]+(p.length>1?p[p.length-1][0]:'')).toUpperCase()}
const MENU=[['/dashboard.html','Dashboard'],['/account.html#profile','Profile'],['/account.html#identity','PAN &amp; demat IDs'],['/account.html#alerts','Alerts'],['/account.html#plan','Plan &amp; payments'],['/account.html#security','Security'],['/contact.html','Help &amp; support']];
const PAGES={'/':'Home','/index.html':'Home','/dashboard.html':'Dashboard','/account.html':'Account','/upgrade.html':'Pricing','/about.html':'About us','/contact.html':'Contact & support','/feedback.html':'Feedback','/stories.html':'Customer stories','/coverage.html':'Coverage','/claim.html':'How to claim','/signin.html':'Sign in','/signup.html':'Sign up','/forgot.html':'Reset password','/reset.html':'Reset password','/terms.html':'Terms','/privacy.html':'Privacy','/admin.html':'Admin','/receipt.html':'Receipt','/experts.html':'Experts','/verify-email.html':'Confirm email','/unsubscribe.html':'Unsubscribe'};
const I_SUN='<svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
 I_MOON='<svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
 I_CHEV='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
 I_MENU='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
const curTheme=()=>document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light';
function setTheme(t){document.documentElement.setAttribute('data-theme',t);try{localStorage.setItem('dk_theme',t)}catch(e){}const b=document.getElementById('tgl');if(b)b.setAttribute('aria-label',t==='dark'?'Switch to light theme':'Switch to dark theme')}
let _shell=false;
function ensureShell(){const h=document.querySelector('header.top');if(!h||_shell)return;_shell=true;
  const nm=PAGES[location.pathname]||String(document.title||'').split(' - ')[0];
  h.querySelector('.logo').insertAdjacentHTML('afterend','<span class="hsep" aria-hidden="true">/</span><span class="hpage">'+esc(nm)+'</span>');
  h.insertAdjacentHTML('beforeend','<div class="hs" id="hs" role="search"><input id="hsq" type="search" autocomplete="off" placeholder="Search a company" aria-label="Search a company or ticker" aria-controls="hsr" aria-expanded="false"><div class="hsr hide" id="hsr" role="listbox"></div></div><div class="hr" id="hr"></div>');initSearch();
  document.addEventListener('click',e=>{
    if(e.target.closest('#tgl')){setTheme(curTheme()==='dark'?'light':'dark');return}
    const hb=e.target.closest('#hbm');if(hb){const o=document.body.classList.toggle('navopen');hb.setAttribute('aria-expanded',o?'true':'false');return}
    const b=e.target.closest('#acb'),m=document.getElementById('acm');
    if(b&&m){const open=m.classList.contains('hide');m.classList.toggle('hide',!open);b.setAttribute('aria-expanded',open?'true':'false');return}
    if(m&&!e.target.closest('.acct')){m.classList.add('hide');const x=document.getElementById('acb');if(x)x.setAttribute('aria-expanded','false')}
    if(e.target.closest('#acm a')&&m)m.classList.add('hide');
    if(!e.target.closest('#nav,#hbm'))document.body.classList.remove('navopen');
    const so=e.target.closest('#signout');if(so){e.preventDefault();api('/api/auth/logout',{}).catch(()=>{}).then(()=>location.replace('/'))}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){const m=document.getElementById('acm'),b=document.getElementById('acb');if(m&&!m.classList.contains('hide')){m.classList.add('hide');b.setAttribute('aria-expanded','false');b.focus()}document.body.classList.remove('navopen')}})}
async function buildNav(){ensureShell();const n=document.getElementById('nav'),r=document.getElementById('hr');if(!n||!r)return;const u=await session();
  n.querySelectorAll('.keep,.dsh').forEach(a=>a.remove());
  const t=curTheme(),th='<button type="button" class="tgl" id="tgl" aria-label="'+(t==='dark'?'Switch to light theme':'Switch to dark theme')+'">'+I_SUN+I_MOON+'</button>',hb='<button type="button" class="hbm" id="hbm" aria-label="Menu" aria-expanded="false">'+I_MENU+'</button>';
  if(!u){r.innerHTML=th+'<a class="hsi" href="/signin.html">Sign in</a><a class="hsu" href="/signup.html">Sign up free</a>'+hb;return}
  n.insertAdjacentHTML('afterbegin','<a class="dsh" href="/dashboard.html">Dashboard</a>');
  const pn=u.plan&&u.plan.active?'<span class="pill">'+esc(u.plan.label)+' plan</span>':'<span class="pill">Free plan</span>';
  r.innerHTML=th+'<div class="acct"><button type="button" class="achip" id="acb" aria-haspopup="true" aria-expanded="false" aria-label="Account menu"><span class="uav" aria-hidden="true">'+esc(initials(u.name))+'</span>'+I_CHEV+'</button>'+
    '<div class="amenu hide" id="acm" role="menu"><div class="umh"><span class="uav" aria-hidden="true">'+esc(initials(u.name))+'</span><div><b>'+esc(u.name)+'</b><small>'+esc(u.email)+'</small>'+pn+'</div></div>'+
    MENU.map(m=>'<a role="menuitem" href="'+m[0]+'">'+m[1]+'</a>').join('')+'<hr><a role="menuitem" href="#" id="signout">Sign out</a></div></div>'+hb}
// ---- header: grouped dropdown menus on every page
(function(){const n=document.getElementById('nav');if(!n)return;
 const dd=(t,items)=>'<div class="dd"><button type="button" class="ddb" aria-expanded="false">'+t+'</button><div class="ddp">'+items.map(i=>'<a href="'+i[0]+'">'+i[1]+'<small>'+i[2]+'</small></a>').join('')+'</div></div>';
 n.innerHTML=dd('Product',[['/dashboard.html','Dashboard','Search and track your dividends'],['/insights.html','Dividend insights','Rankings by yield, consistency and return'],['/coverage.html','Coverage','Which companies we have checked'],['/upgrade.html','Pricing','Free and paid plans']])+
  dd('Learn',[['/#how','How it works','The seven-year rule explained'],['/claim.html','How to claim','Step-by-step, free of charge'],['/#faq','Questions','Short answers']])+
  dd('Company',[['/about.html','About us','Who builds DhanKhoj'],['/contact.html','Contact &amp; support','Write to us'],['/stories.html','Customer stories','How others found their money'],['/feedback.html','Feedback','Tell us what to improve']])+'<a href="/upgrade.html">Pricing</a>';
 n.addEventListener('click',e=>{const b=e.target.closest('.ddb');document.querySelectorAll('.dd.open').forEach(d=>{if(!b||d!==b.parentElement)d.classList.remove('open')});if(b){const d=b.parentElement;d.classList.toggle('open');b.setAttribute('aria-expanded',d.classList.contains('open'))}});
 document.addEventListener('click',e=>{if(!e.target.closest('.dd'))document.querySelectorAll('.dd.open').forEach(d=>d.classList.remove('open'))});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.dd.open').forEach(d=>d.classList.remove('open'))});
 const sc=()=>document.body.classList.toggle('scrolled',scrollY>24);addEventListener('scroll',sc,{passive:true});sc()})();

// ---- header search (sample companies) and the assistant launcher. Both load their code only when first used.
function loadJS(src){return new Promise((ok,no)=>{if(document.querySelector('script[data-l="'+src+'"]'))return ok();const e=document.createElement('script');e.src=src+'?v=1795346545';e.dataset.l=src;e.onload=ok;e.onerror=no;document.head.appendChild(e)})}
let _dx=null;function loadDX(){return _dx||(_dx=loadJS('/js/divdata.js').then(()=>loadJS('/js/dxengine.js')).then(()=>window.dxLoad()))}
function initSearch(){const q=document.getElementById('hsq'),box=document.getElementById('hsr');if(!q)return;let rows=[],sel=-1,list=[];
  const close=()=>{box.classList.add('hide');q.setAttribute('aria-expanded','false');sel=-1};
  const paint=()=>{const t=q.value.trim().toLowerCase();if(!t){close();return}
    list=rows.filter(r=>r.name_l.indexOf(t)>=0).sort((a,b)=>(a.sym.toLowerCase().indexOf(t)===0?0:1)-(b.sym.toLowerCase().indexOf(t)===0?0:1)||a.name.localeCompare(b.name)).slice(0,7);
    box.innerHTML=list.length?list.map((r,i)=>'<a role="option" href="/stock.html?sym='+r.sym+'" id="hso'+i+'"><b>'+esc(r.name)+'</b><small>'+r.sym+' · '+esc(r.sector)+' · yield '+r.yield.toFixed(2)+'%</small></a>').join('')+'<a class="hsall" href="/insights.html">Browse all rankings</a>':'<p>No company matches “'+esc(q.value.trim())+'”. Try the name or ticker, or <a href="/insights.html">browse rankings</a>.</p>';
    box.classList.remove('hide');q.setAttribute('aria-expanded','true');sel=-1};
  q.addEventListener('focus',()=>{loadDX().then(r=>{rows=r;paint()}).catch(()=>{})});
  q.addEventListener('input',()=>{loadDX().then(r=>{rows=r;paint()})});
  q.addEventListener('keydown',e=>{const a=box.querySelectorAll('a[role=option]');
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(!a.length)return;e.preventDefault();sel=(sel+(e.key==='ArrowDown'?1:-1)+a.length)%a.length;a.forEach((x,i)=>x.classList.toggle('on',i===sel));q.setAttribute('aria-activedescendant',a[sel].id)}
    else if(e.key==='Enter'){const t=sel>=0?a[sel]:a[0];if(t){e.preventDefault();location.href=t.getAttribute('href')}}
    else if(e.key==='Escape'){close();q.blur()}});
  document.addEventListener('click',e=>{if(!e.target.closest('#hs'))close()})}
window.dkAssistant=window.dkAssistant||{open:function(m){loadDX().then(()=>loadJS('/js/assistant.js')).then(()=>window.dkAssistant.open(m))}};
(function(){if(document.getElementById('dka'))return;const b=document.createElement('button');b.type='button';b.id='dka';b.className='dka';b.setAttribute('aria-label','Ask the DhanKhoj assistant');b.innerHTML='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg><span>Ask</span>';b.addEventListener('click',()=>window.dkAssistant.open());document.body.appendChild(b)})();
buildNav();

// ---- Sign in with Google: buttons stay hidden until the server says it is configured
let _gopt=null;
async function googleOn(){if(_gopt===null){try{_gopt=!!(await api('/api/auth/options')).google}catch(e){_gopt=false}}return _gopt}
function googleHref(next){return '/auth/google/start?next='+encodeURIComponent(next)}
async function initGoogle(next){if(!document.querySelector('.gwrap'))return;if(!await googleOn())return;
  document.querySelectorAll('.gwrap').forEach(w=>{w.classList.remove('hide');w.querySelector('.gbtn').href=googleHref(next||safeNext())})}
const GERR={off:'Google sign-in is not set up yet. Please use your email and password.',cancelled:'Google sign-in was cancelled.',state:'That Google sign-in session expired. Please try again.',failed:'Google sign-in did not work. Please try again or use your email.',unverified:'Google has not verified that email address, so we cannot use it.'};
function googleError(el){const g=new URLSearchParams(location.search).get('gerr');if(g&&el)show(el,'err',GERR[g]||GERR.failed)}
if(!document.getElementById('lmod'))initGoogle();

// ---- signed-in visitors: skip the home page, and sign out after a few idle minutes
(async function(){const u=await session();if(!u)return;
  if(location.pathname==='/'||location.pathname==='/index.html'){location.replace('/dashboard.html');return}
  const idle=(u.idle_min||0)*60000;if(!idle)return;
  let last=Date.now(),pinged=Date.now(),warned=false,toast=null;
  const bump=()=>{last=Date.now();if(warned){warned=false;if(toast){toast.remove();toast=null}}if(Date.now()-pinged>60000){pinged=Date.now();api('/api/session/ping',{}).catch(()=>{})}};
  ['mousemove','mousedown','keydown','scroll','touchstart','click'].forEach(ev=>document.addEventListener(ev,bump,{passive:true}));
  setInterval(async()=>{const left=idle-(Date.now()-last);
    if(left<=0){try{await api('/api/auth/logout',{})}catch(_){}location.replace('/signin.html?idle=1');return}
    if(left<=30000&&!warned&&!window.PAYING){warned=true;toast=document.createElement('div');toast.className='idle-toast';toast.setAttribute('role','alert');toast.innerHTML='<span>You will be signed out soon because you have been inactive.</span>';const b=document.createElement('button');b.type='button';b.textContent='Stay signed in';b.addEventListener('click',bump);toast.appendChild(b);document.body.appendChild(toast)}
    if(window.PAYING){last=Date.now();if(Date.now()-pinged>60000){pinged=Date.now();api('/api/session/ping',{}).catch(()=>{})}}},5000)})();

// Back / forward button after sign-out: a page restored from the browser's memory is re-checked, so signed-out visitors never see account pages
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload()});

// ---- site footer (replaces each page's plain footer on every page)
(function(){document.querySelectorAll('footer').forEach(f=>f.remove());
 const f=document.createElement('footer');f.className='sitefoot';
 f.innerHTML='<div class="wrap"><div class="fcols"><div><a class="fb" href="/"><img src="/favicon.svg" width="30" height="30" alt="">DhanKhoj</a><p>Find the dividends you forgot to collect, before they move to the government fund.</p></div>'+
 '<div><h4>Product</h4><ul><li><a href="/signup.html">Create free account</a></li><li><a href="/upgrade.html">Pricing</a></li><li><a href="/coverage.html">Coverage</a></li><li><a href="/claim.html">How to claim</a></li></ul></div>'+
 '<div><h4>Company</h4><ul><li><a href="/about.html">About us</a></li><li><a href="/contact.html">Contact &amp; support</a></li><li><a href="/stories.html">Customer stories</a></li><li><a href="/feedback.html">Feedback</a></li></ul></div>'+
 '<div><h4>Legal</h4><ul><li><a href="/terms.html">Terms &amp; refunds</a></li><li><a href="/privacy.html">Privacy notice</a></li></ul></div></div>'+
 '<p class="fdisc">DhanKhoj is an independent information service. It is not affiliated with SEBI, the IEPF Authority, any stock exchange or any company, and it is not investment or legal advice. Matches are estimates from published lists and may be wrong or incomplete; deadlines shown are estimates. Always confirm with the company or its registrar.</p>'+
 '<div class="fbar"><span>&copy; '+new Date().getFullYear()+' DhanKhoj</span><span>Made in India</span></div></div>';
 document.body.appendChild(f)})();
// ---- show / hide password: adds an eye button to every password field, now and when forms are built later
(function(){
 const EYE='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
 const OFF='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.9 17.9A10.4 10.4 0 0 1 12 19C5.6 19 2 12 2 12a18 18 0 0 1 4.1-5.1M9.9 5.2A9.7 9.7 0 0 1 12 5c6.4 0 10 7 10 7a18 18 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2M2 2l20 20"/></svg>';
 function add(i){if(i.dataset.eye)return;i.dataset.eye='1';
  const w=document.createElement('span');w.className='pwwrap';i.parentNode.insertBefore(w,i);w.appendChild(i);
  const b=document.createElement('button');b.type='button';b.className='pweye';b.setAttribute('aria-label','Show password');b.setAttribute('aria-pressed','false');b.innerHTML=EYE;w.appendChild(b);
  b.addEventListener('click',()=>{const show=i.type==='password';i.type=show?'text':'password';b.innerHTML=show?OFF:EYE;b.setAttribute('aria-label',show?'Hide password':'Show password');b.setAttribute('aria-pressed',show?'true':'false');i.focus()})}
 const scan=r=>(r||document).querySelectorAll('input[type=password]').forEach(add);
 scan();new MutationObserver(m=>{for(const x of m)for(const n of x.addedNodes)if(n.nodeType===1)n.matches&&n.matches('input[type=password]')?add(n):scan(n)}).observe(document.documentElement,{childList:true,subtree:true});
})();

window.stCards=function(list,max){const L=(max?list.slice(0,max):list);
 const one=s=>'<figure class="st">'+(s.sample?'<span class="pill warn">Sample - not a real customer</span>':'')+'<div class="stars-ro" aria-label="'+(s.rating||0)+' of 5">'+'&#9733;'.repeat(s.rating||0)+'<span class="off">'+'&#9733;'.repeat(5-(s.rating||0))+'</span></div><blockquote>'+esc(s.quote)+'</blockquote><figcaption><b>'+esc(s.name)+'</b>'+(s.city?', '+esc(s.city):'')+(s.recovered?' <span class="pill">Recovered '+esc(s.recovered)+'</span>':'')+'</figcaption></figure>';
 const html=L.map(one).join('');
 return L.length>=3?'<div class="stmq" role="region" aria-label="Customer stories"><div class="sttrack">'+html+'<span aria-hidden="true" class="stdup">'+html+'</span></div></div>':'<div class="stgrid">'+html+'</div>'};

// ---- sign in / sign up popup (script loads the first time it is needed)
const _CS=document.currentScript;let _amp=null;
window.openAuth=function(mode,opts){if(!_amp)_amp=new Promise((ok,no)=>{const sc=document.createElement('script');sc.src='/js/auth-modal.js'+((_CS&&_CS.src.split('?')[1])?'?'+_CS.src.split('?')[1]:'');sc.onload=ok;sc.onerror=no;document.head.appendChild(sc)});
  return _amp.then(()=>window._openAuth(mode,opts))};
document.addEventListener('click',e=>{if(e.defaultPrevented||e.button||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;
  const a=e.target.closest('a[href]');if(!a||a.target==='_blank')return;const m=/^\/(signin|signup)\.html(\?(.*))?$/.exec(a.getAttribute('href')||'');if(!m)return;
  if(location.pathname==='/'+m[1]+'.html')return;e.preventDefault();const nx=new URLSearchParams(m[3]||'').get('next');openAuth(m[1],nx&&/^\/[A-Za-z0-9_\-.\/?=&%]*$/.test(nx)&&!nx.startsWith('//')?{next:nx}:{})});
