
let timer=null,all=[],page=1,per=10;
const VAL={ok:'Read and total checked',unverified:'Read, total not printed',partial:'Partly read',mismatch:'Needs review'};
function ago(s){if(!s)return '-';const d=Math.floor((Date.now()-new Date(s+'Z').getTime())/864e5);return d<=0?'today':d===1?'1 day ago':d+' days ago'}
const G=id=>document.getElementById(id);
function pages(n,cur){const W=5;let a=Math.max(1,cur-2),b=a+W-1;if(b>n){b=n;a=Math.max(1,b-W+1)}const o=[];for(let i=a;i<=b;i++)o.push(i);return o}
function paint(){const n=Math.max(1,Math.ceil(all.length/per));if(page>n)page=n;const s=(page-1)*per,l=all.slice(s,s+per);
  G('rows').innerHTML=l.length?l.map(c=>'<tr><td>'+esc(c.name)+'</td><td>'+esc([c.nse_symbol,c.bse_code].filter(Boolean).join(' / ')||'-')+'</td><td>'+(c.last_list?esc(ago(c.last_list)):'-')+'</td><td>'+(c.state==='covered'?'<span class="pill">'+esc(VAL[c.validation]||'Loaded')+'</span>':'<span class="pill low">Not checked yet</span>')+'</td></tr>').join(''):'<tr><td colspan="4">No company found. Try the NSE symbol or ISIN.</td></tr>';
  G('cinfo').textContent=all.length?'Showing '+(s+1)+' to '+(s+l.length)+' of '+all.length:'';
  const b=(t,p,d,on)=>'<button type="button" class="'+(on?'on':'')+'" data-p="'+p+'"'+(d?' disabled':'')+(on?' aria-current="page"':'')+'>'+t+'</button>';
  G('pg').innerHTML=n>1?b('‹',page-1,page===1)+pages(n,page).map(i=>b(i,i,false,i===page)).join('')+b('›',page+1,page===n):'';
  G('covs').scrollTop=0}
async function load(){const q=G('q').value.trim();
  try{const r=await api('/api/coverage?limit=1000'+(q?'&q='+encodeURIComponent(q):''));all=r.companies;page=1;paint();
    G('note').textContent=r.note;
    G('official').innerHTML=r.official.map(o=>'<li><a href="'+esc(o.url)+'" target="_blank" rel="noopener noreferrer">'+esc(o.name)+'</a></li>').join('')}
  catch(e){G('note').textContent='Could not load coverage. Please try again.'}}
G('q').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,300)});
G('pp').addEventListener('change',e=>{per=+e.target.value;page=1;G('covs').classList.toggle('scroll',per>10);paint()});
G('pg').addEventListener('click',e=>{const b=e.target.closest('button[data-p]');if(b&&!b.disabled){page=+b.dataset.p;paint()}});
load();
