/* Preview mode. Loaded only when the page is hosted without the DhanKhoj server (for example plain static hosting).
   It answers the site's API calls in the browser with SAMPLE data so every page can be tried. Nothing is sent or saved on a server. */
(function(){
const PLAN={"ok": true, "tiers": [{"key": "silver", "label": "Silver", "companies": 25, "sms": true, "whatsapp": false, "monthly": 49.0, "yearly": 470.0, "yearly_per_month": 39.17, "save_percent": 20, "save_inr": 118, "features": ["Up to 25 companies shown in full", "Email + SMS alerts", "Up to 5 demat / folio IDs plus PAN matching", "Deadline reminders before IEPF transfer", "GST receipts for every payment"], "popular": false}, {"key": "gold", "label": "Gold", "companies": 100, "sms": true, "whatsapp": true, "monthly": 99.0, "yearly": 950.0, "yearly_per_month": 79.17, "save_percent": 20, "save_inr": 238, "features": ["Up to 100 companies shown in full", "Email + SMS + WhatsApp alerts", "Up to 5 demat / folio IDs plus PAN matching", "Deadline reminders before IEPF transfer", "GST receipts for every payment"], "popular": true}, {"key": "platinum", "label": "Platinum", "companies": null, "sms": true, "whatsapp": true, "monthly": 199.0, "yearly": 1910.0, "yearly_per_month": 159.17, "save_percent": 20, "save_inr": 478, "features": ["Every matched company, no limit companies shown in full", "Email + SMS + WhatsApp alerts", "Up to 5 demat / folio IDs plus PAN matching", "Deadline reminders before IEPF transfer", "GST receipts for every payment"], "popular": false}], "free": {"key": "free", "label": "Free", "companies": 5, "sms": false, "whatsapp": false, "features": ["5 companies shown in full", "Email alerts", "Up to 5 demat / folio IDs plus PAN matching"]}, "periods": {"monthly": 30, "yearly": 365}, "yearly_discount": 20.0, "gst_percent": 18.0, "free_companies": 5, "max_dp_ids": 5, "gateway": "mock", "upi": false, "upi_vpa": null, "upi_payee": "DhanKhoj", "support_email": "", "current": {"tier": "free", "label": "Free", "active": false, "until": null, "days_left": 0}, "carry": {}};
const OPTS={"states": ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"], "langs": ["English", "Hindi", "Marathi", "Gujarati", "Bengali", "Tamil", "Telugu", "Kannada", "Malayalam", "Punjabi", "Odia", "Other"]};
const FREE={active:false,tier:'free',label:'Free',until:null,expired_on:null,companies:5,sms:false,whatsapp:false,free_companies:5};
const KEY='dk_preview';
const CO=['Sample Steel Works Ltd','Demo Power Finance Ltd','Example Textiles Ltd','Test Pharma Industries Ltd','Mock Foods Ltd'];
const ST=()=>{try{return JSON.parse(localStorage.getItem(KEY))||{}}catch(e){return{}}};
const SAVE=s=>{try{localStorage.setItem(KEY,JSON.stringify(s))}catch(e){}};
const pick=a=>a[Math.floor(Math.random()*a.length)],ri=(a,b)=>a+Math.floor(Math.random()*(b-a+1));
const mkMail=e=>{const[a,b]=e.split('@');return a[0]+'***@'+b};
const mask=f=>'*'.repeat(Math.max(f.length-4,0))+f.slice(-4);
function err(msg,need,status){const e=new Error(msg);e.need=need;e.status=status||400;return e}
function nameFrom(email){const base=email.split('@')[0].replace(/[0-9]+$/,'').replace(/[._-]+/g,' ').trim();if(/^chetanpalliwal/i.test(email))return['Chetan','Palliwal'];const p=base.split(' ');const cap=s=>s?s[0].toUpperCase()+s.slice(1):'';return[cap(p[0])||'Demo',cap(p[1])||'User']}
function newUser(email,first,last,mobile){return{email,first_name:first,middle_name:'',last_name:last,mobile:mobile||'9876543211',pan:/^chetanpalliwal/i.test(email)?'ABCPP1234F':'',folios:[],aliases:[],address:'',city:'',state:'',pincode:'400001',dob:'',father_name:'',alt_mobile:'',lang:'',channels:{email:true,sms:false,whatsapp:false},since:new Date().toISOString(),seen:Date.now()}}
function user(){const s=ST();return s.user||null}
function need(){const u=user();if(!u)throw err('Please sign in to continue.','login',401);return u}
const fullName=u=>[u.first_name,u.middle_name,u.last_name].filter(Boolean).join(' ');
function sessionInfo(u){return{first_name:u.first_name,name:fullName(u),email:mkMail(u.email),email_verified:true,phone_verified:false,plan:FREE,idle_min:5}}
function profile(u){return{first_name:u.first_name,middle_name:u.middle_name,last_name:u.last_name,email:u.email,mobile:u.mobile,pan_set:!!u.pan,pan_masked:u.pan?'XXXXXX'+u.pan.slice(-4):'',pan_ok:true,dob:u.dob,father_name:u.father_name,address:u.address,city:u.city,state:u.state,pincode:u.pincode,alt_mobile:u.alt_mobile,lang:u.lang,folios:u.folios,max_dp:5,plan:FREE,aliases:u.aliases,email_verified:true,phone_verified:false,channels:u.channels,member_since:u.since,states:OPTS.states,langs:OPTS.langs}}
function rows(u,modes){const n=ri(6,10),out=[],nm=(u.first_name+' '+u.last_name).toUpperCase(),cos=[...CO].sort(()=>Math.random()-.5).slice(0,ri(2,5)),streets=['MG ROAD','STATION ROAD','GANDHI NAGAR','LAKE VIEW COLONY','SUNRISE APARTMENTS','MARKET YARD'],cities=['MUMBAI','PUNE','DELHI','BENGALURU','CHENNAI','JAIPUR'];
  const labels={pan:['PAN','high'],ids:['DP-Client ID','high'],name:['Name + PIN','medium'],address:['Address','low']};
  const pool=(modes&&modes.length?modes:['pan','ids','name']).filter(m=>labels[m]);
  const co={};cos.forEach(c=>{const yr=ri(2019,2026),dec=new Date(Date.now()-ri(200,365*6+120)*864e5),due=new Date(dec.getTime()+(37+365*7+2)*864e5);co[c]={fy:yr+'-'+String((yr+1)%100).padStart(2,'0'),dtype:pick(['Final','Interim']),dec:dec.toISOString().slice(0,10),due:due.toISOString().slice(0,10),days:Math.round((due-Date.now())/864e5)}});
  for(let i=0;i<n;i++){const c=pick(cos),m=pick(pool),[via,conf]=labels[m],strong=conf==='high',hold=pick([10,25,40,55,80,120,160,250,400,1000]),folio=pick(['IN30','1201','1202','IN301'])+Array.from({length:12},()=>ri(0,9)).join(''),addr=ri(1,250)+' '+pick(streets)+' '+pick(cities);
    const nm2=strong||m==='name'?nm:pick([u.first_name.toUpperCase()+' '+pick('ABKMRS')+' '+u.last_name.toUpperCase(),u.first_name[0].toUpperCase()+'. '+u.last_name.toUpperCase()]);
    out.push({id:i+1,company:c,fy:co[c].fy,dtype:co[c].dtype,folio:mask(folio),holding:hold,amount:Math.round(hold*pick([1.5,2.5,4.25,6.8,9,12.5,21])*100)/100,confidence:conf,deadline_est:co[c].due,days_left:co[c].days,source_url:'',declared_on:co[c].dec,
      holder:strong?nm2:nm2.split(' ').map(w=>w[0]+'*'.repeat(w.length-1)).join(' '),address:strong?addr:'',pincode:u.pincode||'400001',via:[via]})}
  return out}
function dash(u,modes){const all=rows(u,modes),likely=all.filter(r=>r.confidence!=='low'),possible=all.filter(r=>r.confidence==='low').map(r=>({...r,amount:null}));
  return{sample:true,profile:{name:fullName(u),first_name:u.first_name,email:mkMail(u.email),phone:'+91*****'+String(u.mobile).slice(-2),since:u.since,pan_masked:u.pan?'XXXXXX'+u.pan.slice(-4):null,ids:u.folios.map(mask),has_address:!!((u.address||u.city)&&u.pincode)},
   plan:{...FREE,used:new Set(likely.map(r=>r.company)).size},needs_pan:!u.pan,dp_count:u.folios.length,likely,possible,total_likely:Math.round(likely.reduce((a,r)=>a+(r.amount||0),0)*100)/100,locked:{companies:0,entries:0,likely_entries:0,amount_band:null},claims:[]}}
const NA=m=>{throw err(m||'This is a preview with sample data, so this action is not available here.')};
const H={
 'GET /api/session':()=>({user:user()?sessionInfo(user()):null}),
 'GET /api/auth/options':()=>({google:false}),
 'GET /api/plan':()=>PLAN,
 'GET /api/stats':()=>({companies_covered:3,records:3606,amount:3592258.5,last_ingest_at:new Date().toISOString(),subscribers:2}),
 'GET /api/form-options':()=>({states:OPTS.states,langs:OPTS.langs}),
 'GET /api/claim-info':()=>({fee_text:'The expert sends you a written fee quote before any work starts. You can decline at no cost.',experts:[]}),
 'GET /api/coverage':()=>({companies_total:5,companies_covered:5,companies:CO.map((c,i)=>({id:i+1,name:c,nse_symbol:'',bse_code:'',isin:'',cin:'',last_list:new Date().toISOString().slice(0,19),lists:1,validation:'unverified',state:'covered'})),official:[{name:'IEPF - search your shares',url:'https://www.iepf.gov.in/IEPFWebSite/IEPF/home.html'},{name:'MCA - investor services',url:'https://www.mca.gov.in/content/mca/global/en/home.html'},{name:'RBI UDGAM - bank deposits',url:'https://udgam.rbi.org.in/'}],note:'Preview with sample companies.'}),
 'POST /api/check':b=>{const nm=String(b.name||'').trim();if(nm.split(/\s+/).length<2)throw err('Enter at least your first and last name (initials are fine).');const rs=rows({first_name:nm.split(/\s+/)[0],last_name:nm.split(/\s+/).pop(),pincode:b.pincode||'400001'},['name']).slice(0,5).map(r=>({company:r.company,fy:r.fy,dtype:r.dtype,name:nm.split(/\s+/).map(w=>w[0]+'*'.repeat(w.length-1)).join(' '),folio:r.folio,amount_band:'Rs 1,000 - Rs 5,000',confidence:r.confidence,deadline_est:r.deadline_est,days_left:r.days_left}));return{likely:rs.length,possible:0,results:rs,more:0,total_band:'Rs 5,000 - Rs 10,000',note:'Preview with sample data.'}},
 'POST /api/auth/login':b=>{const e=String(b.email||'').trim().toLowerCase();if(!e.includes('@')||!b.password)throw err('Enter your email and password.',undefined,401);const s=ST();let u=s.accounts&&s.accounts[e];if(!u){const[f,l]=nameFrom(e);u=newUser(e,f,l)}SAVE({...s,user:u,accounts:{...(s.accounts||{}),[e]:u}});return{user:sessionInfo(u)}},
 'POST /api/auth/signup':b=>{const e=String(b.email||'').trim().toLowerCase();if(!e.includes('@'))throw err('Enter a valid email address.');const u=newUser(e,b.first_name||'Demo',b.last_name||'User',String(b.mobile||'').replace(/\D/g,'').slice(-10));const s=ST();SAVE({...s,user:u,accounts:{...(s.accounts||{}),[e]:u}});return{email:mkMail(e),verified:true}},
 'POST /api/auth/logout':()=>{const s=ST();if(s.user&&s.accounts)s.accounts[s.user.email]=s.user;delete s.user;SAVE(s);return{}},
 'POST /api/session/ping':()=>{need();return{}},
 'GET /api/dashboard':()=>dash(need()),
 'POST /api/me/search':b=>{const u=need(),m=(b.modes||[]).filter(x=>['pan','ids','name','address'].includes(x));if(!m.length)throw err('Tick at least one thing to search with.');
   if(m.includes('pan')&&!u.pan)throw err('Add your PAN in your profile first, or untick PAN.');if(m.includes('ids')&&!u.folios.length)throw err('Add your DP-Client ID or folio number in your profile first, or untick it.');
   if(m.includes('address')&&!((u.address||u.city)&&u.pincode))throw err('Address search needs your address and PIN code in your profile. Add them or untick Address.');
   const d=dash(u,m);d.searched=m.sort();d.found=d.likely.length+d.possible.length;return d},
 'GET /api/account/profile':()=>profile(need()),
 'POST /api/account/profile':b=>{const u=need();
   if(b.pan!==undefined&&String(b.pan).trim()){const p=String(b.pan).replace(/\s/g,'').toUpperCase();if(u.pan&&u.pan!==p)throw err('Your PAN is already saved and cannot be changed here.',undefined,403);if(!/^[A-Z]{3}[ABCFGHJKLPT][A-Z][0-9]{4}[A-Z]$/.test(p))throw err('Enter a valid PAN. The 4th letter must be one of A, B, C, F, G, H, J, K, L, P or T.');u.pan=p}
   if(b.folios!==undefined){const f=[...new Set((b.folios||[]).map(x=>String(x).toUpperCase().replace(/[^A-Z0-9]/g,'')).filter(Boolean))];f.forEach(x=>{if(x.length<4||x.length>24)throw err('"'+x+'" does not look like a DP-Client ID or folio number (4-24 letters and digits).')});if(f.length>5)throw err('You can save up to 5 DP-Client IDs / folio numbers.');
     if(u.folios.length&&JSON.stringify(f)!==JSON.stringify(u.folios))throw err('Your DP-Client IDs / folio numbers are already saved and cannot be changed here.',undefined,403);if(!u.folios.length)u.folios=f}
   for(const k of ['first_name','middle_name','last_name','dob','father_name','address','city','state','pincode','lang'])if(b[k]!==undefined)u[k]=String(b[k]);if(b.mobile!==undefined)u.mobile=String(b.mobile).replace(/\D/g,'').slice(-10);if(b.alt_mobile!==undefined)u.alt_mobile=String(b.alt_mobile).replace(/\D/g,'').slice(-10);
   if(b.aliases!==undefined)u.aliases=b.aliases.slice(0,3);const s=ST();SAVE({...s,user:u,accounts:{...(s.accounts||{}),[u.email]:u}});return profile(u)},
 'POST /api/account/channels':b=>{const u=need();if((b.channels.sms||b.channels.whatsapp))throw err('SMS and WhatsApp need a verified mobile number and a paid plan. Not available in the preview.');u.channels={email:!!b.channels.email,sms:false,whatsapp:false};const s=ST();SAVE({...s,user:u});return{channels:u.channels}},
 'GET /api/account/payments':()=>{need();return{payments:[]}},
 'POST /api/account/password':()=>{need();return{}},
 'POST /api/account/delete':()=>{SAVE({});return{}},
};
window.demoApi=async function(path,body){const method=body===undefined?'GET':'POST',p=path.split('?')[0],f=H[method+' '+p];
  if(!f){if(p.startsWith('/api/pay')||p.startsWith('/api/me/claim')||p.startsWith('/api/expert')||p.startsWith('/api/account/phone'))NA();throw err('Not available in the preview.')}
  await new Promise(r=>setTimeout(r,150));return{ok:true,...f(body||{})}};
function banner(){if(document.getElementById('prevbar'))return;const d=document.createElement('div');d.id='prevbar';d.setAttribute('role','status');d.innerHTML='<b>Preview with sample data.</b> Nothing here is real, saved on a server, or sent. Sign in with any email and password. The full app runs on our server.';document.body.insertBefore(d,document.body.firstChild)}
if(document.body)banner();else document.addEventListener('DOMContentLoaded',banner);
})();
