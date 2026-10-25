const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const snapshot = JSON.parse(fs.readFileSync(path.join(root, 'data_snapshot.json'), 'utf8'));
const registry = JSON.parse(fs.readFileSync(path.join(root, 'data/institutions.json'), 'utf8'));

function setup() {
  const elements = new Map();
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, {innerHTML:'', textContent:'', value:'', classList:{remove(){}}, addEventListener(){}, setAttribute(){}});
    return elements.get(selector);
  }
  const context = vm.createContext({
    document:{querySelector:element, querySelectorAll:()=>[], addEventListener(){}},
    window:{addEventListener(){},scrollTo(){}}, location:{hash:''}, URLSearchParams,
    fetch: async () => { throw new Error('Unexpected request'); }
  });
  const source = fs.readFileSync(path.join(root,'web/app.js'), 'utf8').replace(/initialize\(\);\s*$/, '');
  vm.runInContext(source, context);
  context.registryFixture = registry;
  context.indicatorFixture = snapshot.indicators.map((data,index)=>({id:`indicators-${index+1}`,title:data.Indicador,data}));
  vm.runInContext(`state.overview = {institutions:Object.fromEntries(registryFixture.map(x=>[x.code,x.name])),institution_registry:registryFixture}; state.indicators = indicatorFixture;`,context);
  return {run: code => vm.runInContext(code, context), element, context};
}

test('All 35 indicators belong to exactly one perspective',()=>{
  const {run} = setup();
  const codes = JSON.parse(run('JSON.stringify(Object.values(perspectives).flatMap(p=>p.codes))'));
  assert.equal(codes.length, 35);
  assert.equal(new Set(codes).size,35);
  assert.deepEqual(codes.sort(), snapshot.indicators.map(x=>x.Código).sort());
});

test('Main record table displays canonical institution and omits technical filename',()=>{
  const {run,context} = setup();
  context.item = {id:'projects-0001',institution:'UCI',title:'Proyecto de prueba',data:snapshot.projects[0]};
  const html = run('table([item], "projects")');
  assert.ok(html.includes('Universidad de Ciencias Informáticas'));
  assert.ok(!html.includes('TABLAS PARA MINISTRO'));
  assert.ok(!html.includes('Fuente / estado'));
});

test('Record detail keeps raw source in collapsed provenance',()=>{
  const {run,context} = setup();
  context.item = {id:'projects-0001',institution:'UCI',title:'Proyecto de prueba',data:snapshot.projects[0]};
  const html = run('recordDetails(item,"projects")');
  const provenanceIndex = html.indexOf('<details class="provenance">');
  assert.ok(provenanceIndex > 0);
  assert.ok(html.indexOf('TABLAS PARA MINISTRO') > provenanceIndex);
  assert.ok(!html.includes('<details class="provenance" open'));
});

test('Canonical aliases and escaped titles are consistent',()=>{
  const {run,context} = setup();
  assert.equal(run('canonicalInstitution("UCf")'),'UCF');
  assert.equal(run('canonicalInstitution("UMoA")'),'UMoa');
  context.item = {id:'projects-0001',institution:'UCI',title:'<img src=x onerror=alert(1)>',data:{}};
  const html = run('table([item],"projects")');
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
});
