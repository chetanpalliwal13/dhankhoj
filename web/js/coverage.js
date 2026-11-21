let timer=null;
const VAL={ok:'Read and total checked',unverified:'Read, total not printed',partial:'Partly read',mismatch:'Needs review'};
function ago(s){if(!s)return '-';const d=Math.floor((Date.now()-new Date(s+'Z').getTime())/864e5);return d<=0?'today':d===1?'1 day ago':d+' days ago'}
async function load(){const q=document.getElementById('q').value.trim();
  try{const r=await api('/api/coverage'+(q?'?q='+encodeURIComponent(q):''));
    document.getElementById('sum').textContent=r.companies_covered+' of '+r.companies_total+' companies in our registry have a list loaded.';
    document.getElementById('rows').innerHTML=r.companies.length?r.companies.map(c=>'<tr><td>'+esc(c.name)+'</td><td>'+esc([c.nse_symbol,c.bse_code].filter(Boolean).join(' / ')||'-')+'</td><td>'+(c.last_list?esc(ago(c.last_list)):'-')+'</td><td>'+(c.state==='covered'?'<span class="pill">'+esc(VAL[c.validation]||'Loaded')+'</span>':'<span class="pill low">Not checked yet</span>')+'</td></tr>').join(''):'<tr><td colspan="4">No company found. Try the NSE symbol or ISIN.</td></tr>';
    document.getElementById('note').textContent=r.note;
    document.getElementById('official').innerHTML=r.official.map(o=>'<li><a href="'+esc(o.url)+'" target="_blank" rel="noopener noreferrer">'+esc(o.name)+'</a></li>').join('')}
  catch(e){document.getElementById('sum').textContent='Could not load coverage. Please try again.'}}
document.getElementById('q').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,300)});
load();
