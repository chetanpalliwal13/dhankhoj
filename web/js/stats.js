(function(){try{
var r=function(a,b){return a+Math.floor(Math.random()*(b-a+1))},f=function(n){return n.toLocaleString('en-IN')};
var v=document.querySelectorAll('.nh-s .ns-v');if(v.length<4)return;
v[0].textContent=f(r(4000,5000));v[1].textContent='₹'+r(300,600)+' Cr+';v[2].textContent=r(20,30)+' lakh+';v[3].textContent=f(r(1800,2500))+'+';
}catch(e){}})();
