(()=>{'use strict';if(window.hallUnsupported)return;const data=JSON.parse(document.getElementById('hall-projects').textContent),selected=new Set(JSON.parse(document.getElementById('hall-selected').textContent)),canVote=document.getElementById('hall-config').dataset.canVote==='true';
const $=id=>document.getElementById(id),viewport=$('viewport'),world=$('world'),avatar=$('avatar'),dialog=$('booth-dialog'),frame=$('booth-frame'),message=$('hall-message');
const lastNumber=Math.max(0,...data.map(p=>p.number));const columnSpacing=460,rowSpacing=380,zoneSpacing=920;const width=2300,height=Math.max(1000,Math.ceil(lastNumber/5)*rowSpacing+Math.ceil(lastNumber/10)*160+440);world.style.height=height+'px';let x=1150,y=610,target=null,current=null,near=null,last=0,dirty=false,zoom=.85,walkPhase=0,moving=false,lastFocus=null;const initialSelection=[...selected].sort().join(',');const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;const keys=new Set();let route=[];const visitKey='ailt-exhibition-visited-'+$('hall-config').dataset.visitKey;let restoredVisits=[];try{restoredVisits=JSON.parse(sessionStorage.getItem(visitKey)||'[]');}catch{}const visited=new Set((Array.isArray(restoredVisits)?restoredVisits:[]).filter(id=>data.some(p=>p.id===id)));$('visit-count').textContent=visited.size+' / '+data.length+' explored';$('visit-progress').value=visited.size;
data.forEach(p=>{const i=p.number-1;p.x=70+(i%5)*columnSpacing;p.y=350+Math.floor(i/5)*rowSpacing+Math.floor(i/10)*160;const b=document.createElement('button');b.className='booth';b.type='button';b.style.left=p.x+'px';b.style.top=p.y+'px';const tag=document.createElement('small');tag.textContent=p.code;const title=document.createElement('strong');title.textContent=p.title;const help=document.createElement('small');help.className='booth-status';help.textContent='↗';b.setAttribute('aria-label',tag.textContent+' · '+p.title);b.title=p.team+' · '+p.title+' · Presentation + Demo';b.append(title,help);b.onclick=()=>open(p);world.append(b);p.button=b;});
function open(p){visited.add(p.id);try{sessionStorage.setItem(visitKey,JSON.stringify([...visited]));}catch{}p.button.querySelector('.booth-status').textContent=selected.has(p.id)?'♥':'✓';$('visit-count').textContent=visited.size+' / '+data.length+' explored';$('visit-progress').value=visited.size;lastFocus=document.activeElement;current=p;keys.clear();target=null;route=[];$('booth-name').textContent=p.code+' · '+p.team+' · '+p.title;frame.src=p.url;updateChoose();dialog.showModal();}
function updateChoose(){$('dialog-message').textContent=selected.size+' / 3 projects in your draft';$('choose-project').disabled=!canVote||!current.canVote;$('choose-project').textContent=selected.has(current.id)?'Remove from ballot':'Add project to ballot';}
function close(){dialog.close();frame.src='about:blank';keys.clear();(lastFocus?.isConnected?lastFocus:viewport).focus();} $('close-booth').onclick=close;dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
function toggle(p){if(!canVote||!p.canVote)return;if(selected.has(p.id))selected.delete(p.id);else if(selected.size<3)selected.add(p.id);else{$('dialog-message').textContent='3 / 3 selected. Remove one before adding another.';return;}dirty=[...selected].sort().join(',')!==initialSelection;renderDraft();if(current)updateChoose();}
$('choose-project').onclick=()=>toggle(current);
function renderDraft(){$('ballot-badge').textContent=selected.size;$('draft-state').textContent=dirty?'You have unsaved changes.':'Saved selections loaded.';data.forEach(p=>{p.button.classList.toggle('selected',selected.has(p.id));p.button.querySelector('.booth-status').textContent=selected.has(p.id)?'♥':visited.has(p.id)?'✓':'↗';});$('draft-count').textContent=selected.size+' / 3 projects selected';$('draft-list').replaceChildren();if($('draft-inputs'))$('draft-inputs').replaceChildren();data.filter(p=>selected.has(p.id)).forEach(p=>{const li=document.createElement('li');li.textContent=p.code+' · '+p.title+' ';if(canVote){const b=document.createElement('button');b.type='button';b.textContent='Remove';b.onclick=()=>toggle(p);li.append(b);const input=document.createElement('input');input.type='hidden';input.name='choices';input.value=p.id;$('draft-inputs').append(input);}$('draft-list').append(li);});if($('review-ballot'))$('review-ballot').disabled=!selected.size;}
renderDraft();function options(){const q=$('booth-search').value.toLowerCase();$('booth-picker').replaceChildren();data.filter(p=>(p.title+' '+p.team+' '+p.code+' '+p.number).toLowerCase().includes(q.trim())).forEach(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.code+' · '+p.title;$('booth-picker').append(o);});const n=$('booth-picker').options.length;if(n)$('booth-picker').selectedIndex=0;$('travel').disabled=!n;$('search-count').textContent=n+' matching project'+(n===1?'':'s');}function teleportToSelection(focusHall=false){const p=data.find(p=>p.id===$('booth-picker').value*1);if(!p)return;x=p.x+118;y=p.y-45;target=null;route=[];keys.clear();message.textContent='Arrived at '+p.code+' · '+p.title;if(focusHall)viewport.focus();}
$('booth-search').oninput=()=>{options();if($('booth-search').value.trim()&&$('booth-picker').options.length===1)teleportToSelection();};options();
$('travel').onclick=()=>teleportToSelection(true);
$('booth-picker').onchange=()=>teleportToSelection();
$('booth-picker').onclick=()=>teleportToSelection();
for(const input of [$('booth-search'),$('booth-picker')])input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();e.stopPropagation();teleportToSelection(true);}});
function blocked(nx,ny){return data.some(p=>nx>p.x-16&&nx<p.x+251&&ny>p.y-18&&ny<p.y+162);}
function move(dx,dy){const nx=Math.max(20,Math.min(width-20,x+dx)),ny=Math.max(30,Math.min(height-30,y+dy));if(!blocked(nx,y))x=nx;if(!blocked(x,ny))y=ny;}
const movementCodes={KeyW:'w',KeyA:'a',KeyS:'s',KeyD:'d',ArrowUp:'ArrowUp',ArrowDown:'ArrowDown',ArrowLeft:'ArrowLeft',ArrowRight:'ArrowRight'};
window.addEventListener('keydown',e=>{if(dialog.open||e.isComposing||e.ctrlKey||e.metaKey||e.altKey)return;if(e.target.closest&&e.target.closest('input,textarea,select,[contenteditable="true"]'))return;const key=movementCodes[e.code]||movementCodes[e.key];if(key){e.preventDefault();keys.add(key);target=null;route=[];}if(e.key==='Enter'&&e.target===viewport&&near){e.preventDefault();open(near);}});
window.addEventListener('keyup',e=>keys.delete(movementCodes[e.code]||movementCodes[e.key]));window.addEventListener('blur',()=>keys.clear());document.addEventListener('visibilitychange',()=>{if(document.hidden)keys.clear();});
document.querySelectorAll('[data-key]').forEach(b=>{b.onpointerdown=e=>{e.preventDefault();keys.add(b.dataset.key);target=null;route=[];b.setPointerCapture(e.pointerId);};b.onpointerup=b.onpointercancel=b.onlostpointercapture=()=>keys.delete(b.dataset.key);});
function iso(a,b,z=0){return {x:(a-b)*.68,y:(a+b)*.34-z};}function uniso(a,b){return {x:a/1.36+b/.68,y:b/.68-a/1.36};}let cx=0,cy=0;viewport.addEventListener('pointerdown',e=>{if(e.target!==viewport&&e.target!==world&&e.target.tagName!=='CANVAS')return;viewport.focus();const r=viewport.getBoundingClientRect();const hit=uniso((e.clientX-r.left)/zoom+cx,(e.clientY-r.top+cy*zoom)/zoom);navigate(hit.x,hit.y);});
const canvas=$('map'),ctx=canvas.getContext('2d');canvas.onclick=e=>{const r=canvas.getBoundingClientRect(),nx=(e.clientX-r.left)/r.width*width,ny=(e.clientY-r.top)/r.height*height;if(!blocked(nx,ny)){message.textContent='';x=nx;y=ny;target=null;route=[];viewport.focus();}};
// Place labels above the screen bounds; reserve every video and placed label.
function layoutLabels(screen){
 const projectPoint=pt=>({x:(pt.x-cx)*zoom,y:(pt.y-cy)*zoom});
 const overlaps=(a,b)=>a.l<b.r&&a.r>b.l&&a.t<b.b&&a.b>b.t;
 const videoRects=data.map(p=>{const a=projectPoint(iso(p.x+27,p.y+29,109)),b=projectPoint(iso(p.x+208,p.y+29,34));return {l:a.x-9,r:b.x+9,t:a.y-9,b:b.y+9};});
 const avatarPoint=projectPoint(screen),occupied=[{l:avatarPoint.x-24,r:avatarPoint.x+24,t:avatarPoint.y-66*zoom,b:avatarPoint.y+24}];
 const viewportRect=viewport.getBoundingClientRect();
 viewport.querySelectorAll('.scene-top,.map-card,.movement-dock,#open-near').forEach(el=>{if(!el.offsetWidth)return;const r=el.getBoundingClientRect();if(el.classList.contains('scene-top')){for(const child of el.children){const c=child.getBoundingClientRect();occupied.push({l:c.left-viewportRect.left-6,r:c.right-viewportRect.left+6,t:c.top-viewportRect.top-6,b:c.bottom-viewportRect.top+6});}}else occupied.push({l:r.left-viewportRect.left-6,r:r.right-viewportRect.left+6,t:r.top-viewportRect.top-6,b:r.bottom-viewportRect.top+6});});
 const ranked=data.map((p,i)=>({p,i,d:Math.hypot(p.x+118-x,p.y+72-y)})).sort((a,b)=>a.d-b.d);
 for(const {p,i} of ranked){
  const rect=videoRects[i],w=p.button.offsetWidth,h=p.button.offsetHeight,center=(rect.l+rect.r)/2;
  p.button.style.visibility='hidden';
  if(rect.r<0||rect.l>viewport.clientWidth||rect.b<0||rect.t>viewport.clientHeight)continue;
  let chosen=null;
  for(const dy of [0,28,56,84,112]){for(const dx of [0,-40,40,-80,80]){
   const box={l:center+dx-w/2-6,r:center+dx+w/2+6,t:rect.t-12-dy-h-6,b:rect.t-12-dy+6};
   if(box.l<4||box.r>viewport.clientWidth-4||box.t<4||box.b>viewport.clientHeight-4)continue;
   if(videoRects.some(v=>overlaps(box,v))||occupied.some(o=>overlaps(box,o)))continue;
   chosen={box,cx:center+dx,bottom:rect.t-12-dy};break;
  }if(chosen)break;}
  if(chosen){p.button.style.left=chosen.cx+'px';p.button.style.top=chosen.bottom+'px';p.button.style.visibility='visible';occupied.push(chosen.box);}
 }
}
function tick(time){if(!dialog.open&&!target&&route.length)target=route.shift();moving=false;const dt=Math.min((time-last)/1000,.05);last=time;if(!dialog.open){let dx=(keys.has('ArrowRight')||keys.has('d')?1:0)-(keys.has('ArrowLeft')||keys.has('a')?1:0),dy=(keys.has('ArrowDown')||keys.has('s')?1:0)-(keys.has('ArrowUp')||keys.has('w')?1:0);if(dx||dy){const sx=dx;dx=sx+dy;dy=dy-sx;}if(!dx&&!dy&&target){dx=target.x-x;dy=target.y-y;if(Math.hypot(dx,dy)<8){target=null;dx=dy=0;}}const len=Math.hypot(dx,dy);if(len){const ox=x,oy=y;const distance=Math.min(400*dt,target?len:Infinity);move(dx/len*distance,dy/len*distance);moving=Math.hypot(x-ox,y-oy)>.1;if(target&&Math.hypot(x-ox,y-oy)<.01)target=null;}}
const screen=iso(x,y);cx=screen.x-viewport.clientWidth/(2*zoom);cy=screen.y-viewport.clientHeight*.46/zoom;world.style.transform='none';avatar.style.left=(x-15)+'px';avatar.style.top=(y-15)+'px';data.forEach(p=>{const base=iso(p.x+117,p.y+70);if(p.artwork)p.artwork.alpha=p.x+p.y+235>x+y+35&&Math.abs(base.x-screen.x)<115&&base.y-screen.y> -10&&base.y-screen.y<155?.20:1;if(p.screenImages)p.screenImages.forEach(img=>img.alpha=p.artwork.alpha);});layoutLabels(screen);let best=190,next=null;data.forEach(p=>{const d=Math.hypot(x-(p.x+118),y-(p.y+72));if(d<best){best=d;next=p;}});if(next!==near){near=next;data.forEach(p=>p.button.classList.toggle('near',p===near));$('open-near').disabled=!near;$('open-near').textContent=near?'Explore '+near.title+'  ↗':'Walk towards a project';}
ctx.clearRect(0,0,240,135);ctx.fillStyle='#70cdb6';data.forEach(p=>ctx.fillRect(p.x/width*240,p.y/height*135,235/width*240,145/height*135));ctx.fillStyle='#ffdb70';ctx.beginPath();ctx.arc(x/width*240,y/height*135,4,0,Math.PI*2);ctx.fill();if(sceneRef){sceneRef.cameras.main.setZoom(zoom);sceneRef.cameras.main.setScroll(screen.x-viewport.clientWidth/2,screen.y-viewport.clientHeight/2+viewport.clientHeight*.04/zoom);character.setPosition(screen.x,screen.y);character.setDepth(x+y+35);walkPhase+=dt*11;legLeft.y=-10+(moving&&!reduced?Math.sin(walkPhase)*3:0);legRight.y=-10+(moving&&!reduced?-Math.sin(walkPhase)*3:0);armLeft.rotation=moving&&!reduced?Math.sin(walkPhase)*.2:0;armRight.rotation=-armLeft.rotation;character.scaleY=1+(moving&&!reduced?Math.sin(walkPhase*2)*.015:0);viewport.dataset.position=x.toFixed(1)+','+y.toFixed(1);const zi=Math.max(0,Math.min(zones.length-1,Math.floor((y-290)/zoneSpacing)));if(zi!==activeZone){activeZone=zi;updateZone();}}}


