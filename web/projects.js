'use strict';
const ProjectUI = (() => {
  let context, listing = {items:[],page:1,total:0,limit:15,counts:{}}, editing = null;
  let query = '', institution = '', status = '', page = 1, sequence = 0, evidenceIndex = 0;
  const statuses = {draft:'Borrador',submitted:'En revisión',returned:'Devuelto',validated:'Validado'};
  const implementation = ['Por precisar','Idea','Diseño','Piloto','En ejecución','Finalizado','Suspendido'];
  const labels = {title:'Título',code:'Código',institution_id:'Institución',lead:'Responsable',description:'Descripción',classification:'Clasificación',objectives:'Objetivos B1–B6',implementation_status:'Estado de implementación',start_date:'Inicio',end_date:'Cierre',participants:'Entidades participantes',evidence:'Evidencias',status:'Estado de revisión',revision:'Revisión'};
  const canEdit = () => ['admin','coordinator'].includes(context.user.role);
  const canReview = item => ['admin','reviewer'].includes(context.user.role) && item.last_editor_id !== context.user.id;
  const date = value => value ? new Intl.DateTimeFormat('es',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : '—';
  const badge = value => tag(statuses[value] || value,value === 'returned' ? 'warning' : value === 'validated' ? '' : 'neutral');
  const ensure = () => context && context.isCurrent();
  function errorIn(target,error) { target.innerHTML=`<div class="error" role="alert">${esc(error.message)} <button class="button" data-project-refresh>Volver a cargar</button></div>`; }

  async function render(config) {
    if (context && context.user.id !== config.user.id) { query='';institution='';status='';page=1;editing=null; }
    context = config;
    const ticket = ++sequence;
    const params = new URLSearchParams({q:query,institution_id:institution,status,page,limit:15});
    const result = await context.request(`/api/admin/projects?${params}`);
    if (!ensure() || ticket !== sequence) return;
    listing = result;
    document.querySelector('#admin-content').innerHTML = `${sectionTitle('Proyectos institucionales','Prepare la ficha, envíela a revisión y publique únicamente la versión validada.')}
      <div class="notice"><b aria-hidden="true">ⓘ</b><span>Los reportes importados se conservan como borradores de trabajo y siguen visibles como «Reportado» en el catálogo. La validación requiere una persona distinta de quien editó la ficha.</span></div>
      <div class="workflow-counts">${Object.entries(statuses).map(([key,name])=>`<button class="workflow-count" data-project-status="${key}" aria-pressed="${status === key}"><strong>${listing.counts[key] || 0}</strong><span>${name}</span></button>`).join('')}</div>
      <div class="admin-toolbar"><form id="project-search" class="filters"><div class="field search"><label for="project-query">Buscar proyecto</label><input type="search" id="project-query" value="${esc(query)}" placeholder="Título, código o responsable…"></div>${context.user.role !== 'coordinator' ? `<div class="field"><label for="project-filter-institution">Institución</label><select id="project-filter-institution"><option value="">Todas las instituciones</option>${state.overview.institution_registry.map(i=>`<option value="${esc(i.id)}" ${institution === i.id ? 'selected' : ''}>${esc(i.code)} · ${esc(i.name)}</option>`).join('')}</select></div>` : ''}<button class="button" type="submit">Buscar</button><button class="button" type="button" data-project-reset>Ver todos</button></form>${canEdit() ? '<button class="button primary" data-new-project>Nuevo proyecto</button>' : ''}</div>
      <div class="results-head"><span>${listing.total} proyectos ${status ? '· '+statuses[status] : ''}</span><span>Ordenados por última actualización</span></div>` +
      (listing.items.length ? `<div class="table-wrap"><table><thead><tr><th>Proyecto</th><th>Institución</th><th>Responsable</th><th>Estado de revisión</th><th>Actualización</th><th></th></tr></thead><tbody>${listing.items.map(item=>`<tr><td><strong>${esc(item.data.title)}</strong><span class="sub">${esc(item.data.code || 'Sin código registrado')}</span></td><td>${esc(item.institution_name)}<span class="sub">${esc(item.institution_code)}</span></td><td>${esc(item.data.lead || 'Por completar')}</td><td>${badge(item.status)}<span class="sub">Revisión ${item.revision}${item.published_revision ? ` · Pública: ${item.published_revision}` : ''}</span></td><td>${esc(date(item.updated_at))}</td><td><button class="link-button" data-open-project="${esc(item.id)}">Abrir ficha ↗</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay proyectos para esta combinación de filtros.</div>') +
      `<div class="pagination"><span>Página ${listing.page} de ${Math.max(1,Math.ceil(listing.total/listing.limit))}</span><div><button class="button" data-project-page="${listing.page-1}" ${listing.page<=1 ? 'disabled' : ''}>← Anterior</button><button class="button" data-project-page="${listing.page+1}" ${listing.page*listing.limit>=listing.total ? 'disabled' : ''}>Siguiente →</button></div></div>`;
  }
  function input(key,label,value,disabled=false,type='text',max=240) {
    return `<div class="field"><label for="project-${key}">${label}</label><input id="project-${key}" name="${key}" type="${type}" value="${esc(value)}" ${disabled ? 'disabled' : ''} ${key === 'title' ? 'required minlength="3"' : ''} maxlength="${max}"></div>`;
  }
  function evidenceRow(entry,readonly) {
    const n = ++evidenceIndex;
    return `<div class="evidence-entry"><div class="evidence-heading"><strong>Evidencia ${n}</strong>${readonly ? '' : '<button class="link-button" type="button" data-remove-evidence>Quitar</button>'}</div><div class="field"><label for="evidence-title-${n}">Título</label><input id="evidence-title-${n}" data-evidence-title value="${esc(entry.title || '')}" minlength="3" maxlength="300" ${readonly ? 'disabled' : 'required'}></div><div class="field"><label for="evidence-reference-${n}">Referencia documental</label><textarea id="evidence-reference-${n}" data-evidence-reference maxlength="2000" rows="2" ${readonly ? 'disabled' : ''}>${esc(entry.reference || '')}</textarea></div><div class="field"><label for="evidence-url-${n}">Enlace de consulta · opcional</label><input id="evidence-url-${n}" data-evidence-url type="url" maxlength="2000" value="${esc(entry.url || '')}" ${readonly ? 'disabled' : ''}>${entry.url ? `<a class="text-link" href="${esc(entry.url)}" target="_blank" rel="noopener noreferrer">Consultar evidencia ↗</a>` : ''}</div></div>`;
  }
  function relatedEntries(item) { return item.related_entries?.length ? `<section class="panel role-guide"><h3>Fichas vinculadas</h3>${item.related_entries.map(e=>`<p><button class="link-button" data-related-kind="${esc(e.kind)}" data-related-id="${esc(e.id)}">${esc(e.title)} ↗</button></p>`).join('')}</section>` : ''; }
  function reviewActions(item) {
    if (!item?.institution_active) return '';
    if (item.status === 'submitted') return `<div class="project-review-actions">${canReview(item) ? '<button class="button" data-project-review="return">Devolver con observaciones</button><button class="button primary" data-project-review="validate">Validar y publicar</button>' : '<p class="source">La revisión corresponde a otra persona con rol de revisor o administrador MES.</p>'}${canEdit() ? '<button class="button" data-project-action="withdraw">Retirar envío para corregir</button>' : ''}</div>`;
    if (item.status === 'validated' && canEdit()) return '<div class="project-review-actions"><button class="button primary" data-project-action="reopen">Preparar nueva versión</button><p class="source">La versión validada seguirá en el catálogo mientras se revisa la actualización.</p></div>';
    return '';
  }
  function valueDisplay(value) {
    if (value == null || value === '') return '—';
    if (Array.isArray(value)) return value.map(v=>typeof v === 'object' ? `${v.title}: ${v.url || v.reference || 'Sin referencia'}` : v).join('\n');
    return String(value);
  }
  function eventDiff(event) {
    const before = {...event.before?.data,status:event.before?.status,revision:event.before?.revision};
    const after = {...event.after.data,status:event.after.status,revision:event.after.revision};
    const keys = Object.keys(after).filter(k=>JSON.stringify(before[k]) !== JSON.stringify(after[k]));
    return `<dl class="project-diff">${keys.map(key=>`<div><dt>${esc(labels[key] || key)}</dt><dd><span>Antes: ${esc(key === 'status' ? statuses[before[key]] || '—' : valueDisplay(before[key]))}</span><span>Después: ${esc(key === 'status' ? statuses[after[key]] : valueDisplay(after[key]))}</span></dd></div>`).join('')}</dl>`;
  }
  function history(item) {
    return `<details class="project-history"><summary>Historial del proyecto · ${item.events?.length || 0} operaciones</summary>${(item.events || []).map(event=>`<article class="project-event"><strong>${esc(event.action)}</strong><p class="source">${esc(event.actor_name)} · ${esc(date(event.created_at))}</p>${event.note ? `<p>${esc(event.note)}</p>` : ''}<details><summary>Ver cambios</summary>${eventDiff(event)}</details></article>`).join('')}</details>`;
  }
  function editor(item) {
    editing = item;
    evidenceIndex = 0;
    const editable = canEdit() && (!item || ['draft','returned'].includes(item.status)) && (!item || item.institution_active);
    const d = item?.data || {title:'',code:'',institution_id:context.user.role === 'coordinator' ? context.user.institution_id : '',lead:'',description:'',classification:'',objectives:[],implementation_status:'Por precisar',start_date:'',end_date:'',participants:'',evidence:[]};
    const institutions = state.overview.institution_registry.filter(i=>i.active || i.id === d.institution_id);
    document.querySelector('#detail-body').innerHTML = `<p class="eyebrow">Proyectos institucionales</p><h2>${item ? esc(d.title) : 'Nuevo proyecto'}</h2><div class="project-version">${item ? `${badge(item.status)}<span>Revisión ${item.revision} · Versión de ficha ${item.version}</span>${item.published_revision ? tag(`Versión pública ${item.published_revision}`) : tag('Sin versión validada','neutral')}` : tag('Nuevo borrador','neutral')}</div>${item?.review_note ? `<div class="review-note"><strong>Observación de la última revisión</strong><p>${esc(item.review_note)}</p></div>` : ''}${item?.source_changed ? '<div class="notice">El reporte de origen cambió desde la importación. Compare ambos reportes antes de enviar a revisión.</div>' : ''}${item && !item.institution_active ? '<div class="notice">La institución está inactiva. Su administrador debe reactivarla para continuar con el proyecto.</div>' : ''}
      <form id="project-form" class="admin-form"><div class="admin-form-grid">${input('title','Título del proyecto',d.title,!editable,'text',600)}${input('code','Código del proyecto · si existe',d.code,!editable,'text',100)}<div class="field"><label for="project-institution_id">Institución reportante</label><select id="project-institution_id" name="institution_id" required ${!editable || Boolean(item) || context.user.role === 'coordinator' ? 'disabled' : ''}><option value="">Seleccione una institución</option>${institutions.map(i=>`<option value="${esc(i.id)}" ${i.id === d.institution_id ? 'selected' : ''}>${esc(i.code)} · ${esc(i.name)}</option>`).join('')}</select></div>${input('lead','Responsable del proyecto',d.lead,!editable)}<div class="field"><label for="project-implementation_status">Estado de implementación</label><select id="project-implementation_status" name="implementation_status" ${editable ? '' : 'disabled'}>${implementation.map(s=>`<option ${s === d.implementation_status ? 'selected' : ''}>${s}</option>`).join('')}</select></div>${input('classification','Ámbito o clasificación de trabajo',d.classification,!editable,'text',300)}${input('start_date','Fecha de inicio · si se conoce',d.start_date,!editable,'date')}${input('end_date','Fecha de cierre · si se conoce',d.end_date,!editable,'date')}<div class="field full"><label for="project-description">Descripción y resultados esperados</label><textarea id="project-description" name="description" rows="5" maxlength="12000" ${editable ? '' : 'disabled'}>${esc(d.description)}</textarea></div><div class="field full"><label for="project-participants">Entidades participantes</label><textarea id="project-participants" name="participants" rows="2" maxlength="3000" ${editable ? '' : 'disabled'}>${esc(d.participants)}</textarea></div><fieldset class="project-objectives full"><legend>Objetivos estratégicos B1–B6</legend>${Object.entries(objectives).map(([code,[name]])=>`<label><input type="checkbox" name="objectives" value="${code}" ${d.objectives.includes(code) ? 'checked' : ''} ${editable ? '' : 'disabled'}><span><strong>${code}</strong> · ${esc(name)}</span></label>`).join('')}</fieldset></div>
      <section class="project-evidence"><h3>Evidencias y referencias</h3><p class="source">Registre un título y una referencia documental o un enlace que permita verificar la información.</p><div id="project-evidence-list">${d.evidence.map(e=>evidenceRow(e,!editable)).join('')}</div>${editable ? '<button class="button" type="button" data-add-evidence>+ Añadir evidencia</button>' : ''}</section><p class="form-error" role="alert" hidden></p>${editable ? '<p class="source">Puede guardar una ficha incompleta como borrador. Para enviarla se requieren responsable, descripción, objetivos, estado de implementación y evidencia.</p><div class="form-actions"><button class="button" type="button" data-project-close>Cancelar</button><button class="button" type="submit" value="draft">Guardar borrador</button><button class="button primary" type="submit" value="submit">Guardar y enviar a revisión</button></div>' : ''}</form>${item ? reviewActions(item)+relatedEntries(item)+history(item) : ''}${item?.original ? `<details class="provenance"><summary>Reporte original de importación</summary><dl class="detail-grid">${Object.entries(item.original).map(([key,value])=>`<div class="detail-field"><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl></details>` : ''}${item?.source_changed ? `<details class="provenance"><summary>Reporte de origen actualizado</summary><dl class="detail-grid">${Object.entries(item.latest_report || {}).map(([key,value])=>`<div class="detail-field"><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl></details>` : ''}`;
    dialog.showModal();
  }
  async function open(identity) {
    if (!ensure()) return;
    const item = identity ? await context.request(`/api/admin/projects/${identity}`) : null;
    if (ensure()) editor(item);
  }
  function reviewForm(action) {
    const returning = action === 'return';
    document.querySelector('#detail-body').innerHTML = `<p class="eyebrow">Revisión institucional</p><h2>${returning ? 'Devolver con observaciones' : 'Validar y publicar'}</h2><h3>${esc(editing.data.title)}</h3><p class="intro">${esc(editing.institution_name)} · Revisión ${editing.revision}</p><p>${returning ? 'Explique qué debe completar o corregir la institución. La observación quedará en el historial y no se publicará en el catálogo.' : 'La ficha revisada se incorporará al catálogo como versión validada. Los borradores y las observaciones de revisión seguirán siendo privados.'}</p><form id="project-review-form" class="admin-form" data-action="${action}"><div class="field"><label for="project-review-note">${returning ? 'Observaciones para la institución' : 'Observación de revisión · opcional'}</label><textarea id="project-review-note" name="note" rows="5" maxlength="4000" ${returning ? 'required minlength="10"' : ''}></textarea></div><p class="form-error" role="alert" hidden></p><div class="form-actions"><button class="button" type="button" data-open-project="${esc(editing.id)}">Volver a la ficha</button><button class="button primary" type="submit">${returning ? 'Devolver a la institución' : 'Validar y publicar'}</button></div></form>`;
  }
  function formError(form,error) { const target=form.querySelector('.form-error');target.textContent=error.message;target.hidden=false;target.scrollIntoView({block:'nearest'}); }
  async function transition(action,note='') {
    return context.request(`/api/admin/projects/${editing.id}/${action}`,'POST',{version:editing.version,note});
  }
  document.addEventListener('submit',async event=>{
    const form = event.target;
    if (!['project-search','project-form','project-review-form'].includes(form.id)) return;
    event.preventDefault();
    if (!ensure()) return;
    if (form.id === 'project-search') {
      query=document.querySelector('#project-query').value.trim(); institution=document.querySelector('#project-filter-institution')?.value || ''; page=1;
      try { await render(context); } catch(error) { errorIn(document.querySelector('#admin-content'),error); } return;
    }
    const buttons=[...form.querySelectorAll('[type="submit"]')];
    if (buttons.some(b=>b.disabled)) return;
    buttons.forEach(b=>{b.disabled=true;});
    let saved=false;
    try {
      const data=new FormData(form);
      if (form.id === 'project-review-form') {
        await transition(form.dataset.action,data.get('note') || '');
        dialog.close();await context.onChange(form.dataset.action === 'return' ? 'Proyecto devuelto con observaciones.' : 'Proyecto validado y publicado en el catálogo.');
      } else {
        const payload=Object.fromEntries(['title','code','lead','description','classification','implementation_status','start_date','end_date','participants'].map(key=>[key,data.get(key) || '']));
        payload.institution_id=editing?.institution_id || (context.user.role === 'coordinator' ? context.user.institution_id : data.get('institution_id'));
        payload.objectives=data.getAll('objectives');
        payload.evidence=[...form.querySelectorAll('.evidence-entry')].map(row=>({title:row.querySelector('[data-evidence-title]').value.trim(),reference:row.querySelector('[data-evidence-reference]').value.trim(),url:row.querySelector('[data-evidence-url]').value.trim()}));
        if (editing) payload.version=editing.version;
        const result=await context.request(`/api/admin/projects${editing ? '/'+editing.id : ''}`,editing ? 'PATCH' : 'POST',payload);
        editing={...editing,...result}; saved=true;
        if (event.submitter?.value === 'submit') await transition('submit');
        dialog.close();await context.onChange(event.submitter?.value === 'submit' ? 'Proyecto enviado a revisión.' : 'Borrador guardado. Todavía no se publica esta versión.');
      }
    } catch(error) { formError(form,new Error((saved ? 'El borrador se guardó. ' : '')+error.message)); }
    finally { buttons.forEach(b=>{b.disabled=false;}); }
  });
  document.addEventListener('change',event=>{ if (event.target.id === 'project-filter-institution') document.querySelector('#project-search').requestSubmit(); });
  document.addEventListener('click',async event=>{
    const button=event.target.closest('button');
    if (!button || !ensure()) return;
    try {
      if (button.dataset.openProject) await open(button.dataset.openProject);
      else if (button.hasAttribute('data-new-project')) editor(null);
      else if (button.hasAttribute('data-project-close')) dialog.close();
      else if (button.dataset.projectStatus) {status=status === button.dataset.projectStatus ? '' : button.dataset.projectStatus;page=1;await render(context);}
      else if (button.hasAttribute('data-project-reset')) {query='';institution='';status='';page=1;await render(context);}
      else if (button.hasAttribute('data-project-refresh')) await render(context);
      else if (button.dataset.projectPage) {page=Number(button.dataset.projectPage);await render(context);}
      else if (button.hasAttribute('data-add-evidence')) { if (document.querySelectorAll('.evidence-entry').length>=30) throw new Error('Se admiten hasta 30 evidencias por proyecto.');document.querySelector('#project-evidence-list').insertAdjacentHTML('beforeend',evidenceRow({},false)); }
      else if (button.hasAttribute('data-remove-evidence')) button.closest('.evidence-entry').remove();
      else if (button.dataset.projectReview) reviewForm(button.dataset.projectReview);
      else if (button.dataset.projectAction) {
        button.disabled=true;const identity=editing.id;await transition(button.dataset.projectAction);dialog.close();await context.onChange(button.dataset.projectAction === 'reopen' ? 'Nueva revisión abierta. La versión validada sigue publicada.' : 'Envío retirado. Puede corregir el borrador.');await open(identity);
      }
    } catch(error) {
      button.disabled=false;
      const form=document.querySelector('#project-form') || document.querySelector('#project-review-form');
      if (form && dialog.open) formError(form,error); else errorIn(document.querySelector('#admin-content'),error);
    }
  });
  return {render,open};
})();
