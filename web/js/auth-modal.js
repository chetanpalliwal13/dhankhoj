/* Sign in / Sign up popup: opens on any page, so nobody has to leave what they are doing. */
(function(){
const G='<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';
const ic=p=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+'</svg>';
const MAIL=ic('<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m3.5 7 8.5 6 8.5-6"/>'),LOCK=ic('<rect x="5" y="11" width="14" height="9.5" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),USER=ic('<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>'),PHONE=ic('<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>');
const fld=(id,label,icon,attrs)=>'<label for="'+id+'">'+label+'</label><div class="fld">'+icon+'<input id="'+id+'" '+attrs+'></div>';
const HTML='<div class="amb" role="document"><button type="button" class="amx" id="amx" aria-label="Close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>'+
 '<div class="amlogo"><img src="/favicon.svg" width="34" height="34" alt=""><b>DhanKhoj</b></div>'+
 '<div id="amview"><h2 id="amt"></h2><p class="amsub" id="amsub"></p><div id="amnote" class="amnote hide"></div>'+
 '<div class="amtabs" role="tablist"><button type="button" role="tab" data-m="signin">Sign In</button><button type="button" role="tab" data-m="signup">Sign Up</button></div>'+
 '<button type="button" class="amg" id="amg">'+G+'<span id="amgt"></span></button><div class="amor"><span>Or continue with email</span></div><div id="amm" class="msg hide" role="alert"></div>'+
 '<form id="amfi" novalidate>'+fld('am-em','Email',MAIL,'type="email" placeholder="you@example.com" autocomplete="email" maxlength="254"')+fld('am-pw','Password',LOCK,'type="password" placeholder="Your password" autocomplete="current-password"')+
   '<div class="amrow"><a href="/forgot.html">Forgot password?</a></div><button class="amgo" id="amgoi">Sign in</button><p class="amalt">New to DhanKhoj? <button type="button" class="amlink" data-m="signup">Create a free account</button></p></form>'+
 '<form id="amfu" class="hide" novalidate><div class="amgrid"><div>'+fld('am-fn','First name',USER,'type="text" placeholder="First name" autocomplete="given-name" maxlength="40"')+'</div><div>'+fld('am-ln','Last name',USER,'type="text" placeholder="Last name" autocomplete="family-name" maxlength="40"')+'</div></div>'+
   '<p class="amhint">Exactly as on your share certificate or demat account. We match this against company lists.</p>'+
   fld('am-mo','Mobile number',PHONE,'type="tel" inputmode="numeric" placeholder="98XXXXXXXX" autocomplete="tel-national" maxlength="14"')+fld('am-se','Email',MAIL,'type="email" placeholder="you@example.com" autocomplete="email" maxlength="254"')+
   '<div class="amgrid"><div>'+fld('am-sp','Password',LOCK,'type="password" placeholder="8+ characters" autocomplete="new-password"')+'</div><div>'+fld('am-sc','Confirm password',LOCK,'type="password" placeholder="Type again" autocomplete="new-password"')+'</div></div>'+
   '<label class="amchk"><input id="am-co" type="checkbox"><span>I am 18 or older and I accept the <a href="/terms.html" target="_blank" rel="noopener">Terms</a> and the <a href="/privacy.html" target="_blank" rel="noopener">Privacy Notice</a>.</span></label>'+
   '<button class="amgo" id="amgou">Create account</button><p class="amalt">Already have an account? <button type="button" class="amlink" data-m="signin">Sign in</button></p></form></div>'+
 '<div id="amdone" class="hide"><div class="amok">'+ic('<path d="m5 12.5 4.5 4.5L19 7.5"/>')+'</div><h2>Check your email</h2><p class="amsub">We sent a confirmation link to <b id="amde"></b>. Click it to activate your account, then sign in.</p><div id="amdm" class="msg hide"></div><div id="amdev" class="msg hide"></div>'+
   '<p class="amalt">Nothing arrived? Check spam, or <button type="button" class="amlink" id="amres">send it again</button></p><button type="button" class="amgo" data-m="signin">Back to sign in</button></div></div>';
let el=null,S={mode:'signin',opts:{},email:'',last:null};
const q=s=>el.querySelector(s);
function build(){el=document.createElement('div');el.className='am hide';el.id='am';el.setAttribute('role','dialog');el.setAttribute('aria-modal','true');el.setAttribute('aria-labelledby','amt');el.innerHTML=HTML;document.body.appendChild(el);
 el.addEventListener('mousedown',e=>{if(e.target===el)close()});
 q('#amx').addEventListener('click',close);
 el.addEventListener('click',e=>{const m=e.target.closest('[data-m]');if(m&&el.contains(m)){e.preventDefault();setMode(m.dataset.m)}});
 el.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();close();return}
  if(e.key==='Tab'){const f=[...el.querySelectorAll('button,a[href],input,select')].filter(x=>!x.disabled&&x.offsetParent!==null);if(!f.length)return;const a=f[0],z=f[f.length-1];if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus()}else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus()}}});
 q('#amg').addEventListener('click',async()=>{const m=q('#amm');m.classList.add('hide');
  if(await googleOn())location.href=googleHref(S.opts.next||safeNext());else show(m,'err',GERR.off)});
 q('#amfi').addEventListener('submit',signin);q('#amfu').addEventListener('submit',signup);q('#amres').addEventListener('click',resend)}
