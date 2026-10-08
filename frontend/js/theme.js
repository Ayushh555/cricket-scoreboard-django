(function(){
  var t=null;
  try{t=localStorage.getItem('crease-theme')}catch(e){}
  if(t!=='light'&&t!=='dark')t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
  document.documentElement.dataset.theme=t;
})();

// Pages that need a login stay hidden until we know who is looking, so a visitor never sees a flash of the home page.
(function(){
  var p=location.pathname;
  var gated=/\/(index|history|teams|stats|new)\.html$/.test(p)||/\/$/.test(p)||(/\/match\.html$/.test(p)&&/mode=score/.test(location.search));
  if(gated)document.documentElement.classList.add('gate');
})();
