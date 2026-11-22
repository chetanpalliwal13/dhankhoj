/* Ranking engine for sample data. Used by the Insights page and the assistant, so both give the same answers. */
(function(){
const F=window.dxFmt;
const M={
 yield:{label:'Dividend yield',per:0,get:r=>r.yield,fmt:v=>F.pc(v),note:'Latest yearly dividend divided by price'},
 divret:{label:'Dividend return',per:1,get:(r,p)=>r.ret[p].div,fmt:v=>F.pc(v,1),note:'Dividends received over the period, as a share of the price at the start'},
 totalret:{label:'Total return (price + dividends)',per:1,get:(r,p)=>r.ret[p].total,fmt:v=>F.pct(v,0),note:'Price change plus dividends received over the period'},
 priceret:{label:'Price return',per:1,get:(r,p)=>r.ret[p].price,fmt:v=>F.pct(v,0),note:'Price change only'},
 years:{label:'Years paid in a row',per:0,get:r=>r.years,fmt:v=>v+' yrs',note:'Consecutive years with a dividend'},
 pays:{label:'Dividend payouts in 10 years',per:0,get:r=>r.pays10,fmt:v=>v+' payouts',note:'Number of dividend payments in the last 10 years'},
 growth:{label:'Dividend growth (5Y a year)',per:0,get:r=>r.cagr,fmt:v=>F.pc(v,0),note:'Yearly growth of the dividend over five years'},
 mcap:{label:'Market cap',per:0,get:r=>r.mcap,fmt:v=>F.cr(v),note:'Company size'},
 payout:{label:'Payout ratio (lowest first)',per:0,asc:1,get:r=>r.payout,fmt:v=>v+'%',note:'Share of profit paid out. Lower leaves more room to keep paying'},
 ex:{label:'Next ex-dividend date',per:0,asc:1,get:r=>r.exIn,fmt:v=>v===0?'Today':'in '+v+' days',note:'You must hold the share before this date to get the dividend'}
};
const PER=['1m','3m','6m','1y','3y','5y','10y'],PL={'1m':'1 month','3m':'3 months','6m':'6 months',1:'1 year',3:'3 years',5:'5 years',10:'10 years'};
function pk(v){v=String(v==null?'':v).toLowerCase();if(/^\d+$/.test(v))v+='y';if(/^\d+m$/.test(v))return PER.indexOf(v)>=0?v:'3m';const m=v.match(/^(\d+)y$/);if(m&&[1,3,5,10].indexOf(+m[1])>=0)return +m[1];return 5}
function query(rows,o){o=o||{};const m=M[o.metric]||M.yield,p=pk(o.period);
 let l=rows.filter(r=>(!o.cap||r.cap===o.cap)&&(!o.sector||r.sector===o.sector)&&(!o.freq||r.freq===o.freq)&&(!o.min||r.yield>=+o.min)&&(!o.years||r.years>=+o.years)&&(!o.maxPayout||r.payout<=+o.maxPayout)&&(!o.minGrowth||r.cagr>=+o.minGrowth));
 if(m.per)l=l.filter(r=>r.ret[p]&&(typeof p==='string'?r.years>=1:r.years>=p));
 let out=l.map(r=>({r:r,v:m.get(r,p)}));const asc=o.dir?o.dir==='asc':!!m.asc;
 out.sort((a,b)=>(asc?a.v-b.v:b.v-a.v)||b.r.years-a.r.years);
 return{items:out.slice(0,o.n||10),total:out.length,metric:o.metric&&M[o.metric]?o.metric:'yield',period:p,m:m}}
function title(o){const m=M[o.metric]||M.yield;const p=m.per?' over '+PL[pk(o.period)]:'';return m.label+p}
function link(o){const q=[];['metric','period','cap','sector','min','years','n','freq','maxPayout','minGrowth'].forEach(k=>{if(o[k]!=null&&o[k]!=='')q.push(k+'='+encodeURIComponent(o[k]))});return '/insights.html?'+q.join('&')+'#table'}
const WK='dk_watch';function wget(){try{const a=JSON.parse(localStorage.getItem(WK)||'[]');return Array.isArray(a)?a:[]}catch(e){return[]}}
window.dkWatch={get:wget,has:s=>wget().indexOf(s)>=0,toggle:s=>{let a=wget();const i=a.indexOf(s);if(i>=0)a.splice(i,1);else a.push(s);try{localStorage.setItem(WK,JSON.stringify(a.slice(0,50)))}catch(e){}return i<0}};
window.DX={M:M,PER:PER,PL:PL,pk:pk,query:query,title:title,link:link};
})();