function setMode(m){S.mode=m;const up=m==='signup',done=m==='done';
 q('#amview').classList.toggle('hide',done);q('#amdone').classList.toggle('hide',!done);if(done)return q('#amdone .amgo').focus();
 q('#amfi').classList.toggle('hide',up);q('#amfu').classList.toggle('hide',!up);q('#amm').classList.add('hide');
 q('#amt').textContent=up?'Create your free account':'Welcome back';
 q('#amsub').textContent=up?'Free plan: 1 company, latest year. Upgrade any time. No card needed.':'Sign in to see your unclaimed dividends.';
 q('#amgt').textContent=up?'Sign up with Google':'Sign in with Google';
 el.querySelectorAll('.amtabs button').forEach(b=>{const on=b.dataset.m===m;b.classList.toggle('on',on);b.setAttribute('aria-selected',on?'true':'false')});
 const first=up?'#am-fn':'#am-em';setTimeout(()=>{const f=q(first);if(f)f.focus()},30)}
function close(){if(!el||el.classList.contains('hide'))return;el.classList.add('hide');document.body.classList.remove('amopen');const o=S.opts;if(S.last&&S.last.focus)S.last.focus();if(o.onClose)o.onClose()}
async function signin(e){e.preventDefault();const m=q('#amm'),b=q('#amgoi');m.classList.add('hide');
 if(!q('#am-em').value.trim()||!q('#am-pw').value)return show(m,'err','Enter your email and password.');
 b.disabled=true;
 try{const r=await api('/api/auth/login',{email:q('#am-em').value,password:q('#am-pw').value});q('#am-pw').value='';
  const o=S.opts;if(typeof o.onSuccess==='function'){S.opts={};el.classList.add('hide');document.body.classList.remove('amopen');o.onSuccess(r.user)}else location.href=o.next||safeNext()}
 catch(err){show(m,'err',err.message)}b.disabled=false}
async function signup(e){e.preventDefault();const m=q('#amm'),b=q('#amgou');m.classList.add('hide');
 if(q('#am-sp').value!==q('#am-sc').value)return show(m,'err','The two passwords do not match.');
 if(!q('#am-co').checked)return show(m,'err','Please confirm you are 18+ and accept the Terms and Privacy Notice.');
 b.disabled=true;
 try{S.email=q('#am-se').value.trim();
  const r=await api('/api/auth/signup',{first_name:q('#am-fn').value,last_name:q('#am-ln').value,mobile:q('#am-mo').value,email:S.email,password:q('#am-sp').value,consent:true});
  q('#amde').textContent=r.email;if(r.dev_link)show(q('#amdev'),'ok','DEV MODE - confirmation link: '+r.dev_link);setMode('done')}
 catch(err){show(m,'err',err.message)}b.disabled=false}
async function resend(){const m=q('#amdm');try{const r=await api('/api/auth/resend-verification',{email:S.email});show(m,'ok','If that address still needs confirming, a new link is on its way.');if(r.dev_link)show(q('#amdev'),'ok','DEV MODE - confirmation link: '+r.dev_link)}catch(err){show(m,'err',err.message)}}
window._openAuth=function(mode,opts){if(!el)build();S.opts=opts||{};S.last=document.activeElement;
 const n=q('#amnote');if(S.opts.note){n.textContent=S.opts.note;n.classList.remove('hide')}else n.classList.add('hide');
 el.classList.remove('hide');document.body.classList.add('amopen');setMode(mode==='signup'?'signup':'signin');
 if(S.opts.message)show(q('#amm'),S.opts.message.type,S.opts.message.text)};
})();
