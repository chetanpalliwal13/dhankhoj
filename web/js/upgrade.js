const m=$('#msg');let PLAN=null,UPI=null,USER=null,period='yearly',sel=null,hl='';
const per=p=>p==='yearly'?'year':'month';
function done(t){$('#opts').classList.add('hide');$('#okbox').classList.remove('hide');$('#oktext').textContent=t}
function loadScript(src){return new Promise((ok,no)=>{if(window.Razorpay)return ok();const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=()=>no(new Error('Could not load the payment window. Check your connection or ad-blocker.'));document.head.appendChild(s)})}
const T=k=>PLAN.tiers.find(t=>t.key===k);
const priceOf=(t,p)=>p==='yearly'?t.yearly:t.monthly;
const HL=f=>esc(f).replace(/(Unlimited|\d+)/,'<b class="hv">$1</b>').replace(/(SMS \+ WhatsApp|WhatsApp|SMS)/,'<b class="hv">$1</b>');
function cards(){const cur=PLAN.current&&PLAN.current.active?PLAN.current.tier:null;const ci=cur?PLAN.tiers.findIndex(x=>x.key===cur):-1;const y=period==='yearly',on=(hl||(sel&&sel.key))||'';
 const free=`<div class="tier${on==='free'?' sel':''}${ci>=0?' low':''}" data-t="free" tabindex="0"><h3>Free</h3><div class="amt">${inr(0)}<small> / month</small></div><div class="sub">Start here. No card needed.</div>
  <div class="big"><b>${PLAN.free_companies}</b> companies in full</div><ul>${PLAN.free.features.map(f=>`<li>${HL(f)}</li>`).join('')}</ul>
  ${ci>=0?'<button type="button" class="choose" disabled>Included in your plan</button>':(USER?'<button type="button" class="choose" disabled>Your current plan</button>':'<a class="btn choose" href="/signup.html">Start free</a>')}</div>`;
 const paid=PLAN.tiers.map((t,i)=>{const isCur=cur===t.key,low=ci>=0&&i<ci,up=ci>=0&&i>ci;
  const big=t.companies===null?'<b>Unlimited</b> companies in full':'Up to <b>'+t.companies+'</b> companies in full';
  const btn=low?'<button type="button" class="choose" disabled>Included in your plan</button>':`<button type="button" class="choose" data-t="${t.key}">${isCur?'Extend ':(up?'Upgrade to ':'Choose ')}${esc(t.label)}</button>`;
  return `<div class="tier${t.popular?' pop':''}${on===t.key?' sel':''}${low?' low':''}" data-t="${t.key}" tabindex="0">${t.popular?'<div class="ribbon">Most popular</div>':''}${t.key==='platinum'&&!isCur?'<div class="ribbon">Maximum coverage</div>':''}${isCur?'<div class="ribbon cur">Your plan</div>':''}
  <h3>${esc(t.label)}</h3>
  <div class="amt">${inr(y?t.yearly_per_month:t.monthly)}<small> / month</small></div>
  <div class="sub">${y?`<s>${inr(t.monthly)}</s> billed ${inr(t.yearly)} a year <span class="save">save ${t.save_percent}%</span>`:`billed monthly - or <b>${inr(t.yearly)}</b> a year (save ${t.save_percent}%)`}</div>
  <div class="big">${big}</div>
  <ul>${t.features.map(f=>`<li>${HL(f)}</li>`).join('')}</ul>${btn}</div>`}).join('');
 const custom=`<div class="tier${on==='custom'?' sel':''}" data-t="custom" tabindex="0"><h3>Custom</h3><div class="amt">Let's talk</div><div class="sub">Built around what you need.</div><div class="big"><b>Your</b> numbers, your set-up</div><ul><li>More companies than <b class="hv">Platinum</b> covers</li><li>Family or team portfolios</li><li>Bulk checks for advisers and CAs</li></ul><a class="btn choose" href="/contact.html?topic=custom">Ask for a custom plan</a></div>`;
 $('#cards').innerHTML=free+paid+custom;
 $('#saveall').textContent='save up to '+Math.max(...PLAN.tiers.map(t=>t.save_percent))+'%';
 $('#pm').classList.toggle('on',period==='monthly');$('#py').classList.toggle('on',period==='yearly')}
function checkout(){if(!sel)return;const p=period,price=priceOf(sel,p);UPI=null;$('#upi').classList.add('hide');m.classList.add('hide');$('#okbox').classList.add('hide');
 $('#checkout').classList.remove('hide');$('#selname').textContent=sel.label+' membership';$('#selper').textContent='- '+(p==='yearly'?'1 year':'1 month')+', one-time payment';$('#price').textContent=inr(price);
 let note='';const c=PLAN.current;
 if(c&&c.active){const carry=(PLAN.carry||{})[sel.key]||0;
  note=c.tier===sel.key?`Your new period starts after your current ${c.label} plan ends on ${c.until}.`:(carry>0?`Your remaining ${c.days_left} days of ${c.label} are converted to ${carry} days of ${sel.label} and added to this purchase.`:'')}
 $('#selnote').textContent=note;
 if(!USER)return;
 if(!USER.email_verified){$('#opts').classList.add('hide');show(m,'err','Please confirm your email address first (check your inbox for the link), then come back here.');return}
 if(!PLAN.gateway&&!PLAN.upi){$('#opts').classList.add('hide');$('#none').classList.remove('hide');return}
 $('#opts').classList.remove('hide');$('#gw').classList.toggle('hide',!PLAN.gateway);$('#upibox').classList.toggle('hide',!PLAN.upi);
 $('#bpay').textContent=(PLAN.gateway==='mock'?'Pay (test mode) ':'Pay ')+inr(price);$('#checkout').scrollIntoView({behavior:'smooth'})}
