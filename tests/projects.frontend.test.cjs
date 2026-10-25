const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname,'..');

function setup(role='admin',status='draft',own=true) {
  const elements=new Map(),listeners=new Map(),calls=[],messages=[];
  let failSubmit=false;
  let item={id:'project-1',institution_id:'institution-1',institution_name:'Universidad de prueba',institution_code:'UP',institution_active:true,
    status,version:1,revision:1,last_editor_id:own ? 'user-1' : 'another-person',published_revision:status === 'validated' ? 1 : null,
    review_note:status === 'returned' ? 'Precise las referencias y los resultados.' : '',events:[],updated_at:'2026-10-24T12:00:00Z',
    data:{title:'Proyecto científico de prueba',code:'SCI-01',institution_id:'institution-1',lead:'Responsable de prueba',description:'Descripción de la investigación para revisar los resultados.',classification:'Investigación',objectives:['B6'],implementation_status:'Piloto',start_date:'',end_date:'',participants:'',evidence:[]}};
  const element = key => {if (!elements.has(key)) elements.set(key,{innerHTML:'',textContent:'',value:'',disabled:false,hidden:false,open:false,classList:{remove(){}},setAttribute(){},addEventListener(){},scrollIntoView(){},showModal(){this.open=true;},close(){this.open=false;},insertAdjacentHTML(position,html){this.innerHTML+=html;}});return elements.get(key);};
  const context=vm.createContext({document:{querySelector:element,querySelectorAll:()=>[],addEventListener(type,listener){if (!listeners.has(type)) listeners.set(type,[]);listeners.get(type).push(listener);}},window:{addEventListener(){},scrollTo(){}},location:{hash:'#admin'},URLSearchParams,Intl,
    FormData:class {constructor(form){this.values=form.values;}get(key){const v=this.values[key];return Array.isArray(v) ? v[0] : v ?? null;}getAll(key){const v=this.values[key];return v == null ? [] : Array.isArray(v) ? v : [v];}}
  });
  vm.runInContext(fs.readFileSync(path.join(root,'web/app.js'),'utf8').replace(/initialize\(\);\s*$/,''),context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/projects.js'),'utf8'),context);
  vm.runInContext("state.overview={institution_registry:[{id:'institution-1',code:'UP',name:'Universidad de prueba',active:true}]};",context);
  const config={user:{id:'user-1',role,institution_id:role === 'coordinator' ? 'institution-1' : null},isCurrent:()=>true,onChange:async message=>{messages.push(message);},request:async(url,method='GET',data)=>{
    calls.push({url,method,data});
    if (method==='GET' && url.includes('?')) return {items:[item],page:1,total:1,limit:15,counts:{draft:1,submitted:0,returned:0,validated:0}};
    if (method==='GET') return item;
    if (url.endsWith('/submit')) {if (failSubmit) throw new Error('Complete el responsable antes de enviar.');item={...item,status:'submitted',version:item.version+1};return item;}
    if (url.endsWith('/return')) {item={...item,status:'returned',version:item.version+1};return item;}
    if (url.endsWith('/validate')) {item={...item,status:'validated',published_revision:item.revision,version:item.version+1};return item;}
    if (url.endsWith('/withdraw') || url.endsWith('/reopen')) {item={...item,status:'draft',version:item.version+1};return item;}
    item={...item,id:item.id,data,status:'draft',version:item.version+1};return item;
  }};
  context.config=config;
  async function click(dataset={},attributes=[]) {const button={dataset,disabled:false,hasAttribute:name=>attributes.includes(name)};for (const f of listeners.get('click')) await f({target:{closest:()=>button}});}
  async function submit(values,intent='draft',reviewAction='') {
    const button={disabled:false},error=element('#form-error');
    const form={id:reviewAction ? 'project-review-form' : 'project-form',dataset:{action:reviewAction},values,
      querySelector:()=>error,querySelectorAll:selector=>selector==='[type="submit"]' ? [button] : []};
    for (const f of listeners.get('submit')) await f({target:form,submitter:{value:intent},preventDefault(){}});
    return error;
  }
  return {run:code=>vm.runInContext(code,context),element,calls,messages,click,submit,setFailSubmit:value=>{failSubmit=value;}};
}

test('Project management has counters, search and institution-scoped creation controls',async()=>{
  const t=setup('coordinator');await t.run('ProjectUI.render(config)');
  const html=t.element('#admin-content').innerHTML;
  assert.ok(html.includes('Nuevo proyecto'));
  assert.ok(html.includes('En revisión'));
  assert.ok(!html.includes('id="project-filter-institution"'));
  await t.click({},['data-new-project']);
  assert.ok(t.element('#detail-body').innerHTML.includes('Guardar y enviar a revisión'));
  assert.match(t.element('#detail-body').innerHTML,/id="project-institution_id"[^>]+disabled/);
});

test('Reviewer can review submitted projects but cannot edit data',async()=>{
  const t=setup('reviewer','submitted',false);await t.run('ProjectUI.render(config)');
  assert.ok(!t.element('#admin-content').innerHTML.includes('data-new-project'));
  await t.click({openProject:'project-1'});
  const html=t.element('#detail-body').innerHTML;
  assert.match(html,/id="project-title"[^>]+disabled/);
  assert.ok(!html.includes('Guardar borrador'));
  assert.ok(html.includes('data-project-review="validate"'));
  assert.ok(html.includes('data-project-review="return"'));
});

test('Author cannot approve their own project; validated projects can open a revision',async()=>{
  const author=setup('admin','submitted',true);await author.run('ProjectUI.render(config)');await author.click({openProject:'project-1'});
  assert.ok(!author.element('#detail-body').innerHTML.includes('data-project-review="validate"'));
  assert.ok(author.element('#detail-body').innerHTML.includes('Retirar envío'));
  const validated=setup('coordinator','validated');await validated.run('ProjectUI.render(config)');await validated.click({openProject:'project-1'});
  assert.ok(validated.element('#detail-body').innerHTML.includes('Preparar nueva versión'));
  assert.ok(!validated.element('#detail-body').innerHTML.includes('Guardar borrador'));
});

test('Save and submit sends only editable fields then uses the saved version',async()=>{
  const t=setup();await t.run('ProjectUI.render(config)');await t.click({openProject:'project-1'});
  await t.submit({title:'Título revisado',code:'SCI-01',lead:'Responsable',description:'Descripción científica ampliada para la revisión.',classification:'Ciencia',implementation_status:'Piloto',start_date:'',end_date:'',participants:'',objectives:['B1','B6']},'submit');
  const mutations=t.calls.filter(c=>c.method!=='GET');
  assert.equal(mutations[0].method,'PATCH');
  assert.equal(mutations[0].data.version,1);
  assert.equal(mutations[0].data.institution_id,'institution-1');
  assert.deepEqual(Array.from(mutations[0].data.objectives),['B1','B6']);
  assert.ok(!('status' in mutations[0].data));
  assert.ok(mutations[1].url.endsWith('/submit'));
  assert.equal(mutations[1].data.version,2);
  assert.ok(t.messages.includes('Proyecto enviado a revisión.'));
});

test('Failed submission retains saved identity and version for a safe retry',async()=>{
  const t=setup('coordinator');await t.run('ProjectUI.render(config)');await t.click({},['data-new-project']);t.setFailSubmit(true);
  const values={title:'Nuevo proyecto',code:'NEW-01',description:'Borrador todavía incompleto.',implementation_status:'Por precisar',objectives:[]};
  const error=await t.submit(values,'submit');
  assert.ok(error.textContent.includes('El borrador se guardó.'));
  assert.ok(t.element('#detail').open);
  await t.submit(values,'draft');
  const mutations=t.calls.filter(c=>c.method!=='GET' && !c.url.endsWith('/submit'));
  assert.equal(mutations[0].method,'POST');
  assert.equal(mutations[1].method,'PATCH');
  assert.equal(mutations[1].data.version,2);
});

test('Return form requires an observation and sends it with the review version',async()=>{
  const t=setup('reviewer','submitted',false);await t.run('ProjectUI.render(config)');await t.click({openProject:'project-1'});await t.click({projectReview:'return'});
  assert.ok(t.element('#detail-body').innerHTML.includes('required minlength="10"'));
  await t.submit({note:'Precise la metodología y complete las referencias.'},'','return');
  const action=t.calls.find(c=>c.url.endsWith('/return'));
  assert.equal(action.data.version,1);
  assert.equal(action.data.note,'Precise la metodología y complete las referencias.');
});
