const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr=n=>{n=Number(n||0);return '₹'+n.toLocaleString('en-IN',n>=10000?{maximumFractionDigits:0}:{minimumFractionDigits:n%1?2:0,maximumFractionDigits:2})};
async function api(path,body){
  const o=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
  if(window.demoApi)return window.demoApi(path,body);
  let r;try{r=await fetch(path,o)}catch(e){throw new Error('Network problem. Please try again.')}
  if(!(r.headers.get('content-type')||'').includes('json')){  // no DhanKhoj server behind this address (plain static hosting): switch to the sample-data preview
    if(!window.DEMO_P)window.DEMO_P=new Promise((res,rej)=>{const s=document.createElement('script');s.src='/js/demo.js';s.onload=res;s.onerror=rej;document.head.appendChild(s)});
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
const MENU=[['/dashboard.html','Dashboard'],['/account.html#profile','Profile'],['/account.html#identity','PAN &amp; demat IDs'],['/account.html#alerts','Alerts'],['/account.html#plan','Plan &amp; payments'],['/account.html#security','Security']];
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
  if((location.pathname==='/'||location.pathname==='/index.html')&&!/[?&]home=1/.test(location.search)&&!(document.referrer&&new URL(document.referrer).origin===location.origin)){location.replace('/dashboard.html');return}
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
