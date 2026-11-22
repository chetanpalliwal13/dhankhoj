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
    if(!window.DEMO_P)window.DEMO_P=new Promise((res,rej)=>{const s=document.createElement('script');s.src='/js/demo.js?v=1795339562';s.onload=res;s.onerror=rej;document.head.appendChild(s)});
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
async function buildNav(){const n=document.getElementById('nav');if(!n)return;const u=await session();
  n.querySelectorAll('.keep').forEach(a=>a.remove());
  if(!u){n.insertAdjacentHTML('beforeend','<a class="keep" href="/signin.html">Sign in</a><a class="keep" href="/signup.html">Sign up free</a>');return}
  if(!n.querySelector('a[href="/dashboard.html"]:not(.keep)'))n.insertAdjacentHTML('afterbegin','<a class="keep" href="/dashboard.html">Dashboard</a>');
  n.insertAdjacentHTML('beforeend','<div class="keep um"><button type="button" class="uav" id="umb" aria-haspopup="true" aria-expanded="false" aria-label="Account menu">'+esc(initials(u.name))+'</button>'+
    '<div class="umenu hide" id="umm" role="menu"><div class="umh"><span class="uav big" aria-hidden="true">'+esc(initials(u.name))+'</span><div><b>'+esc(u.name)+'</b><small>'+esc(u.email)+'</small></div></div>'+
    MENU.map(m=>'<a role="menuitem" href="'+m[0]+'">'+m[1]+'</a>').join('')+'<hr><a role="menuitem" href="#" id="signout">Sign out</a></div></div>');
  const b=document.getElementById('umb'),m=document.getElementById('umm');
  const close=()=>{m.classList.add('hide');b.setAttribute('aria-expanded','false')};
  b.addEventListener('click',e=>{e.stopPropagation();const open=m.classList.contains('hide');m.classList.toggle('hide',!open);b.setAttribute('aria-expanded',open?'true':'false')});
  m.addEventListener('click',e=>{if(e.target.closest('a'))close()});
  document.addEventListener('click',e=>{if(!e.target.closest('.um'))close()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){close();b.focus()}});
  document.getElementById('signout').addEventListener('click',async e=>{e.preventDefault();try{await api('/api/auth/logout',{})}catch(_){}location.replace('/')})}
// ---- header: grouped dropdown menus on every page
(function(){const n=document.getElementById('nav');if(!n)return;
 const dd=(t,items)=>'<div class="dd"><button type="button" class="ddb" aria-expanded="false">'+t+'</button><div class="ddp">'+items.map(i=>'<a href="'+i[0]+'">'+i[1]+'<small>'+i[2]+'</small></a>').join('')+'</div></div>';
 n.innerHTML=dd('Product',[['/dashboard.html','Dashboard','Search and track your dividends'],['/coverage.html','Coverage','Which companies we have checked'],['/upgrade.html','Pricing','Free and paid plans']])+
  dd('Learn',[['/#how','How it works','The seven-year rule explained'],['/claim.html','How to claim','Step-by-step, free of charge'],['/#faq','Questions','Short answers']])+
  dd('Company',[['/about.html','About us','Who builds DhanKhoj'],['/contact.html','Contact &amp; support','Write to us'],['/stories.html','Customer stories','How others found their money'],['/feedback.html','Feedback','Tell us what to improve']])+'<a href="/upgrade.html">Pricing</a>';
 n.addEventListener('click',e=>{const b=e.target.closest('.ddb');document.querySelectorAll('.dd.open').forEach(d=>{if(!b||d!==b.parentElement)d.classList.remove('open')});if(b){const d=b.parentElement;d.classList.toggle('open');b.setAttribute('aria-expanded',d.classList.contains('open'))}});
 document.addEventListener('click',e=>{if(!e.target.closest('.dd'))document.querySelectorAll('.dd.open').forEach(d=>d.classList.remove('open'))});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.dd.open').forEach(d=>d.classList.remove('open'))});
 const sc=()=>document.body.classList.toggle('scrolled',scrollY>24);addEventListener('scroll',sc,{passive:true});sc()})();
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
