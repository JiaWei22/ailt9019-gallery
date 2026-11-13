(()=>{const header=document.querySelector('.site-header'),toggle=document.querySelector('.menu-toggle'),nav=document.querySelector('.nav-links');const close=()=>{header.classList.remove('menu-open');toggle.setAttribute('aria-expanded','false');toggle.textContent='Menu ☰';};toggle.addEventListener('click',()=>{const open=header.classList.toggle('menu-open');toggle.setAttribute('aria-expanded',String(open));toggle.textContent=open?'Close ×':'Menu ☰';});nav.addEventListener('click',e=>{if(e.target.closest('a'))close();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&header.classList.contains('menu-open')){close();toggle.focus();}});const update=()=>header.classList.toggle('scrolled',window.scrollY>40);window.addEventListener('scroll',update,{passive:true});update();window.matchMedia('(min-width:761px)').addEventListener('change',e=>{if(e.matches)close();});})();
(()=>{
 const hero=document.querySelector('.hero'),slides=[...document.querySelectorAll('.hero-photo')],dots=[...document.querySelectorAll('.photo-dots button')],caption=document.querySelector('#photo-caption'),pause=document.querySelector('#photo-pause');
 const reduced=window.matchMedia('(prefers-reduced-motion:reduce)');let index=0,paused=reduced.matches,timer=null,inView=true,touch=null;
 function sync(){clearInterval(timer);timer=null;hero.classList.toggle('slideshow-paused',paused);pause.setAttribute('aria-label',paused?'Play slideshow':'Pause slideshow');pause.textContent=paused?'▶':'Ⅱ';if(!paused&&!document.hidden&&inView&&!hero.hidden)timer=setInterval(()=>show(index+1),5000);}
 function show(next){index=(next+slides.length)%slides.length;slides.forEach((s,i)=>s.classList.toggle('active',i===index));dots.forEach((d,i)=>d.setAttribute('aria-current',String(i===index)));caption.textContent=slides[index].dataset.caption;sync();}
 document.querySelector('#photo-prev').addEventListener('click',()=>show(index-1));document.querySelector('#photo-next').addEventListener('click',()=>show(index+1));dots.forEach((d,i)=>d.addEventListener('click',()=>show(i)));pause.addEventListener('click',()=>{paused=!paused;sync();});document.addEventListener('visibilitychange',sync);document.addEventListener('courseviewchange',sync);reduced.addEventListener('change',e=>{paused=e.matches;sync();});
 new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;sync();},{threshold:.1}).observe(hero);
 hero.addEventListener('touchstart',e=>{if(e.target.closest('a,button'))return;touch={x:e.changedTouches[0].clientX,y:e.changedTouches[0].clientY};},{passive:true});hero.addEventListener('touchend',e=>{if(!touch)return;const dx=e.changedTouches[0].clientX-touch.x,dy=e.changedTouches[0].clientY-touch.y;touch=null;if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.5)show(index+(dx<0?1:-1));},{passive:true});sync();
})();

(()=>{
 const groups={home:['home'],course:['course','submission'],schedule:['schedule'],help:['faq','contact']};
 const aliases={faq:'help',contact:'help',submission:'course'};
 const titles={home:'Home',course:'Course',schedule:'Schedule',help:'Help & contact'};
 const sections=[...document.querySelectorAll('main section')],banner=document.querySelector('#view-banner'),title=document.querySelector('#view-title');
 function route(moveFocus=false){
  const hash=location.hash.slice(1),view=aliases[hash]||(groups[hash]?hash:'home');
  document.body.dataset.view=view;
  sections.forEach(section=>{const visible=groups[view].includes(section.id);section.hidden=!visible;section.classList.toggle('view-enter',visible&&view!=='home');});
  banner.hidden=view==='home';title.textContent=titles[view];document.querySelector('#view-crumb').textContent=titles[view];
  document.querySelectorAll('.nav-links a[href^="#"]').forEach(a=>{if(a.hash==='#'+view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  document.title=(view==='home'?'AILT9019 · Artificial Intelligence Literacy II':titles[view]+' · AILT9019');
  document.dispatchEvent(new Event('courseviewchange'));
  window.scrollTo({top:0,behavior:'instant'});
  if(moveFocus){const target=view==='home'?document.querySelector('main'):title;target.focus({preventScroll:true});}
 }
 document.addEventListener('click',e=>{
  const a=e.target.closest('a[href^="#"]');if(!a||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||e.button!==0)return;
  const key=a.hash.slice(1);if(!groups[key]&&!aliases[key])return;
  e.preventDefault();const dest=aliases[key]||key;
  if(location.hash!=='#'+dest)history.pushState(null,'','#'+dest);
  route(true);
 });
 window.addEventListener('popstate',()=>route(true));window.addEventListener('hashchange',()=>route(true));route();
})();
