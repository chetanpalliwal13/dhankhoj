/* DhanKhoj language switcher: self-hosted dictionaries, no external scripts. */
(function(){
'use strict';
var LANGS=[['en','English'],['hi','हिन्दी'],['mr','मराठी'],['bn','বাংলা'],['ta','தமிழ்'],['te','తెలుగు'],['kn','ಕನ್ನಡ'],['ml','മലയാളം'],['pa','ਪੰਜਾਬੀ'],['or','ଓଡ଼ିଆ']];
var CODES=LANGS.map(function(l){return l[0]});
var KEY='dk_lang',DICT={},cur='en',busy=false,ATTR=['placeholder','title','aria-label','alt'];
var orig=new WeakMap();           // node -> original English
var SKIP={SCRIPT:1,STYLE:1,NOSCRIPT:1,TEXTAREA:1,CODE:1};
function norm(s){return s.replace(/\s+/g,' ').trim()}
function key(s){var n=[];var k=s.replace(/\d[\d,.]*/g,function(m){n.push(m);return '{#}'});return {k:k,n:n}}
function lookup(text){
  var d=DICT[cur];if(!d)return null;
  var t=norm(text);if(!t)return null;
  var q=key(t),v=d[q.k];
  if(v==null){ // allow trailing punctuation to fall back
    return null}
  var i=0;return v.replace(/\{#\}/g,function(){return q.n[i++]||''});
}
function trText(node){
  var o=orig.get(node);
  if(o==null||(node.nodeValue!==o.out&&node.nodeValue!==o.src)){o={src:node.nodeValue,out:null};orig.set(node,o)}
  if(cur==='en'){if(o.src!=null&&node.nodeValue!==o.src)node.nodeValue=o.src;return}
  var r=lookup(o.src);
  if(r!=null){var lead=/^\s*/.exec(o.src)[0],tail=/\s*$/.exec(o.src)[0];o.out=lead+r+tail;if(node.nodeValue!==o.out)node.nodeValue=o.out}
  else if(node.nodeValue!==o.src)node.nodeValue=o.src;
}
function trAttrs(el){
  for(var i=0;i<ATTR.length;i++){var a=ATTR[i];if(!el.hasAttribute(a))continue;
    var sk='data-i18n-'+a,src=el.getAttribute(sk),now=el.getAttribute(a);
    if(src==null||(now!==src&&now!==el.__dkOut)){src=now;el.setAttribute(sk,src)}
    var r=cur==='en'?src:lookup(src);var v=r!=null?r:src;
    if(v!==now){el.__dkOut=v;el.setAttribute(a,v)}}
}
function walk(root){
  if(!root)return;
  if(root.nodeType===3){if(root.parentNode&&!SKIP[root.parentNode.nodeName])trText(root);return}
  if(root.nodeType!==1||SKIP[root.nodeName])return;
  if(root.closest&&root.closest('[data-no-i18n]'))return;
  trAttrs(root);
  var w=document.createTreeWalker(root,5,{acceptNode:function(n){
    if(n.nodeType===1)return SKIP[n.nodeName]||n.hasAttribute('data-no-i18n')?2:1;
    return norm(n.nodeValue)?1:3}});
  var n;while((n=w.nextNode())){if(n.nodeType===3)trText(n);else trAttrs(n)}
}
function meta(){
  var t=document.documentElement;
  if(!meta.t){meta.t=document.title;var m=document.querySelector('meta[name=description]');meta.d=m?m.getAttribute('content'):null}
  var tt=cur==='en'?null:lookup(meta.t);document.title=tt||meta.t;
  var m=document.querySelector('meta[name=description]');
  if(m&&meta.d){var dd=cur==='en'?null:lookup(meta.d);m.setAttribute('content',dd||meta.d)}
}
function apply(){busy=true;try{walk(document.body);meta();syncSel()}finally{obs.takeRecords();busy=false}}
var obs=new MutationObserver(function(ms){
  if(busy)return;
  busy=true;
  try{ms.forEach(function(m){
    if(m.type==='childList')m.addedNodes.forEach(function(n){walk(n)});
    else if(m.type==='characterData')walk(m.target);
    else if(m.type==='attributes'&&m.target.nodeType===1)trAttrs(m.target)});
    injectSwitch()}
  finally{obs.takeRecords();busy=false}
});
function load(code,cb){
  if(code==='en'||DICT[code])return cb();
  var s=document.createElement('script');s.src='/js/i18n/'+code+'.js?v=1';
  s.onload=function(){cb()};s.onerror=function(){cb()};document.head.appendChild(s);
}
window.DK_I18N={add:function(code,d){DICT[code]=Object.assign(DICT[code]||{},d)},t:function(s){var r=cur==='en'?null:lookup(s);return r!=null?r:s},get lang(){return cur}};
function setLang(code){
  if(CODES.indexOf(code)<0)code='en';
  load(code,function(){
    cur=code;try{localStorage.setItem(KEY,code)}catch(e){}
    document.documentElement.lang=code;document.documentElement.setAttribute('data-lang',code);
    apply()});
}
function syncSel(){document.querySelectorAll('.lsw select').forEach(function(s){if(s.value!==cur)s.value=cur})}
function injectSwitch(){
  if(document.querySelector('.lsw'))return;
  var hr=document.getElementById('hr');if(!hr||!hr.parentNode)return;
  var d=document.createElement('div');d.className='lsw';d.setAttribute('data-no-i18n','');
  d.innerHTML='<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.8 3 2.8 15 0 18M12 3c-2.8 3-2.8 15 0 18"/></svg><select aria-label="Language" title="Language">'+
   LANGS.map(function(l){return '<option value="'+l[0]+'" lang="'+l[0]+'">'+l[1]+'</option>'}).join('')+'</select>';
  hr.parentNode.insertBefore(d,hr);
  var s=d.querySelector('select');s.value=cur;s.addEventListener('change',function(){setLang(s.value)});
}
function start(){
  var saved='en';try{saved=localStorage.getItem(KEY)||'en'}catch(e){}
  var q=/[?&]lang=([a-z]{2})/.exec(location.search);if(q&&CODES.indexOf(q[1])>=0)saved=q[1];
  injectSwitch();
  obs.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:ATTR});
  if(saved!=='en')setLang(saved);
  // header is built by common.js after load; retry a few times
  var n=0,iv=setInterval(function(){injectSwitch();if(++n>20)clearInterval(iv)},250);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
