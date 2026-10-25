'use strict';
const sections = {
  overview: ['◈', 'Panorama general'], indicators: ['▥', 'Cuadro de mando'], institutions: ['◎', 'Instituciones'],
  ecosystem: ['⊞', 'Investigación y formación'], strategy: ['◇', 'Estrategia B1–B6'],
  governance: ['⌘', 'Gobernanza'], sources: ['▤', 'Fuentes y evidencias'],
  quality: ['✓', 'Calidad de los datos'], admin: ['⚙', 'Administración']
};
const navigationGroups = [
  ['Seguimiento', ['overview', 'indicators']],
  ['Exploración', ['institutions', 'ecosystem']],
  ['Marco estratégico', ['strategy', 'governance']],
  ['Documentación y calidad', ['sources', 'quality']], ['Gestión', ['admin']]
];
const perspectives = {
  learning: {name:'Formación y capacidades', description:'Competencias, docencia y aprendizaje a lo largo de la vida.', codes:['I01','I02','I03','I04','I05','I10','I16','I17','I28','I31','I34']},
  research: {name:'Investigación e impacto', description:'Talento avanzado, innovación y contribución al sistema universitario.', codes:['I06','I11','I12','I13','I14','I15','I18']},
  governance: {name:'Procesos y gobernanza', description:'Adopción responsable, calidad y capacidad de gestión institucional.', codes:['I07','I08','I09','I19','I21','I23','I24','I25','I27','I29','I30','I32','I33']},
  sustainability: {name:'Recursos y sostenibilidad', description:'Soberanía, inversión y sostenibilidad de las capacidades de IA.', codes:['I20','I22','I26','I35']}
};
const kinds = {projects: 'Proyectos', programs: 'Formación', products: 'Productos', doctorands: 'Doctorandos', portfolio: 'Portafolio estratégico'};
const objectives = {
  B1: ['Currículo y competencias', 'Actualizar los planes de estudio e integrar la IA de forma transversal y ética.'],
  B2: ['Enseñanza, aprendizaje y evaluación', 'Perfeccionar los procesos formativos con centralidad humana.'],
  B3: ['Desarrollo profesional docente', 'Preparar al profesorado para integrar la IA con criterio pedagógico.'],
  B4: ['Cultura y alfabetización', 'Desarrollar una comprensión crítica y un uso responsable de la IA.'],
  B5: ['Fundamentos STEM', 'Fortalecer matemáticas, lógica, programación y pensamiento computacional.'],
  B6: ['Formación especializada, ciencia e innovación', 'Desarrollar talento avanzado y capacidades de investigación en IA.']
};
const state = {overview: null, section: 'overview', kind: 'projects', page: 1, q: '', institution: '', mode: 'table', request: 0, board: {perspective:'', objective:'', type:'', q:''}, indicators:[]};
const content = document.querySelector('#content');
const dialog = document.querySelector('#detail');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function canonicalInstitution(code) {
  const normalized = String(code || '').trim().toLocaleLowerCase('es');
  return state.overview.institution_registry?.find(item => [item.code, item.name, ...item.aliases].some(alias => alias.toLocaleLowerCase('es') === normalized))?.code || code;
}
const institutionName = code => state.overview.institutions[canonicalInstitution(code)] || code;
const institutionProvince = code => state.overview.institution_registry?.find(item => item.code === canonicalInstitution(code))?.province || '';
const tag = (label, style = '') => `<span class="tag ${style}">${esc(label)}</span>`;

