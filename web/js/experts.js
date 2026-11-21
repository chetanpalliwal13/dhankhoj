$('#f').addEventListener('submit',async e=>{e.preventDefault();const m=$('#msg');
 try{await api('/api/expert/register',{name:$('#n').value,profession:$('#p').value,membership_no:$('#m').value,city:$('#c').value,email:$('#e').value,phone:$('#t').value,languages:$('#l').value,consent:$('#k').checked});
  $('#f').classList.add('hide');show(m,'ok','Thank you. We will verify your membership and contact you by email.')}catch(err){show(m,'err',err.message)}});
