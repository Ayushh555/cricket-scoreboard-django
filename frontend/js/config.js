// Same-origin by default: Django serves this folder, so the API is on the same address.
// Hosting the frontend separately? Set the backend address, e.g. 'http://127.0.0.1:8000'
// (and enable CORS on the backend).
const API_BASE = '';

// Two-tap "End match": first tap arms the button, second tap ends the live match.
function endButton(id,onDone){
  const b=document.createElement('button');b.type='button';b.className='del';b.textContent='End match';let t;
  b.onclick=async()=>{
    if(!b.classList.contains('armed')){b.classList.add('armed');b.textContent='Tap again to end';
      t=setTimeout(()=>{b.classList.remove('armed');b.textContent='End match'},4000);return}
    clearTimeout(t);b.disabled=true;
    try{const r=await fetch(API_BASE+'/api/matches/'+id+'/end/',{method:'POST'});
      if(!r.ok)throw 0;onDone()}catch(e){b.disabled=false;b.classList.remove('armed');b.textContent='End match'}
  };
  return b;
}