async function api(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'No se pudo consultar el catálogo. Intente nuevamente.');
  return data;
}
function heading(eyebrow, title, description) {
  return `<div class="page-heading"><div><p class="eyebrow">${esc(eyebrow)}</p><h1>${esc(title)}</h1><p class="intro">${esc(description)}</p></div><div class="edition">EDICIÓN DEL CATÁLOGO<strong>Octubre de 2026</strong>Levantamiento institucional</div></div>`;
}
function notice() { return `<div class="notice"><b aria-hidden="true">ⓘ</b><span>${esc(state.overview.notice)} Las discrepancias se conservan para su conciliación.</span></div>`; }
function sectionTitle(title, subtitle, link = '', target = '') {
  return `<div class="section-title"><div><h2>${esc(title)}</h2>${subtitle ? `<p>${esc(subtitle)}</p>` : ''}</div>${link ? `<a class="text-link" href="#${target}">${esc(link)} →</a>` : ''}</div>`;
}
function sourceTitle(title) {
  if (/TABLAS PARA MINISTRO/i.test(title)) return 'Informe consolidado de capacidades de inteligencia artificial';
  return String(title || '').replace(/\.(docx?|xlsx?|pdf|pptx?)$/i, '').replace(/_/g, ' ');
}
function recordButton(collection, id, label = 'Ver ficha') { return `<button class="link-button" data-record="${esc(id)}" data-collection="${esc(collection)}">${label} ↗</button>`; }
function cards(items, collection) {
  return `<div class="cards">${items.map(item => `<article class="record-card"><div class="card-top">${tag(item.institution || item.data['ID'] || item.data['Código'] || 'MES')}${tag(item.data['Estado evidencia'] || item.data['Estado'] || 'Registro de trabajo', 'neutral')}</div>${item.institution ? `<p class="institution-name">${esc(institutionName(item.institution))}</p>` : ''}<h3>${esc(collection === 'sources' ? sourceTitle(item.title) : item.title)}</h3><p>${esc(item.data['Clasificación de trabajo'] || item.data['Definición'] || item.data['Aporte principal'] || item.data['Línea / relación con IA'] || item.data['Programa doctoral'] || '')}</p><div class="card-bottom"><span class="source">${esc(item.data['Mapeo B1-B6'] || item.data['Objetivo'] || 'Catálogo institucional')}</span>${recordButton(collection, item.id)}</div></article>`).join('')}</div>`;
}
async function overview() {
  const data = state.overview, k = data.kpis;
  const stats = [[`${k.ies_with_info}<small> / ${k.ies_total}</small>`, 'Instituciones', 'Con información sustantiva'], [data.counts.projects, 'Proyectos de investigación', 'Registros integrados'], [data.counts.programs, 'Programas y ofertas', 'Formación relacionada con IA'], [data.counts.doctorands, 'Registros doctorales', 'Talento en formación'], [data.counts.products, 'Productos y resultados', 'Software y otras contribuciones']];
  const classification = Object.entries(data.classifications).sort((a,b) => b[1] - a[1]);
  const max = Math.max(1, ...classification.map(x => x[1]));
  content.innerHTML = heading('Cuba · Sistema de Educación Superior', 'Inteligencia artificial,\nconocimiento y evidencia.', 'Un espacio de consulta para comprender las capacidades, la investigación y la transformación del sistema universitario cubano.') + notice() +
    `<div class="kpi-grid">${stats.map((x,i) => `<div class="kpi"><div class="kpi-index">0${i+1} / CATÁLOGO</div><div class="kpi-number">${x[0]}</div><div class="kpi-label">${x[1]}</div><div class="kpi-caption">${x[2]}</div></div>`).join('')}</div>
    <div class="dashboard-grid"><section class="panel">${sectionTitle('Ámbitos de investigación', 'Distribución de proyectos por clasificación de trabajo')}${classification.map(([label,n]) => `<div class="bar-row"><span>${esc(label.replace(/^. · /,''))}</span><strong>${n}</strong><div class="track"><div class="bar-fill" data-width="${n/max*100}"></div></div></div>`).join('')}<p class="panel-note">Clasificación preliminar sujeta a validación institucional.</p></section>
    <section class="panel">${sectionTitle('Cobertura institucional', 'Disponibilidad de información en el levantamiento')}<div class="coverage-number">${k.ies_with_info}<small> / ${k.ies_total}</small></div><p class="intro">Instituciones y entidades con información sustantiva reportada.</p><div class="coverage-grid" aria-hidden="true">${Array.from({length:k.ies_total}, (_,i) => `<i class="${i >= k.ies_with_info ? 'empty' : ''}"></i>`).join('')}</div><p class="panel-note">${data.quality.length} instituciones presentan observaciones de conciliación. La ausencia de datos no implica ausencia de actividad.</p><a class="text-link" href="#institutions">Consultar instituciones →</a></section></div>
    ${sectionTitle('Explorar la investigación', 'Proyectos del registro institucional', 'Ver todos los proyectos', 'ecosystem')}<div id="featured" class="loading">Consultando proyectos…</div>`;
  document.querySelectorAll('[data-width]').forEach(el => { el.style.width = `${Number(el.dataset.width)}%`; });
  const request = state.request;
  const result = await api('/api/records/projects?limit=3');
  if (request === state.request) document.querySelector('#featured').outerHTML = cards(result.items, 'projects');
}
function filters(withInstitution = true) {
  return `<form class="filters" id="filters"><div class="field search"><label for="query">Buscar en el catálogo</label><input type="search" id="query" name="q" value="${esc(state.q)}" placeholder="Título, tema, autor o palabra clave…"></div>${withInstitution ? `<div class="field"><label for="institution">Institución reportante</label><select id="institution" name="institution"><option value="">Todas las instituciones</option>${Object.entries(state.overview.institutions).map(([code,name]) => `<option value="${esc(code)}" ${code === state.institution ? 'selected' : ''}>${esc(code)} · ${esc(name)}</option>`).join('')}</select></div>` : ''}<button class="button primary" type="submit">Buscar</button><button class="button" type="button" id="reset-filters">Limpiar</button></form>`;
}
function collectionForSection() {
  return {institutions:'summary', ecosystem:state.kind, strategy:'matrix', sources:'sources', indicators:'indicators', quality:'summary'}[state.section];
}
async function collectionResults() {
  const collection = collectionForSection();
  const request = ++state.request;
  const params = new URLSearchParams({page:state.page, limit:12, q:state.q, institution:state.institution});
  const result = await api(`/api/records/${collection}?${params}`);
  if (request !== state.request) return;
  const target = document.querySelector('#results');
  if (!target) return;
  document.querySelector('#announcement').textContent = `${result.total} registros encontrados`;
  target.classList.remove('loading');
  target.innerHTML = `<div class="results-head"><span><strong>${result.total}</strong> registros encontrados</span><span>Orden alfabético · ${esc(state.mode === 'cards' ? 'Fichas' : 'Tabla')}</span></div>` +
    (result.total ? (state.mode === 'cards' && collection !== 'summary' ? cards(result.items, collection) : table(result.items, collection)) : '<div class="empty">No hay registros para esta consulta. Pruebe con otros términos o elimine los filtros.</div>') +
    `<div class="pagination"><span>Página ${result.page} de ${Math.max(1,Math.ceil(result.total/result.limit))}</span><div><button class="button" id="previous" ${result.page <= 1 ? 'disabled' : ''}>← Anterior</button><button class="button" id="next" ${result.page*result.limit >= result.total ? 'disabled' : ''}>Siguiente →</button></div></div>`;
}
function table(items, collection) {
  const summary = collection === 'summary';
  let headers = summary ? ['Institución / entidad','Proyectos¹','Programas¹','Productos¹','Estado de información',''] : ['Registro / título','Institución','Ámbito y estado',''];
  if (collection === 'indicators') headers = ['Indicador / definición','Objetivo / unidad','Periodicidad / línea base',''];
  if (collection === 'sources') headers = ['Documento / fuente','Fecha','Cautela de uso',''];
  if (collection === 'matrix') headers = ['Acción estratégica','Responsable','Prioridad / estado',''];
  return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${items.map(item => {
    const d = item.data;
    let cells;
    if (summary) {
      const value = (a,b) => d[a] !== '' && d[a] != null ? d[a] : (d[b] !== '' && d[b] != null ? d[b] : '—');
      cells = [`<strong>${esc(institutionName(item.institution))}</strong><span class="sub">${esc(item.institution)} · ${esc(institutionProvince(item.institution))}</span>`, value('Proyectos (registros anexo)','Proyectos (declarado)'), value('Programas/ofertas (registros anexo)','Programas (declarado)'), value('Productos (registros anexo)','Productos (declarado)'), tag(d['Observaciones de conciliación'] ? 'Requiere conciliación' : hasData(d) ? 'Reportado' : 'Información insuficiente', d['Observaciones de conciliación'] ? 'warning' : 'neutral')];
    } else if (collection === 'indicators') cells = [`<strong>${esc(d['Código'])} · ${esc(item.title)}</strong><span class="sub">${esc(d['Definición'])}</span>`, `${tag(d['Objetivo'])}<span class="sub">${esc(d['Unidad'])}</span>`, `${esc(d['Periodicidad'])}<span class="sub">Base 2026: ${esc(d['Línea base 2026'])}</span>`];
    else if (collection === 'sources') cells = [`<strong>${esc(d.ID)} · ${esc(sourceTitle(item.title))}</strong><span class="sub">${esc(d['Aporte principal'])}</span>`, esc(d.Fecha), esc(d['Cautela / uso recomendado'])];
    else if (collection === 'matrix') cells = [`<strong>${esc(d.ID)} · ${esc(item.title)}</strong><span class="sub">${esc(d['Línea / objetivo'])}</span>`, esc(d['Responsable principal']), `${tag(d.Prioridad, d.Prioridad === 'Alta' ? 'warning' : 'neutral')}<span class="sub">${esc(d.Estado)}</span>`];
    else cells = [`<strong>${esc(item.title)}</strong><span class="sub">${esc(d['Clasificación de trabajo'] || d['Nombre'] || d['Autor(es)'] || '')}</span>`, `${esc(institutionName(item.institution))}<span class="sub">${esc(item.institution)}</span>`, `${tag(d['Estado evidencia'] || d.Estado || 'Registro de trabajo', 'neutral')}<span class="sub">${esc(d['Mapeo B1-B6'] || d['Tipo de oferta'] || d['Nivel de aplicación'] || '')}</span>`];
    return `<tr>${cells.map(c => `<td>${c}</td>`).join('')}<td>${recordButton(collection,item.id)}</td></tr>`;
  }).join('')}</tbody></table></div>${summary ? '<p class="source">¹ Se muestra el dato del anexo cuando existe; en su ausencia, el declarado. «—» indica ausencia de cifra; cero indica un valor reportado. Consulte la ficha para comparar ambas fuentes.</p>' : ''}`;
}
function hasData(row) { return Object.entries(row).some(([key,value]) => /declarado|registros anexo/.test(key) && value !== '' && value != null); }
function listPage() {
  const descriptions = {
    institutions:['Capacidades del sistema', 'Instituciones y entidades', 'Información institucional, capacidades reportadas y diferencias entre los resúmenes y sus anexos.'],
    ecosystem:['Catálogo de iniciativas', 'Investigación y formación', 'Explore proyectos, programas, resultados y talento. Cada registro conserva la información y la fuente de su reporte.'],
    sources:['Trazabilidad del conocimiento', 'Fuentes y evidencias', 'Inventario de las fuentes referenciadas en la matriz de trabajo. Las fichas describen su aporte y sus cautelas; no equivalen a documentos completos disponibles.'],
    indicators:['Marco de seguimiento', 'Indicadores', 'Definiciones, responsables y metas propuestas. Este catálogo presenta el marco de medición; no atribuye valores observados a indicadores sin línea base.'],
    strategy:['Estrategia nacional · Eje B', 'Capital humano y transformación', 'Objetivos B1–B6, acciones estratégicas y responsabilidades propuestas para la Educación Superior.' ]
  };
  content.innerHTML = heading(...descriptions[state.section]) + (['institutions','ecosystem'].includes(state.section) ? notice() : '') +
    (state.section === 'ecosystem' ? `<div class="tabs" role="tablist" aria-label="Tipos de registro">${Object.entries(kinds).map(([key,name])=>`<button class="tab ${state.kind === key ? 'active' : ''}" role="tab" aria-selected="${state.kind === key}" data-kind="${key}">${name} <small>(${state.overview.counts[key]})</small></button>`).join('')}</div>` : '') +
    (state.section === 'strategy' ? `<div class="objective-grid">${Object.entries(objectives).map(([key,[name,description]])=>`<article class="objective">${tag(key)}<h3>${name}</h3><p>${description}</p><button class="link-button" data-objective="${key}">Consultar acciones →</button></article>`).join('')}</div>${sectionTitle('Matriz de acciones', 'Incluye acciones B1–B6 y acciones transversales')}` : '') +
    filters(state.section === 'ecosystem' || state.section === 'institutions') +
    (state.section === 'ecosystem' ? `<div class="results-head"><span>Vista del catálogo</span><div><button class="link-button" data-mode="table" aria-pressed="${state.mode === 'table'}">Tabla</button> · <button class="link-button" data-mode="cards" aria-pressed="${state.mode === 'cards'}">Fichas</button></div></div>` : '') + '<div id="results" class="loading">Consultando registros…</div>';
  return collectionResults();
}
function quality() {
  content.innerHTML = heading('Lectura crítica del catálogo', 'Calidad y conciliación de datos', 'La calidad se documenta junto con los registros. Las diferencias entre fuentes se mantienen visibles hasta su validación por las instituciones.') + notice() +
    `<section class="panel">${sectionTitle('Criterios de interpretación', 'Cómo leer los conteos del observatorio')}<div class="flow"><div><small>01 / PROCEDENCIA</small><h3>Conservar la fuente</h3><p>Los registros mantienen sus campos originales y la referencia documental recibida.</p></div><div><small>02 / AUSENCIAS</small><h3>Distinguir vacío de cero</h3><p>Un campo sin información no demuestra ausencia de actividad institucional.</p></div><div><small>03 / CONCILIACIÓN</small><h3>Comparar las cifras</h3><p>El resumen declarado y el detalle de los anexos pueden presentar diferencias.</p></div><div><small>04 / VALIDACIÓN</small><h3>Evitar inferencias oficiales</h3><p>Los conteos describen registros de trabajo pendientes de validación.</p></div></div></section>
    <div class="section-title quality-title"><h2>Observaciones por institución</h2>${tag(`${state.overview.quality.length} con observaciones`, 'warning')}</div>
    <div class="cards">${state.overview.quality.map(r=>`<article class="record-card"><div class="card-top">${tag(canonicalInstitution(r.Centro))}${tag('Conciliación pendiente','warning')}</div><h3>${esc(institutionName(r.Centro))}</h3><p>${esc(r['Observaciones de conciliación'])}</p></article>`).join('')}</div>`;
}
function governance() {
  content.innerHTML = heading('Marco de referencia', 'Gobernanza y uso responsable', 'Un marco común para conectar las prioridades nacionales con las decisiones institucionales, la implementación y la evaluación de resultados.') +
    `<div class="notice"><b>ⓘ</b><span>El prototipo referencia Lineamientos MES v0.2 en consulta técnica. Esta vista resume ese marco; no acredita su aprobación ni sustituye los documentos rectores.</span></div>
    <section class="panel">${sectionTitle('De la estrategia a la implementación','Responsabilidades y evidencia a lo largo del proceso')}<div class="flow"><div><small>01 / MARCO NACIONAL</small><h3>Estrategia Nacional de IA</h3><p>Prioridades del país y objetivos de capital humano B1–B6.</p></div><div><small>02 / COORDINACIÓN</small><h3>Lineamientos MES</h3><p>Principios, responsabilidades y criterios comunes.</p></div><div><small>03 / INSTITUCIÓN</small><h3>Estrategias y planes IES</h3><p>Diagnóstico, capacidades y portafolio institucional.</p></div><div><small>04 / SEGUIMIENTO</small><h3>Proyectos e indicadores</h3><p>Implementación, evaluación y mejora con evidencia.</p></div></div></section>
    <div class="section-title quality-title"><h2>Principios e instrumentos</h2></div><div class="cards"><article class="record-card"><p class="eyebrow">Principios</p><h3>Centralidad humana y responsabilidad</h3><p>Propósito, agencia humana, responsabilidad, transparencia, integridad, inclusión, privacidad, soberanía, sostenibilidad y rigor.</p></article><article class="record-card"><p class="eyebrow">Evaluación de soluciones</p><h3>Criterios para pilotar y escalar</h3><p>Propósito, datos, impacto humano, calidad, accesibilidad, costo total y evidencia de resultados.</p></article><article class="record-card"><p class="eyebrow">Instrumentos de gestión</p><h3>Planificación y seguimiento</h3><p>Matriz de acciones, marco de indicadores y fuentes documentales para apoyar decisiones trazables.</p><div class="card-bottom"><a class="text-link" href="#strategy">Consultar matriz →</a><a class="text-link" href="#sources">Ver fuentes →</a></div></article></div>`;
}
async function scorecard() { return DashboardUI.render(); }
function recordDetails(item, collection) {
  const sourceFields = new Set(['Fuente','Fuentes principales','Fuente principal','Documento / fuente']);
  const institutionFields = new Set(['Centro reportante','Centro','Institución']);
  const detailField = ([key, value]) => `<div class="detail-field ${String(value).length > 150 ? 'wide' : ''}"><dt>${esc(key)}</dt><dd>${value === '' || value == null ? '<span class="source">Sin información reportada</span>' : esc(institutionFields.has(key) ? `${institutionName(value)} (${canonicalInstitution(value)})` : value)}</dd></div>`;
  const provenance = [...Object.entries(item.data).filter(([key])=>sourceFields.has(key)),
    ...Object.entries(item.data).filter(([key])=>institutionFields.has(key)).map(([key,value])=>[`${key} (denominación original)`,value])];
  const publication = item.publication === 'validated' ? `<p class="publication-note">Versión validada ${esc(item.published_revision)} · ${esc(new Date(item.published_at).toLocaleDateString('es'))}</p>` : '';
  return `${tag(item.institution || item.data.ID || item.data['Código'] || 'CATÁLOGO')}<h2>${esc(collection === 'summary' ? institutionName(item.institution) : collection === 'sources' ? sourceTitle(item.title) : item.title)}</h2>${item.institution ? `<p class="intro">${esc(institutionName(item.institution))}${institutionProvince(item.institution) ? ` · ${esc(institutionProvince(item.institution))}` : ''}</p>` : ''}${publication}${item.related_entries?.length?`<section class="panel role-guide"><h3>Fichas vinculadas</h3>${item.related_entries.map(e=>`<p>${esc(e.title)} · ${recordButton(e.collection,e.id,'Consultar')}</p>`).join('')}</section>`:''}<dl class="detail-grid">${Object.entries(item.data).filter(([key])=>!sourceFields.has(key)).map(detailField).join('')}</dl><details class="provenance"><summary>Procedencia y referencia técnica</summary><p class="source">Identificador del registro: ${esc(item.id)} · Edición octubre de 2026</p><dl>${provenance.map(detailField).join('')}</dl></details>`;
}
async function render() {
  state.request++;
  const section = location.hash.slice(1) || 'overview';
  state.section = Object.hasOwn(sections,section) ? section : 'overview';
  state.page = 1; state.q = ''; state.institution = '';
  document.querySelector('#breadcrumb').textContent = sections[state.section][1];
  document.title = `${sections[state.section][1]} · IA-ES`;
  document.querySelector('#navigation').innerHTML = navigationGroups.map(([name,keys])=>`<div class="navigation-group"><div class="navigation-heading">${name}</div>${keys.map(key=>`<a href="#${key}" class="${state.section === key ? 'active' : ''}" ${state.section === key ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${sections[key][0]}</span>${sections[key][1]}</a>`).join('')}</div>`).join('');
  try {
    if (state.section === 'overview') await overview();
    else if (state.section === 'indicators') await scorecard();
    else if (state.section === 'quality') quality();
    else if (state.section === 'governance') governance();
    else if (state.section === 'admin') await Admin.render();
    else await listPage();
  } catch(error) { showError(error); }
}
function showError(error) {
  const target = document.querySelector('#results') || content;
  target.innerHTML = `<div class="error"><h2>Error de consulta</h2><p>${esc(error.message)}</p><button class="button" id="retry">Volver a intentar</button></div>`;
}
document.addEventListener('submit', event => {
  if (event.target.id !== 'filters') return;
  event.preventDefault();
  state.q = document.querySelector('#query').value.trim();
  state.institution = document.querySelector('#institution')?.value || '';
  state.page = 1;
  collectionResults().catch(showError);
});
document.addEventListener('change', event => {
  if (event.target.id === 'institution') document.querySelector('#filters').requestSubmit();
});
document.addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  try {
    if (button.dataset.record) {
      const item = await api(`/api/records/${button.dataset.collection}/${button.dataset.record}`);
      document.querySelector('#detail-body').innerHTML = recordDetails(item, button.dataset.collection);
      dialog.showModal();
    } else if (button.id === 'close-detail') dialog.close();
    else if (button.dataset.kind) { state.kind = button.dataset.kind; state.page = 1; await listPage(); }
    else if (button.dataset.mode) { state.mode = button.dataset.mode; await listPage(); }
    else if (button.dataset.objective) { state.q = button.dataset.objective; state.page = 1; document.querySelector('#query').value = state.q; await collectionResults(); document.querySelector('#filters').scrollIntoView({behavior:'smooth'}); }
    else if (button.id === 'previous' || button.id === 'next') { state.page += button.id === 'next' ? 1 : -1; await collectionResults(); }
    else if (button.id === 'reset-filters') { state.q = ''; state.institution = ''; state.page = 1; await listPage(); }
    else if (button.id === 'retry') await initialize();
  } catch(error) { showError(error); }
});
dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
window.addEventListener('hashchange', () => { render(); window.scrollTo({top:0}); });
async function initialize() { try { [state.overview] = await Promise.all([api('/api/overview'),Admin.loadSession()]); await render(); } catch(error) { showError(error); } }
initialize();
