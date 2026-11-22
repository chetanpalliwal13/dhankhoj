/* DhanKhoj assistant (preview). It reads your question with simple rules and answers from the sample data.
   It is not a live AI model yet. To upgrade: send the question to a server endpoint that calls a language model with tool access to the same DX.query(). */
(function(){
const E=window.DX,F=window.dxFmt,esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let rows=[],panel,log,inp,last=null,opener=null;
const SEC=[[/bank/,'Banking'],[/\b(it|tech|software|infotech|digital)\b/,'IT'],[/pharma|drug|medicine/,'Pharma'],[/fmcg|consumer|food/,'FMCG'],[/\bauto|motor|tyre/,'Auto'],[/cement|building/,'Cement'],[/power|utilit|hydro|thermal/,'Power'],[/\benergy|oil|gas|refin/,'Energy'],[/metal|steel|mining|coal|zinc/,'Metals & Mining'],[/financ|nbfc|insur|housing/,'Finance'],[/chemical|fertili[sz]er|paint/,'Chemicals'],[/industrial|engineering|logistic|rail|infra/,'Industrials']];
const SUG=['Top 5 large cap dividend stocks','Best total return in 5 years','Most consistent dividend payers','High yield with safe payout','What is unclaimed dividend?','Next ex-dividend dates'];
function parse(t){const o={},w=t.toLowerCase();
 let mm=w.match(/(\d+)\s*(?:m|mo|mos|month|months)\b/);if(mm){const n=+mm[1];o.period=n>=12?'1y':[1,3,6].reduce((a,b)=>Math.abs(b-n)<Math.abs(a-n)?b:a)+'m'}else if(/last month|past month|this month/.test(w))o.period='1m';else if(/quarter(?!ly)/.test(w))o.period='3m';
 let m=w.match(/(?:last|past|over|in|for|of)\s*(?:the\s*)?(\d+)\s*(?:y|yr|yrs|year|years)\b(?!\s*(?:of|in a row|straight|consecutive|consistent))/)||w.match(/\b(\d+)\s*(?:y|yr)\b/);
 if(m&&!o.period){const n=+m[1];o.period=[1,3,5,10].reduce((a,b)=>Math.abs(b-n)<Math.abs(a-n)?b:a)}else if(!o.period&&/last year|past year|this year|1 year/.test(w))o.period=1;
 m=w.match(/(\d+)\s*(?:\+\s*)?(?:years?|yrs?)\s*(?:of|in a row|straight|consecutive|without)/);if(m)o.years=+m[1];
 else if(/consistent|regular|streak|every year|in a row/.test(w)&&!o.years)o.flagCons=1;
 m=w.match(/top\s*(\d+)|(\d+)\s*(?:best|top)|best\s*(\d+)|first\s*(\d+)|\b(\d+)\s*(?:stocks|companies|shares)/);if(m){o.n=Math.min(20,+(m[1]||m[2]||m[3]||m[4]||m[5]))}
 if(/large\s*-?\s*cap|\blarge\b|big compan/.test(w))o.cap='Large';else if(/mid\s*-?\s*cap|\bmid\b/.test(w))o.cap='Mid';else if(/small\s*-?\s*cap|\bsmall\b/.test(w))o.cap='Small';
 for(const s of SEC)if(s[0].test(w)){o.sector=s[1];break}
 m=w.match(/(?:yield|dividend|return)[^\d]{0,20}(?:above|over|more than|at least|>=?|minimum|min)\s*(\d+(?:\.\d+)?)|(?:above|over|more than|at least|>=?)\s*(\d+(?:\.\d+)?)\s*%/);if(m)o.min=+(m[1]||m[2]);
 if(/quarterly/.test(w))o.freq='Quarterly';else if(/half[- ]?yearly|semi/.test(w))o.freq='Half-yearly';else if(/\bannual\b|yearly payer/.test(w))o.freq='Annual';
 if(/ex[- ]?(?:dividend )?date|upcoming|next dividend|record date|soon/.test(w))o.metric='ex';
 else if(/total return|best return|returns?\b.*(?:stock|share)|gave.*return|price \+/.test(w)&&!/dividend return/.test(w))o.metric='totalret';
 else if(/price (?:return|gain|growth)|share price|capital gain/.test(w))o.metric='priceret';
 else if(/dividend return|dividends? (?:received|earned|paid)|highest dividend|most dividend|payout in/.test(w)&&o.period)o.metric='divret';
 else if(/number of (?:dividend|payout)|most payouts|payouts|how often|frequent/.test(w))o.metric='pays';
 else if(/consistent|streak|in a row|regular|longest|every year/.test(w))o.metric='years';
 else if(/growth|growing|grow/.test(w))o.metric='growth';
 else if(/market cap|biggest|largest/.test(w))o.metric='mcap';
 else if(/safe|low payout|sustainable|payout ratio/.test(w)){o.metric='yield';o.maxPayout=50;if(!o.min)o.min=1.5}
 else if(/yield|highest dividend|best dividend|high dividend|dividend stocks?|dividend payers?/.test(w))o.metric='yield';
 if(o.metric==='divret'&&!o.period)o.period=5;
 if(o.flagCons&&!o.metric){o.metric='years'}
 if((o.metric==='totalret'||o.metric==='priceret')&&!o.period)o.period=5;
 delete o.flagCons;return o}
function find(t){const w=t.toLowerCase();return rows.filter(r=>new RegExp('\\b'+r.sym.toLowerCase()+'\\b').test(w)||w.indexOf(r.name.toLowerCase())>=0).slice(0,2)}
function describe(o){const p=[];if(o.cap)p.push(o.cap.toLowerCase()+'-cap');if(o.sector)p.push(o.sector);if(o.freq)p.push(o.freq.toLowerCase()+' payers');if(o.min)p.push('yield '+o.min+'% or more');if(o.years)p.push(o.years+'+ years paid in a row');if(o.maxPayout)p.push('payout '+o.maxPayout+'% or less');return p.join(', ')}
function listHTML(res){return '<ol class="dka-l">'+res.items.map(x=>'<li><a href="/stock.html?sym='+x.r.sym+'"><b>'+esc(x.r.name)+'</b><small>'+x.r.sym+' · '+esc(x.r.sector)+' · yield '+F.pc(x.r.yield)+'</small></a><em>'+res.m.fmt(x.v)+'</em></li>').join('')+'</ol>'}
function answer(t){const w=t.toLowerCase().trim();
 if(/^(hi|hello|hey|namaste|help|what can you do)\b/.test(w))return{h:'Hello. I can rank dividend stocks from the sample data and explain unclaimed dividends. Try one of these.',chips:1};
 if(/unclaimed|iepf|forgot|forgotten|lost dividend|unpaid|claim|seven[- ]year|7[- ]year/.test(w)&&!find(t).length)return{h:'<b>Unclaimed dividends</b> are dividends a company declared but you never received, often because the bank details changed or the shares were held by an old folio. After <b>seven years</b> unpaid, companies must move the money and the shares to the IEPF, a government fund. You can still claim it back, free of charge.<br><br>DhanKhoj matches your name, PAN and folio or demat IDs against the companies\' published lists and alerts you. <a href="/claim.html">How to claim</a> · <a href="/signup.html">Create a free account</a> · <a href="/#dx">See the home page</a>'};
 if(/price|plan|cost|subscription|silver|gold|platinum|pay\b/.test(w)&&!/stock|share price/.test(w))return{h:'DhanKhoj has a free plan and paid plans (Silver, Gold, Platinum) plus a custom plan. <a href="/upgrade.html">See pricing</a>.'};
 if(/tradingview|live price|real[- ]time|today.s price/.test(w))return{h:'Charts and prices here are sample data for now. Live market data will be added when the real backend is connected.'};
 const f=find(t);
 if(f.length&&!/top|best|rank|list/.test(w)){const r=f[0];const a=r.ret[5];return{h:'<b>'+esc(r.name)+'</b> ('+r.sym+', '+esc(r.sector)+', '+r.cap.toLowerCase()+'-cap) pays about <b>'+F.rs(r.dps)+'</b> a share, a yield of <b>'+F.pc(r.yield)+'</b>. It has paid <b>'+r.years+' years in a row</b>, '+r.freq.toLowerCase()+', with a payout ratio of '+r.payout+'%.'+(a&&r.years>=5?' Over 5 years the total return was '+F.pct(a.total,0)+' (price '+F.pct(a.price,0)+', dividends '+F.pc(a.div,1)+').':'')+'<br><a href="/stock.html?sym='+r.sym+'">Open chart and dividend history</a>'}}
 let o=parse(t);const has=Object.keys(o).length;
 if(!has&&last&&/^(only|make|show|and|now|what about|how about|same|but|just)\b/.test(w))return null;
 if(!o.metric){if(has){o.metric=last&&!/yield|dividend/.test(w)?last.metric:'yield'}else return{h:'I did not catch that. I can rank stocks by yield, consistency, payouts, growth, market cap, total return or upcoming ex-dates, and filter by size, sector, minimum yield and years paid. Try one of these.',chips:1}}
 return{o:o}}
function run(t){const a=answer(t);let o;
 if(a===null){o=Object.assign({},last,parse(t))}else if(a.o)o=a.o;else return a;
 if(o.metric!=='ex'&&!o.n)o.n=5;if(o.metric==='ex'&&!o.n)o.n=6;
 const res=E.query(rows,o);last=Object.assign({},o);
 if(!res.items.length)return{h:'No company matches '+(describe(o)||'that')+' in the sample data. Try lowering the minimum yield or years, or removing the size or sector.'};
 const d=describe(o);
 return{h:'<b>'+esc(E.title(o))+'</b>'+(d?' <span class="dka-d">('+esc(d)+')</span>':'')+(o.period&&!res.m.per?'':'')+listHTML(res)+'<a href="'+E.link(Object.assign({},o,{n:20}))+'">Open the full ranking with filters</a>'+(res.m.per?'<p class="dka-n">'+esc(res.m.note)+'. Only companies with that much dividend history are counted.</p>':'')}}
function add(cls,html){const d=document.createElement('div');d.className='dka-m '+cls;d.innerHTML=html;log.appendChild(d);log.scrollTop=log.scrollHeight;return d}
function chips(){return '<div class="dka-c">'+SUG.map(s=>'<button type="button" data-s="'+esc(s)+'">'+esc(s)+'</button>').join('')+'</div>'}
function send(t){t=String(t||'').trim();if(!t)return;add('u',esc(t));inp.value='';const th=add('b dka-t','<i></i><i></i><i></i>');
 setTimeout(()=>{th.remove();let r;try{r=run(t)}catch(e){r={h:'Something went wrong while reading that. Please try rephrasing.'}}add('b',r.h+(r.chips?chips():''))},380)}
function build(){panel=document.createElement('div');panel.className='dka-p';panel.id='dkap';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','DhanKhoj assistant');
 panel.innerHTML='<div class="dka-h"><div><b>DhanKhoj assistant</b><small>Preview. Answers come from sample data, not a live AI model. Not investment advice.</small></div><button type="button" class="dka-x" aria-label="Close assistant">×</button></div><div class="dka-log" id="dkal" aria-live="polite"></div><form class="dka-f"><input id="dkai" type="text" autocomplete="off" placeholder="Ask, for example: top 5 large cap stocks" aria-label="Your question"><button class="btn" type="submit">Send</button></form>';
 document.body.appendChild(panel);log=panel.querySelector('#dkal');inp=panel.querySelector('#dkai');
 panel.querySelector('form').addEventListener('submit',e=>{e.preventDefault();send(inp.value)});
 panel.addEventListener('click',e=>{if(e.target.closest('.dka-x'))api.close();const c=e.target.closest('.dka-c button');if(c)send(c.dataset.s);if(e.target.closest('.dka-m a'))if(window.innerWidth<600)api.close()});
 panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();api.close()}if(e.key==='Tab'){const f=[...panel.querySelectorAll('button,input')].filter(x=>!x.disabled&&x.offsetParent);const a=f[0],z=f[f.length-1];if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus()}else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus()}}});
 add('b','Hello. Ask me for a list of dividend stocks, for example “top 5 large cap stocks with 10 years of dividends”, or ask what unclaimed dividends are.'+chips())}
const api={open:function(m){opener=document.activeElement;if(!panel)build();panel.classList.add('on');document.body.classList.add('dka-open');inp.focus();if(m)send(m)},
 close:function(){if(!panel)return;panel.classList.remove('on');document.body.classList.remove('dka-open');if(opener&&opener.focus)opener.focus()}};
window.dkAssistant=api;window.dxLoad().then(r=>{rows=r});
window.dkAssistant._run=run;
})();
