(async()=>{const mode=document.currentScript.dataset.mode,qs=new URLSearchParams(location.search);
 if(await session()){location.replace(mode==='signin'?safeNext():'/dashboard.html');return}
 let message=null;const g=qs.get('gerr');
 if(g)message={type:'err',text:GERR[g]||GERR.failed};
 else if(qs.get('out'))message={type:'ok',text:'You have been signed out.'};
 else if(qs.get('idle'))message={type:'ok',text:'You were signed out after a few minutes of inactivity. Please sign in again.'};
 openAuth(mode,{message,next:mode==='signin'?safeNext():undefined,onClose:()=>location.replace('/')})})();
