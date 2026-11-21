(async()=>{const u=await requireLogin();if(!u)return;const id=new URLSearchParams(location.search).get('id')||'0';
 try{const r=await api('/api/pay/receipt?id='+encodeURIComponent(id));
  $('#body').className='';$('#body').innerHTML=`<p><b>${esc(r.seller)}</b>${r.gstin?'<br>GSTIN: '+esc(r.gstin):''}</p><table><tr><td>Receipt no.</td><td>${esc(r.receipt_no)}</td></tr><tr><td>Date</td><td>${esc(r.date)}</td></tr><tr><td>Billed to</td><td>${esc(r.billed_to)} (${esc(r.email)})</td></tr>
  <tr><td>Item</td><td>${esc(r.item)} - ${r.plan_days} days purchased, valid until ${esc(r.valid_until||'')}</td></tr>${r.gst_percent?`<tr><td>Taxable value</td><td>${inr(r.taxable)}</td></tr><tr><td>GST @ ${r.gst_percent}%</td><td>${inr(r.gst)}</td></tr>`:''}
  <tr><td><b>Total paid</b></td><td><b>${inr(r.amount)}</b></td></tr><tr><td>Payment method / reference</td><td>${esc(r.method||'')} ${esc(r.reference||'')}</td></tr></table>`}
 catch(e){$('#body').textContent=e.message}})();
$('#pr').addEventListener('click',()=>window.print());
