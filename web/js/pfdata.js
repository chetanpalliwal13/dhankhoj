// Sample portfolio data for the preview. Nothing here is real or saved.
window.PF=(()=>{const F=n=>'₹'+Math.round(n).toLocaleString('en-IN');
const MF=[['Parag Parikh Flexi Cap Fund',210000,16.2],['Quant Small Cap Fund',115216,27.4],['HDFC Mid-Cap Opportunities',100000,21.1],['SBI Bluechip Fund',100000,13.6]],
ST=[['HDFC Bank',92782,11.8],['Infosys',70000,9.4],['ITC',60000,24.9],['Coal India',40000,38.2]],
FD=[['HDFC Bank FD (7.1%, 3 yrs)',87362,7.1]];
const hold=[...MF.map(x=>({n:x[0],t:'Mutual Fund',v:x[1],r:x[2]})),...ST.map(x=>({n:x[0],t:'Stock',v:x[1],r:x[2]})),...FD.map(x=>({n:x[0],t:'Fixed Deposit',v:x[1],r:x[2]}))];
const sum=a=>a.reduce((s,x)=>s+x[1],0);
return{F,hold,total:875360,invested:749930,returns:125430,retPct:18.73,today:2450,todayPct:0.38,
alloc:[['Mutual Funds',60,sum(MF),'#2E7BE6'],['Stocks',30,sum(ST),'#1B9E3A'],['FD',10,sum(FD),'#F2A516']],
recent:[['SIP in Parag Parikh Flexi Cap Fund',5000,'Today'],['Investment in HDFC Bank FD',100000,'2 days ago'],['SIP in Quant Small Cap Fund',3000,'3 days ago']],
sips:[['Parag Parikh Flexi Cap Fund',5000,'5th of every month','Active'],['Quant Small Cap Fund',3000,'12th of every month','Active'],['HDFC Mid-Cap Opportunities',2000,'20th of every month','Paused']],
goals:[['Retirement corpus',5000000,2150000],['Child education',1500000,1020000],['Emergency fund',300000,285000]],
tx:[['Today','SIP','Parag Parikh Flexi Cap Fund',5000],['2 days ago','Investment','HDFC Bank FD',100000],['3 days ago','SIP','Quant Small Cap Fund',3000],['12 days ago','Buy','Infosys',20000],['25 days ago','SIP','Parag Parikh Flexi Cap Fund',5000],['27 days ago','Buy','ITC',15000]],
market:[['NIFTY 50','22,530.70',0.65],['SENSEX','74,123.57',0.59],['USD / INR','83.19',-0.12]],
side(on){const I=p=>'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+'</svg>';
 const L=[['/dashboard.html','dash','Dashboard','<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>'],
 ['/portfolio.html#investments','investments','My Investments','<path d="M3 17l5-5 4 4 8-9"/>'],['/dashboard.html#results','div','My unclaimed dividends','<path d="M12 2v20M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.6 7 6.5 9.2 9.5 12 10s5 1.4 5 3.5-2.2 3-5 3-5-1.1-5-3"/>'],
 ['/dashboard.html#mkt','watch','Watchlist','<path d="M12 2l3 6.5 7 .9-5.1 4.8 1.3 7L12 17.8 5.8 21.2l1.3-7L2 9.4l7-.9z"/>'],['/portfolio.html#sip','sip','SIP Dashboard','<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/>'],
 ['/portfolio.html#analysis','analysis','Portfolio Analysis','<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'],['/portfolio.html#goals','goals','Goal Planner','<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>'],
 ['/portfolio.html#transactions','transactions','Transactions','<path d="M7 7h13M7 7l3-3M7 7l3 3M17 17H4M17 17l-3-3M17 17l-3 3"/>'],['/insights.html','ins','Dividend insights','<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'],['/coverage.html','cov','Coverage','<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'],
 ['/upgrade.html','plan','Plan &amp; billing','<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>'],['/account.html','acct','Account settings','<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>']];
 return L.map(l=>'<a'+(l[1]===on?' class="on"':'')+' href="'+l[0]+'">'+I(l[3])+l[2]+'</a>').join('')+'<hr><a href="/contact.html">'+I('<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7M12 17h0"/>')+'Help &amp; support</a><a href="#" id="signout2">'+I('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>')+'Logout</a>'}};})();
