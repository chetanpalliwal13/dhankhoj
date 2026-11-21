const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr=n=>{n=Number(n||0);return '₹'+n.toLocaleString('en-IN',n>=10000?{maximumFractionDigits:0}:{minimumFractionDigits:n%1?2:0,maximumFractionDigits:2})};
async function api(path,body){
  const o=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
  let r;try{r=await fetch(path,o)}catch(e){throw new Error('Network problem. Please try again.')}
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
async function buildNav(){const n=document.getElementById('nav');if(!n)return;const u=await session();
  n.querySelectorAll('.keep').forEach(a=>a.remove());
  n.insertAdjacentHTML('beforeend',u?'<a class="keep" href="/dashboard.html">Dashboard</a><a class="keep" href="/account.html">Account</a><a class="keep" href="#" id="signout">Sign out</a>':'<a class="keep" href="/signin.html">Sign in</a><a class="keep" href="/signup.html">Sign up free</a>');
  const so=document.getElementById('signout');if(so)so.addEventListener('click',async e=>{e.preventDefault();try{await api('/api/auth/logout',{})}catch(_){}location.href='/'})}
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
