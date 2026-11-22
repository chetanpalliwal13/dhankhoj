(async()=>{const box=document.getElementById('stories');if(!box)return;
 try{const r=await api('/api/testimonials');if(!r.stories||!r.stories.length)return;
  box.querySelector('.stgrid').outerHTML=stCards(r.stories,8);box.classList.remove('hide')}catch(e){}})();
