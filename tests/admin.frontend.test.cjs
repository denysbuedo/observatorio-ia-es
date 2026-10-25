const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname,'..');
const registry = JSON.parse(fs.readFileSync(path.join(root,'data/institutions.json'),'utf8')).map(i=>({...i,id:`inst-${i.code}`,active:true,kind:'Universidad',version:1,contact_name:'',contact_email:'',notes:''}));
const roles = {admin:'Administrador MES',coordinator:'Coordinador institucional',reviewer:'Revisor',reader:'Lector'};
const indicatorRecords=JSON.parse(fs.readFileSync(path.join(root,'data_snapshot.json'),'utf8')).indicators.map((data,n)=>({id:'indicators-'+n,title:data.Indicador,data}));

function setup(role='admin',setupRequired=false) {
  const elements = new Map(), listeners = new Map(), calls = [];
  function element(key) {
    if (!elements.has(key)) elements.set(key,{innerHTML:'',textContent:'',value:'',hidden:false,disabled:false,
      classList:{remove(){}},addEventListener(){},setAttribute(){},showModal(){this.open=true;},close(){this.open=false;},scrollIntoView(){}});
    return elements.get(key);
  }
  const user = role ? {id:'user-1',full_name:'Persona de prueba',username:'prueba',role,institution_id:role === 'coordinator' ? 'inst-UH' : null,active:true,version:1} : null;
  const responses = {
    '/api/auth/session':{user,csrf_token:user ? 'csrf-prueba' : null,setup_required:setupRequired,roles,institution_kinds:['Universidad','Otra entidad']},
    '/api/admin/institutions':{items:role === 'coordinator' ? registry.filter(i=>i.code === 'UH') : registry},
    '/api/admin/users':{items:[user]},
    '/api/admin/audit?page=1':{items:[{id:1,actor_name:'Responsable',action:'Actualizar institución',entity_type:'institution',entity_id:'inst-UH',created_at:'2026-10-24T10:00:00+00:00',before:{notes:'Anterior'},after:{notes:'Actualizada'}}],page:1,limit:20,total:1}
  };
  responses['/api/admin/projects?q=&institution_id=&status=&page=1&limit=15']={items:[],page:1,total:0,limit:15,counts:{draft:0,submitted:0,returned:0,validated:0}};
  responses['/api/dashboard/rules']={items:[]};responses['/api/admin/indicator-rules']={items:[]};responses['/api/records/indicators?limit=100']={items:indicatorRecords};
  for(const kind of ['programs','products','doctorands','measurements'])responses[`/api/admin/${kind}?q=&status=&institution_id=&page=1&limit=15`]={items:[],page:1,total:0,limit:15,counts:{}};
  const context = vm.createContext({document:{querySelector:element,querySelectorAll:()=>[],addEventListener(type,listener){if (!listeners.has(type)) listeners.set(type,[]); listeners.get(type).push(listener);}},
    window:{addEventListener(){},scrollTo(){}},location:{hash:'#admin'}, URLSearchParams,Intl,
    FormData:class {constructor(form){this.values=form.values;} [Symbol.iterator](){return this.values[Symbol.iterator]();} get(key){const v=this.values.find(x=>x[0]===key)?.[1];return Array.isArray(v)?v[0]:v??null;} getAll(key){const v=this.values.find(x=>x[0]===key)?.[1];return v==null?[]:Array.isArray(v)?v:[v];}},
    fetch:async (url,options)=>{calls.push({url,options});if (!(url in responses)) throw new Error(`Unexpected request ${url}`);return {ok:true,status:200,json:async()=>responses[url]};}
  });
  vm.runInContext(fs.readFileSync(path.join(root,'web/app.js'),'utf8').replace(/initialize\(\);\s*$/,''),context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/projects.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/registry.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/dashboard.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/admin.js'),'utf8'),context);
  context.registry = registry;
  vm.runInContext(`state.section='admin'; state.request=1; state.overview={institution_registry:registry,institutions:Object.fromEntries(registry.map(i=>[i.code,i.name]))};`,context);
  async function click(dataset,attributes=[]) {
    const button = {dataset,hasAttribute:name=>attributes.includes(name)};
    for (const listener of listeners.get('click')) await listener({target:{closest:()=>button}});
  }
  async function submit(id,values,intent='draft',extra={}) {
    const button = {disabled:false};
    const error = element('#form-error');
    const form = {id,values:Object.entries(values),dataset:extra,querySelector:selector=>selector === '[type="submit"]' ? button : error,querySelectorAll:selector=>selector==='[type="submit"]'?[button]:[]};
    for (const listener of listeners.get('submit')) await listener({target:form,submitter:{value:intent},preventDefault(){}});
    return error;
  }
  responses['/api/overview'] = {institution_registry:registry,institutions:Object.fromEntries(registry.map(i=>[i.code,i.name]))};
  return {run:code=>vm.runInContext(code,context),element,calls,click,submit,responses};
}

test('Initial setup and login provide real credential forms without defaults', async()=>{
  const initial = setup(null,true);
  await initial.run('Admin.render()');
  const html = initial.element('#content').innerHTML;
  assert.ok(html.includes('Configurar la primera cuenta'));
  assert.ok(html.includes('confirm_password'));
  assert.ok(html.includes('minlength="12"'));
  const login = setup(null,false);
  await login.run('Admin.render()');
  assert.ok(login.element('#content').innerHTML.includes('Iniciar sesión'));
  assert.ok(!login.element('#content').innerHTML.includes('confirm_password'));
});

test('Administrator can open institution and user management forms', async()=>{
  const t = setup();
  await t.run('Admin.render()');
  assert.ok(t.element('#content').innerHTML.includes('Usuarios y permisos'));
  assert.ok(t.element('#admin-content').innerHTML.includes('Nueva institución'));
  await t.click({},['data-new-institution']);
  assert.ok(t.element('#detail-body').innerHTML.includes('institution-form'));
  assert.ok(t.element('#detail').open);
  await t.click({adminTab:'users'});
  assert.ok(t.element('#admin-content').innerHTML.includes('Nuevo usuario'));
  await t.click({},['data-new-user']);
  assert.ok(t.element('#detail-body').innerHTML.includes('Contraseña inicial'));
  assert.ok(t.element('#detail-body').innerHTML.includes('Institución asignada'));
});

test('Coordinator sees only their institution and cannot edit official metadata', async()=>{
  const t = setup('coordinator');
  await t.run('Admin.render()');
  assert.ok(!t.element('#content').innerHTML.includes('Usuarios y permisos'));
  assert.ok(!t.element('#admin-content').innerHTML.includes('Nueva institución'));
  await t.click({editInstitution:'inst-UH'});
  const html = t.element('#detail-body').innerHTML;
  assert.match(html,/id="admin-name"[^>]+disabled/);
  assert.match(html,/id="admin-province"[^>]+disabled/);
  assert.ok(!/id="admin-contact_name"[^>]+disabled/.test(html));
  assert.ok(!t.calls.some(c=>c.url === '/api/admin/users'));
});

test('Reviewer has read-only forms; reader has only account controls', async()=>{
  const reviewer = setup('reviewer');
  await reviewer.run('Admin.render()');
  await reviewer.click({editInstitution:'inst-UH'});
  const html = reviewer.element('#detail-body').innerHTML;
  assert.ok(html.includes('Ficha de institución'));
  assert.match(html,/id="admin-contact_name"[^>]+disabled/);
  assert.ok(!html.includes('type="submit"'));
  const reader = setup('reader');
  await reader.run('Admin.render()');
  assert.ok(!reader.element('#content').innerHTML.includes('data-admin-tab="institutions"'));
  assert.ok(reader.element('#admin-content').innerHTML.includes('Cambiar mi contraseña'));
  assert.ok(!reader.calls.some(c=>c.url.startsWith('/api/admin/')));
});

test('Audit details show old and new values with named actor', async()=>{
  const t = setup();
  await t.run('Admin.render()');
  await t.click({adminTab:'audit'});
  assert.ok(t.element('#admin-content').innerHTML.includes('Responsable'));
  await t.click({audit:'1'});
  const html = t.element('#detail-body').innerHTML;
  assert.ok(html.includes('Anterior'));
  assert.ok(html.includes('Actualizada'));
  assert.ok(html.includes('Notas'));
});

test('Institution save sends boolean state, aliases, version and CSRF to backend', async()=>{
  const t = setup();
  await t.run('Admin.render()');
  await t.click({editInstitution:'inst-UH'});
  t.responses['/api/admin/institutions/inst-UH'] = {id:'inst-UH'};
  const error = await t.submit('institution-form',{name:'Nombre corregido',province:'La Habana',kind:'Universidad',active:'false',aliases:'Alias uno\nAlias dos',contact_name:'Persona',contact_email:'persona@example.org',notes:'Nota de gestión'});
  const request = t.calls.find(c=>c.url === '/api/admin/institutions/inst-UH');
  assert.ok(request,error.textContent);
  const payload = JSON.parse(request.options.body);
  assert.equal(request.options.method,'PATCH');
  assert.equal(request.options.headers['X-CSRF-Token'],'csrf-prueba');
  assert.equal(payload.active,false);
  assert.equal(payload.version,1);
  assert.equal(payload.code,'UH');
  assert.deepEqual(payload.aliases,['Alias uno','Alias dos']);
  assert.ok(!('id' in payload));
});

test('Coordinator contact save keeps official data unchanged', async()=>{
  const t = setup('coordinator');
  await t.run('Admin.render()');
  await t.click({editInstitution:'inst-UH'});
  t.responses['/api/admin/institutions/inst-UH'] = {id:'inst-UH'};
  await t.submit('institution-form',{contact_name:'Contacto actualizado',contact_email:'coordinador@example.org',notes:'Nota institucional'});
  const payload = JSON.parse(t.calls.find(c=>c.url === '/api/admin/institutions/inst-UH').options.body);
  const original = registry.find(i=>i.code === 'UH');
  assert.equal(payload.name,original.name);
  assert.equal(payload.province,original.province);
  assert.equal(payload.active,true);
  assert.equal(payload.contact_name,'Contacto actualizado');
  assert.deepEqual(payload.aliases,original.aliases);
});

test('Project tab is connected to authenticated administration and hidden for readers',async()=>{
  const admin=setup('admin');await admin.run('Admin.render()');
  assert.ok(admin.element('#content').innerHTML.includes('data-admin-tab="projects"'));
  await admin.click({adminTab:'projects'});
  assert.ok(admin.element('#admin-content').innerHTML.includes('Proyectos institucionales'));
  assert.ok(admin.element('#admin-content').innerHTML.includes('Nuevo proyecto'));
  const reader=setup('reader');await reader.run('Admin.render()');
  assert.ok(!reader.element('#content').innerHTML.includes('data-admin-tab="projects"'));
});

test('All catalogue and measurement tabs are connected, and only MES sees rule controls',async()=>{
  const admin=setup();await admin.run('Admin.render()');
  for(const kind of ['programs','products','doctorands','measurements','rules']){
    assert.ok(admin.element('#content').innerHTML.includes(`data-admin-tab="${kind}"`));
    await admin.click({adminTab:kind});
    assert.ok(!admin.element('#admin-content').innerHTML.includes('error'));
  }
  const coordinator=setup('coordinator');await coordinator.run('Admin.render()');
  assert.ok(!coordinator.element('#content').innerHTML.includes('data-admin-tab="rules"'));
  const reader=setup('reader');await reader.run('Admin.render()');
  assert.ok(!reader.element('#content').innerHTML.includes('data-admin-tab="measurements"'));
});

test('Training draft preserves pending IA relationship, numeric hours and typed links',async()=>{
  const t=setup();await t.run('Admin.render()');await t.click({adminTab:'programs'});await t.click({},['data-entry-new']);
  assert.ok(t.element('#detail-body').innerHTML.includes('Vínculo IA por confirmar'));
  t.responses['/api/admin/programs']={id:'new-program',kind:'programs',institution_id:'inst-UH',status:'draft',version:1};
  const error=await t.submit('entry-form',{institution_id:'inst-UH',title:'Programa de prueba',code:'P-01',lead:'Coordinador',description:'Descripción académica de la formación.',training_type:'Doctorado',modality:'Híbrida',ia_relation:'pending',hours:'120',start_date:'',end_date:'',objectives:['B6'],project_ids:['project-id'],program_ids:[]});
  const request=t.calls.find(c=>c.url==='/api/admin/programs');assert.ok(request,error.textContent);
  const body=JSON.parse(request.options.body);assert.equal(body.hours,120);assert.equal(body.ia_relation,'pending');assert.deepEqual(body.project_ids,['project-id']);
});

test('Measurement form sends zero as a number rather than a missing value',async()=>{
  const t=setup('coordinator');await t.run('Admin.render()');await t.click({adminTab:'measurements'});await t.click({},['data-entry-new']);
  t.responses['/api/admin/measurements']={id:'measurement-1',kind:'measurements',institution_id:'inst-UH',status:'draft',version:1};
  const error=await t.submit('entry-form',{indicator_code:'I06',method:'direct',value:'0',start_date:'2026-01-01',end_date:'2026-12-31',description:'Registro institucional comprobado.'});
  const request=t.calls.find(c=>c.url==='/api/admin/measurements');assert.ok(request,error.textContent);
  const body=JSON.parse(request.options.body);assert.equal(body.value,0);assert.equal(body.numerator,null);assert.equal(body.denominator,null);assert.equal(body.institution_id,'inst-UH');
});

test('MES rule form keeps empty numerical targets and thresholds as null',async()=>{
  const t=setup();await t.run('Admin.render()');await t.click({adminTab:'rules'});await t.click({},['data-rule-new']);
  t.responses['/api/admin/indicator-rules']={items:[]};
  const error=await t.submit('rule-form',{indicator_code:'I06',institution_id:'',start_date:'',end_date:'',method:'direct',direction:'',baseline:'',target:'',good_threshold:'',warning_threshold:'',definition:'Conteo verificable de pilotos institucionales.'});
  const request=t.calls.find(c=>c.url==='/api/admin/indicator-rules'&&c.options.method==='POST');assert.ok(request,error.textContent);
  const body=JSON.parse(request.options.body);assert.equal(body.target,null);assert.equal(body.baseline,null);assert.equal(body.good_threshold,null);
});

function boardFixture(){return {items:indicatorRecords.map(i=>({code:i.data.Código,definition:i.data,observations:[],history:[],coverage:0,value:null,target:null,achievement:null,delta:null,signal:'missing'})),periods:[],selected_period:{start_date:'',end_date:''},institutions_reporting:0,validated_observations:0,notice:'Solo valores validados.'};}

test('Dashboard shows zero, missing observations and national breakdown without invented averages',async()=>{
  const t=setup();const board=boardFixture();board.items[0]={...board.items[0],coverage:1,value:0,signal:'unconfigured'};board.items[1]={...board.items[1],coverage:2,signal:'multiple'};
  t.responses['/api/dashboard?institution_id=']=board;t.run("state.section='indicators'");await t.run('DashboardUI.render()');
  const html=t.element('#dashboard-results').innerHTML;assert.ok(html.includes('0 %'));assert.ok(html.includes('2 instituciones · ver desglose'));assert.ok(html.includes('Sin medición'));assert.ok(html.includes('Cumplimiento no calculable'));
  await t.click({dashboardPerspective:'sustainability'});assert.ok(t.element('#dashboard-results').innerHTML.includes('4 indicadores'));
});

test('Validated dashboard history renders comparable series and evidence without review notes',async()=>{
  const t=setup();const board=boardFixture();const m={institution_id:'inst-UH',institution_name:'Universidad de La Habana',method:'direct',cadence:'annual',unit:'%',revision:1,evidence:[{title:'Informe validado',reference:'Referencia verificable',url:''}],rule_snapshot:null,achievement:null,signal:'unconfigured'};
  board.items[0].history=[{...m,start_date:'2025-01-01',end_date:'2025-12-31',value:10},{...m,start_date:'2026-01-01',end_date:'2026-12-31',value:0}];
  t.responses['/api/dashboard?institution_id=']=board;t.run("state.section='indicators'");await t.run('DashboardUI.render()');await t.click({dashboardDetail:'I01'});
  const html=t.element('#detail-body').innerHTML;assert.ok(html.includes('<svg'));assert.ok(html.includes('Informe validado'));assert.ok(html.includes('2025-12-31'));assert.ok(!html.includes('review_note'));
});