(async()=>{USER=await session();PLAN=await api('/api/plan');$('#free').textContent=PLAN.free_companies;
 $('#freenote').textContent='Free plan: '+PLAN.free.features.join(' - ')+'.';
 if(PLAN.support_email)$('#sup').innerHTML='Write to <a href="mailto:'+esc(PLAN.support_email)+'">'+esc(PLAN.support_email)+'</a>.';
 const q=new URLSearchParams(location.search);if(q.get('period')==='monthly'||q.get('period')==='yearly')period=q.get('period');
 cards();const pre=T(q.get('plan'));if(pre){sel=pre;cards();if(USER){checkout();if(q.get('go')&&USER.email_verified&&PLAN.gateway)pay()}else openLogin()}})();
document.addEventListener('click',e=>{const b=e.target.closest('button.choose[data-t]'),s=e.target.closest('.seg button'),box=e.target.closest('.tier[data-t]');
 if(s){period=s.dataset.p;cards();if(sel)checkout();return}
 if(b&&!b.disabled){sel=T(b.dataset.t);hl=sel.key;go();return}
 if(box&&!e.target.closest('a,button')){hl=box.dataset.t;cards()}});
document.addEventListener('keydown',e=>{const box=e.target.closest&&e.target.closest('.tier[data-t]');if(box&&e.target===box&&(e.key==='Enter'||e.key===' ')){e.preventDefault();hl=box.dataset.t;cards();const f=document.querySelector('.tier.sel');if(f)f.focus()}});
async function pay(){const b=$('#bpay');b.disabled=true;m.classList.add('hide');
 try{const o=await api('/api/pay/order',{tier:sel.key,period});
  if(o.provider==='mock'){await api('/api/pay/mock-confirm',{payment_id:o.payment_id});return done('Test payment done - your '+sel.label+' plan is active.')}
  await loadScript('https://checkout.razorpay.com/v1/checkout.js');
  const rz=new Razorpay({key:o.key_id,amount:o.amount_paise,currency:o.currency,name:o.name,description:o.description,order_id:o.order_id,prefill:o.prefill,theme:{color:'#3446E0'},
   handler:async r=>{window.PAYING=false;try{await api('/api/pay/confirm',r);done('Payment received - your '+sel.label+' plan is active. A receipt was emailed to you.')}catch(err){show(m,'err',err.message+' If money was deducted, your plan activates automatically within a few minutes.')}},
   modal:{ondismiss:()=>{b.disabled=false;window.PAYING=false}}});
  rz.on('payment.failed',r=>{show(m,'err','Payment failed: '+((r.error&&r.error.description)||'please try again.'));b.disabled=false;window.PAYING=false});window.PAYING=true;rz.open()}
 catch(err){show(m,'err',err.message);b.disabled=false}}
$('#bpay').addEventListener('click',pay);
$('#bupi').addEventListener('click',async()=>{try{UPI=await api('/api/pay/upi/start',{tier:sel.key,period});$('#upi').classList.remove('hide');$('#uvpa').textContent=UPI.vpa;$('#upayee').textContent=UPI.payee;$('#uamt').textContent=inr(UPI.amount);$('#uref').textContent=UPI.ref;$('#ulink').href=UPI.link}catch(err){show(m,'err',err.message)}});
$('#butr').addEventListener('click',async()=>{try{await api('/api/pay/upi/submit',{payment_id:UPI.payment_id,utr:$('#utr').value});done('Thank you - we received your reference and will activate your '+sel.label+' plan after matching it with our bank statement (usually a few working hours). You will get an email.')}catch(err){show(m,'err',err.message)}});

// ---- sign-in pop-up: pricing stays public, sign-in is asked only when a plan is chosen
function gnext(){return '/upgrade.html?plan='+(sel?sel.key:'')+'&period='+period+'&go=1'}
// sign in (or create an account) in a popup, then go straight on to payment
function openLogin(mode){openAuth(mode||'signin',{next:gnext(),note:sel?sel.label+' membership - '+(period==='yearly'?'yearly':'monthly')+', '+inr(priceOf(sel,period)):'',
 onSuccess:async user=>{ME.user=user;ME.loaded=true;USER=user;PLAN=await api('/api/plan');buildNav();cards();checkout();if(USER.email_verified&&PLAN.gateway)pay()}})}

// plan clicked: look at the live session first (it may have changed in another tab), then sign in or go straight to payment
async function go(){ME.loaded=false;USER=await session();cards();if(!USER){openLogin();return}
 PLAN=await api('/api/plan');buildNav();
 checkout();if(USER.email_verified&&PLAN.gateway)pay()}
