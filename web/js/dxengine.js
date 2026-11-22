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
const PER=[1,3,5,10];
function query(rows,o){o=o||{};const m=M[o.metric]||M.yield,p=PER.indexOf(+o.period)>=0?+o.period:5;
 let l=rows.filter(r=>(!o.cap||r.cap===o.cap)&&(!o.sector||r.sector===o.sector)&&(!o.freq||r.freq===o.freq)&&(!o.min||r.yield>=+o.min)&&(!o.years||r.years>=+o.years)&&(!o.maxPayout||r.payout<=+o.maxPayout)&&(!o.minGrowth||r.cagr>=+o.minGrowth));
 if(m.per)l=l.filter(r=>r.years>=p&&r.ret[p]);
 let out=l.map(r=>({r:r,v:m.get(r,p)}));const asc=o.dir?o.dir==='asc':!!m.asc;
 out.sort((a,b)=>(asc?a.v-b.v:b.v-a.v)||b.r.years-a.r.years);
 return{items:out.slice(0,o.n||10),total:out.length,metric:o.metric&&M[o.metric]?o.metric:'yield',period:p,m:m}}
function title(o){const m=M[o.metric]||M.yield;const p=m.per?' over '+(o.period||5)+' years':'';return m.label+p}
function link(o){const q=[];['metric','period','cap','sector','min','years','n','freq','maxPayout','minGrowth'].forEach(k=>{if(o[k]!=null&&o[k]!=='')q.push(k+'='+encodeURIComponent(o[k]))});return '/insights.html?'+q.join('&')+'#table'}
window.DX={M:M,PER:PER,query:query,title:title,link:link};
})();