let sceneRef,character,legLeft,legRight,armLeft,armRight;
const surface=document.createElement('div');surface.style.cssText='position:absolute;inset:0;pointer-events:none';viewport.prepend(surface);
const colours=[0x75977b,0xb89961,0x8299b9,0xbb8c79,0x9a8dac];
function polygon(g,points,colour,alpha=1){g.fillStyle(colour,alpha);g.fillPoints(points,true);}
function tile(g,a,b,w,d,c,z=0,alpha=1){polygon(g,[iso(a,b,z),iso(a+w,b,z),iso(a+w,b+d,z),iso(a,b+d,z)],c,alpha);}
function box(g,a,b,w,d,h,c,base=0){polygon(g,[iso(a+w,b,h+base),iso(a+w,b+d,h+base),iso(a+w,b+d,base),iso(a+w,b,base)],Phaser.Display.Color.ValueToColor(c).darken(23).color);polygon(g,[iso(a,b+d,h+base),iso(a+w,b+d,h+base),iso(a+w,b+d,base),iso(a,b+d,base)],Phaser.Display.Color.ValueToColor(c).darken(9).color);tile(g,a,b,w,d,c,h+base);}
function front(g,a,b,w,h,z,c){polygon(g,[iso(a,b,z),iso(a+w,b,z),iso(a+w,b,z+h),iso(a,b,z+h)],c);}
function plant(scene,a,b){const g=scene.add.graphics().setDepth(a+b+30),pt=iso(a,b);g.fillStyle(0x3b5139,.09);g.fillEllipse(pt.x+8,pt.y+8,48,19);box(g,a-12,b-12,24,24,28,0xe9e3cf);const q=iso(a,b,33);g.lineStyle(3,0x7e8e61);g.lineBetween(q.x,q.y,q.x-2,q.y-37);for(const [dx,dy,r,c] of [[-12,-18,11,0x809d64],[9,-27,13,0x9bab76],[-4,-41,12,0x6b8958],[15,-8,10,0x879a65],[-16,-3,9,0xa4b481]]){g.fillStyle(c);g.fillEllipse(q.x+dx,q.y+dy,r*1.5,r);}return g;}
// Project each video thumbnail onto the same inclined plane as its screen.
function addVideoThumbnails(scene,p){
 p.screenImages=[];
 [p.presentation_video,p.demo_video].forEach((id,j)=>{
  if(!/^[A-Za-z0-9_-]{11}$/.test(id||''))return;
  const photo=new Image();photo.crossOrigin='anonymous';
  photo.onload=()=>{
   if(!scene.sys.isActive())return;
   const key='video-screen-'+p.id+'-'+j,texture=scene.textures.createCanvas(key,56,87),context=texture.context;
   context.setTransform(.68,.34,0,1,0,0);context.drawImage(photo,0,0,photo.width,photo.height,0,0,79,58);
   context.fillStyle='rgba(0,0,0,.32)';context.fillRect(0,40,79,18);context.fillStyle='#fff';context.font='8px Arial';context.textAlign='center';context.fillText(j?'DEMO':'PRESENTATION',39.5,52);texture.refresh();
   const pt=iso(p.x+33+j*90,p.y+30,100),image=scene.add.image(pt.x,pt.y,key).setOrigin(0).setDepth(p.x+p.y+235.5);p.screenImages.push(image);
  };
  photo.src='https://i.ytimg.com/vi/'+id+'/mqdefault.jpg';
 });
}
const game=new Phaser.Game({type:Phaser.CANVAS,parent:surface,width:viewport.clientWidth,height:viewport.clientHeight,resolution:Math.min(window.devicePixelRatio||1,2),backgroundColor:'#e9ede5',banner:false,audio:{noAudio:true},scene:{create(){sceneRef=this;const g=this.add.graphics().setDepth(-1000);
// Limestone floor: low-contrast joints, timber edging and soft ambient shadows.
tile(g,-16,-16,width+32,height+32,0xc1c8b6,-20);tile(g,0,0,width,height,0xe9e6d9);for(let yy=0;yy<height;yy+=120)for(let xx=0;xx<width;xx+=120)tile(g,xx+1,yy+1,118,118,(xx/120+yy/120)%3===0?0xf2efe5:0xedece2);
tile(g,0,0,16,height,0xb9ad8f,2);tile(g,width-16,0,16,height,0xb9ad8f,2);tile(g,16,0,width-32,12,0xb9ad8f,2);
for(let z=0;z<Math.ceil(lastNumber/10);z++){const top=290+z*zoneSpacing,accent=colours[z%5];tile(g,35,top,width-70,790,[0xdce4cf,0xece1c8,0xdce4ea,0xebdcd2,0xe6dfee][z%5]);tile(g,35,top,width-70,5,accent);tile(g,35,top+785,width-70,5,accent);for(let a=55;a<width-55;a+=38)tile(g,a,top+777,18,2,0xffffff,0,.5);
// Sculptural zone sign and plants frame the aisle without blocking its route.
const sign=iso(95,top-40);this.add.text(sign.x,sign.y,String.fromCharCode(65+z)+'  /  '+['DISCOVERY','IDEAS','EXPERIMENTS','POSSIBILITIES','HORIZONS'][z%5],{fontSize:'17px',fontFamily:'Arial',fontStyle:'bold',color:'#68775e',letterSpacing:2}).setOrigin(0,.5).setDepth(-900);plant(this,35,top-50);plant(this,width-35,top-50);}

data.forEach((p,i)=>{const z=Math.floor((p.number-1)/10)%5,c=colours[z],bg=this.add.graphics().setDepth(p.x+p.y+235);p.artwork=bg;tile(g,p.x+18,p.y+25,245,145,0x58694a,0,.09);tile(g,p.x+10,p.y+18,240,145,0x58694a,0,.06);
// Open low plinth, slim frame and two independent screens, instead of solid blocks.
box(bg,p.x,p.y,235,145,13,0xe9e2cd);box(bg,p.x+8,p.y+8,219,129,5,0xfaf7eb,13);box(bg,p.x+18,p.y+14,199,14,99,c,18);front(bg,p.x+27,p.y+29,181,75,34,0x2f4f44);
for(let j=0;j<2;j++){const a=p.x+33+j*90,b=p.y+30;front(bg,a,b,79,58,42,j?0x8ea899:0xb6c7aa);front(bg,a+4,b+.3,71,3,45,j?0x749485:0x9bb690);const pt=iso(a+36,b+.5,73);polygon(bg,[{x:pt.x-4,y:pt.y-6},{x:pt.x+5,y:pt.y},{x:pt.x-4,y:pt.y+6}],0xfaf9e9);}
box(bg,p.x+43,p.y+94,149,30,18,0xc9b58d,18);box(bg,p.x+46,p.y+96,143,26,3,0xfaf6e8,36);const plaque=iso(p.x+118,p.y+110,40);this.add.text(plaque.x,plaque.y,p.code,{fontSize:'14px',color:'#8e7750',fontFamily:'Arial',fontStyle:'bold'}).setOrigin(.5).setDepth(p.x+p.y+236);
addVideoThumbnails(this,p);
});
const shadow=this.add.ellipse(0,4,42,17,0x425134,.15),ring=this.add.ellipse(0,4,52,24).setStrokeStyle(1.5,0xc8ae6a,.8);// Each shoe shares its leg's local transform so the ankle stays connected throughout the stride.
legLeft=this.add.container(-6,-10,[this.add.rectangle(0,0,8,20,0x435349),this.add.ellipse(0,9,12,6,0xeee8d3)]);legRight=this.add.container(6,-10,[this.add.rectangle(0,0,8,20,0x435349),this.add.ellipse(0,9,12,6,0xeee8d3)]);armLeft=this.add.rectangle(-16,-29,7,25,0xdca966).setOrigin(.5,.15);armRight=this.add.rectangle(16,-29,7,25,0xdca966).setOrigin(.5,.15);const body=this.add.graphics();body.fillStyle(0xe7b873);body.fillRoundedRect(-13,-44,26,32,7);body.fillStyle(0xf5d598);body.fillRoundedRect(-5,-39,10,24,3);const head=this.add.circle(0,-54,12,0xf1c7a0),hair=this.add.graphics();hair.fillStyle(0x4e4a3a);hair.fillRoundedRect(-12,-66,24,12,6);hair.fillStyle(0x4e4a3a);hair.fillRect(-12,-57,5,7);const you=this.add.text(0,21,'YOU',{fontSize:'9px',fontFamily:'Arial',color:'#57734d',letterSpacing:2,backgroundColor:'#faf9eb',padding:{x:5,y:3}}).setOrigin(.5);
character=this.add.container(0,0,[shadow,ring,legLeft,legRight,armLeft,armRight,body,head,hair,you]);$('scene-status').textContent='';viewport.dataset.ready='true';},update(time){tick(time);}}});
new ResizeObserver(()=>{if(sceneRef)game.scale.resize(viewport.clientWidth,viewport.clientHeight);}).observe(viewport);
function navigate(tx,ty){message.textContent='';const step=40,cols=Math.ceil(width/step),rows=Math.ceil(height/step),cell=(a,b)=>b*cols+a;const sx=Math.floor(x/step),sy=Math.floor(y/step),ex=Math.floor(tx/step),ey=Math.floor(ty/step);if(blocked(tx,ty))return;let queue=[[sx,sy]],index=0,prev=new Map([[cell(sx,sy),null]]),end=null;while(index<queue.length){const [a,b]=queue[index++];if(a===ex&&b===ey){end=cell(a,b);break;}for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){const na=a+dx,nb=b+dy,k=cell(na,nb);if(na<0||nb<0||na>=cols||nb>=rows||prev.has(k)||blocked(na*step+20,nb*step+20))continue;prev.set(k,cell(a,b));queue.push([na,nb]);}}
route=[];target=null;if(end===null){message.textContent='That spot is blocked. Click an open aisle or use Take me there.';return;}while(prev.get(end)!==null){route.push({x:(end%cols)*step+20,y:Math.floor(end/cols)*step+20});end=prev.get(end);}route.reverse();}
$('entrance').onclick=()=>{x=1150;y=610;route=[];target=null;keys.clear();viewport.focus();};
$('open-near').onclick=()=>near&&open(near);
const zones=Array.from({length:Math.ceil(lastNumber/10)},(_,i)=>({letter:String.fromCharCode(65+i),name:['Discovery','Ideas','Experiments','Possibilities','Horizons'][i%5],count:data.filter(p=>Math.floor((p.number-1)/10)===i).length}));let activeZone=-1;
zones.forEach((z,i)=>{const b=document.createElement('button');b.type='button';b.className='zone-link';b.style.setProperty('--zone-tint',['#e1ead6','#e9dfca','#dce4ef','#ebddd6','#e5dfec'][i%5]);const letter=document.createElement('b');letter.textContent=z.letter;const name=document.createElement('span');name.textContent=z.name;const count=document.createElement('small');count.textContent=z.count+'  ↗';b.append(letter,name,count);b.onclick=()=>{x=1150;y=610+i*zoneSpacing;keys.clear();route=[];target=null;viewport.focus();};$('zone-list').append(b);z.button=b;});
function updateZone(){const z=zones[activeZone];$('zone-letter').textContent=z?.letter||'—';$('zone-name').textContent=z?.name||'Entrance';zones.forEach((z,i)=>z.button.setAttribute('aria-current',String(i===activeZone)));}
function showTab(which){for(const id of ['explore','ballot']){const on=id===which;$(id+'-panel').hidden=!on;$(id+'-tab').setAttribute('aria-selected',String(on));$(id+'-tab').tabIndex=on?0:-1;}}
for(const id of ['explore','ballot']){$(id+'-tab').onclick=()=>showTab(id);$(id+'-tab').onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();e.stopPropagation();const next=e.key==='Home'?'explore':e.key==='End'?'ballot':id==='explore'?'ballot':'explore';showTab(next);$(next+'-tab').focus();}};}
function setZoom(value){zoom=Math.max(.6,Math.min(1.15,Math.round(value*100)/100));$('zoom-value').value=Math.round(zoom*100)+'%';$('zoom-out').disabled=zoom<=.6;$('zoom-in').disabled=zoom>=1.15;}
$('zoom-in').onclick=()=>setZoom(zoom+.1);$('zoom-out').onclick=()=>setZoom(zoom-.1);
$('expand-hall').hidden=!viewport.requestFullscreen;$('expand-hall').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await viewport.requestFullscreen();}catch{message.textContent='Full screen is unavailable in this browser.';}};

if($('hall-ballot'))$('hall-ballot').addEventListener('submit',()=>dirty=false);window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
})();