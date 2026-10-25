'use strict';
const Admin = (() => {
  let auth = {user:null, setup_required:false, roles:{}, institution_kinds:[]};
  let tab = 'institutions';
  let institutions = [], users = [], audit = {items:[],page:1,total:0,limit:20};
  let institutionQuery = '', province = '', activeFilter = '', flash = '';
  let editing = null;
  let viewRequest = 0;
  const can = (...roles) => Boolean(auth.user && roles.includes(auth.user.role));
  const fieldLabels = {code:'Siglas',name:'Nombre institucional',province:'Provincia',kind:'Tipo de entidad',aliases:'Variantes del nombre',
    active:'Estado',contact_name:'Persona de contacto',contact_email:'Correo de contacto',notes:'Notas',username:'Usuario',full_name:'Nombre completo',
    role:'Rol',institution_id:'Institución asignada',version:'Versión',updated_at:'Última modificación',created_at:'Fecha de creación',data:'Ficha de proyecto',status:'Estado de revisión',revision:'Revisión',published_revision:'Versión pública',review_note:'Observación de revisión'};
  const roleLabel = role => auth.roles[role] || role;
  const entityName = id => state.overview.institution_registry.find(item => item.id === id)?.name || 'Sin institución asignada';

  async function request(path, method='GET', data) {
    const response = await fetch(path, {method, credentials:'same-origin', headers: data ? {'Content-Type':'application/json','X-CSRF-Token':auth.csrf_token || ''} : {}, body:data ? JSON.stringify(data) : undefined});
    const body = await response.json();
    if (!response.ok) {
      if (response.status === 401) { auth.user = null; updateAccountLink(); }
      throw new Error(body.error || 'No se pudo completar la operación.');
    }
    return body;
  }
  async function loadSession() { auth = await request('/api/auth/session'); updateAccountLink(); return auth; }
  function updateAccountLink() {
    const link = document.querySelector('#account-link');
    if (link) link.textContent = auth.user ? `${auth.user.full_name} · ${roleLabel(auth.user.role)}` : 'Administración · Acceder';
  }
  function input(name, label, value='', options={}) {
    const {type='text', required=false, disabled=false, min='', max=160, autocomplete='off'} = options;
    return `<div class="field"><label for="admin-${name}">${label}</label><input id="admin-${name}" name="${name}" type="${type}" value="${esc(value)}" ${required ? 'required' : ''} ${disabled ? 'disabled' : ''} ${min ? `minlength="${min}"` : ''} maxlength="${max}" autocomplete="${autocomplete}"></div>`;
  }
  function select(name,label,items,value,disabled=false) {
    return `<div class="field"><label for="admin-${name}">${label}</label><select id="admin-${name}" name="${name}" ${disabled ? 'disabled' : ''}>${items.map(([key,name])=>`<option value="${esc(key)}" ${String(key) === String(value) ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select></div>`;
  }
  function formFooter(label) { return `<p class="form-error" role="alert" hidden></p><div class="form-actions"><button class="button" type="button" data-admin-close>Cancelar</button><button class="button primary" type="submit">${label}</button></div>`; }
  function formError(form, error) {
    const target = form.querySelector('.form-error');
    target.textContent = error.message;
    target.hidden = false;
    target.scrollIntoView({block:'nearest'});
  }
  function loginPage() {
    const setup = auth.setup_required;
    content.innerHTML = heading('Administración del observatorio', setup ? 'Configurar la primera cuenta' : 'Acceso a la administración',
      setup ? 'Cree la cuenta administradora MES para comenzar a gestionar instituciones y usuarios.' : 'Acceda con su cuenta para trabajar con los permisos de su rol e institución.') +
      `<section class="panel auth-panel"><h2>${setup ? 'Cuenta administradora MES' : 'Iniciar sesión'}</h2><form id="auth-form" class="admin-form" data-setup="${setup}">${setup ? input('full_name','Nombre completo','',{required:true,min:2,autocomplete:'name'}) : ''}${input('username','Usuario','',{required:true,min:3,max:80,autocomplete:'username'})}${input('password','Contraseña','',{type:'password',required:true,min:setup ? 12 : '',max:1024,autocomplete:setup ? 'new-password' : 'current-password'})}${setup ? input('confirm_password','Repita la contraseña','',{type:'password',required:true,min:12,max:1024,autocomplete:'new-password'}) : ''}<p class="source">${setup ? 'Use al menos 12 caracteres. No se crean credenciales predeterminadas.' : 'Si necesita una cuenta o restablecer el acceso, contacte al administrador MES.'}</p><p class="form-error" role="alert" hidden></p><button class="button primary" type="submit">${setup ? 'Crear cuenta y entrar' : 'Entrar'}</button></form></section>`;
  }
  async function render() {
    const view = ++viewRequest;
    const ticket = state.request;
    await loadSession();
    if (state.section !== 'admin' || ticket !== state.request || view !== viewRequest) return;
    if (!auth.user) { loginPage(); return; }
    const tabs = [...(can('admin','coordinator','reviewer') ? [['institutions','Instituciones'],['projects','Proyectos'],['programs','Formación'],['products','Productos'],['doctorands','Doctorandos'],['measurements','Mediciones']] : []), ...(can('admin') ? [['rules','Reglas del cuadro de mando'],['users','Usuarios y permisos']] : []),
      ...(can('admin','coordinator','reviewer') ? [['audit','Historial de cambios']] : []), ['account','Mi cuenta']];
    if (!tabs.some(([key])=>key === tab)) tab = tabs[0][0];
    content.innerHTML = heading('Administración', 'Gestión del observatorio', 'Instituciones, acceso y trazabilidad de los cambios en un mismo espacio de trabajo.') +
      `<div class="session-panel"><div><strong>${esc(auth.user.full_name)}</strong><span>${esc(roleLabel(auth.user.role))}${auth.user.institution_id ? ` · ${esc(entityName(auth.user.institution_id))}` : ''}</span></div><button class="button" type="button" data-admin-logout>Cerrar sesión</button></div><div class="admin-flash" role="status" ${flash ? '' : 'hidden'}>${esc(flash)}</div><div class="tabs" aria-label="Secciones administrativas">${tabs.map(([key,name])=>`<button class="tab ${tab === key ? 'active' : ''}" data-admin-tab="${key}" aria-pressed="${tab === key}">${name}</button>`).join('')}</div><div id="admin-content"><div class="loading">Cargando información…</div></div>`;
    if (tab === 'institutions') {
      institutions = (await request('/api/admin/institutions')).items;
      if (state.section === 'admin' && ticket === state.request && view === viewRequest) institutionList();
    } else if (tab === 'users') {
      users = (await request('/api/admin/users')).items;
      if (state.section === 'admin' && ticket === state.request && view === viewRequest) userList();
    } else if (tab === 'projects') {
      await ProjectUI.render({request,user:auth.user,onChange:refresh,isCurrent:()=>state.section === 'admin' && tab === 'projects' && view === viewRequest && ticket === state.request});
    } else if (['programs','products','doctorands','measurements','rules'].includes(tab)) {
      await RegistryUI.render({kind:tab,request,user:auth.user,onChange:refresh,isCurrent:()=>state.section === 'admin' && ['programs','products','doctorands','measurements','rules'].includes(tab) && view === viewRequest && ticket === state.request});
    } else if (tab === 'audit') {
      audit = await request(`/api/admin/audit?page=${audit.page}`);
      if (state.section === 'admin' && ticket === state.request && view === viewRequest) auditList();
    } else account();
  }
  function institutionList() {
    document.querySelector('#admin-content').innerHTML = `${sectionTitle(can('coordinator') ? 'Mi institución' : 'Catálogo institucional', can('coordinator') ? 'Puede actualizar los contactos y las notas de su institución. Los datos oficiales los gestiona el administrador MES.' : 'Mantenga las denominaciones, variantes, contactos y estados de las entidades.')}
      <div class="admin-toolbar"><form id="institution-search" class="filters"><div class="field search"><label for="institution-query">Buscar institución</label><input id="institution-query" type="search" value="${esc(institutionQuery)}" placeholder="Nombre, siglas o provincia…"></div><div class="field"><label for="province-filter">Provincia</label><select id="province-filter"><option value="">Todas las provincias</option>${[...new Set(institutions.map(i=>i.province))].sort().map(p=>`<option ${province === p ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select></div><div class="field"><label for="active-filter">Estado</label><select id="active-filter"><option value="">Todos</option><option value="true" ${activeFilter === 'true' ? 'selected' : ''}>Activas</option><option value="false" ${activeFilter === 'false' ? 'selected' : ''}>Inactivas</option></select></div><button class="button" type="submit">Filtrar</button></form>${can('admin') ? '<button class="button primary" data-new-institution>Nueva institución</button>' : ''}</div><div id="institution-rows"></div>`;
    institutionRows();
  }
  function institutionRows() {
    const norm = s => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    const rows = institutions.filter(i=>(!province || i.province === province) && (!activeFilter || String(i.active) === activeFilter) && norm([i.name,i.code,i.province,...i.aliases].join(' ')).includes(norm(institutionQuery)));
    document.querySelector('#institution-rows').innerHTML = `<p class="source">${rows.length} instituciones ${can('coordinator') ? 'asignadas a su cuenta' : 'en el catálogo'}</p>` + (rows.length ? `<div class="table-wrap"><table><thead><tr><th>Institución</th><th>Provincia y tipo</th><th>Contacto institucional</th><th>Estado</th><th></th></tr></thead><tbody>${rows.map(i=>`<tr><td><strong>${esc(i.name)}</strong><span class="sub">${esc(i.code)}</span></td><td>${esc(i.province)}<span class="sub">${esc(i.kind)}</span></td><td>${esc(i.contact_name || 'Sin contacto registrado')}<span class="sub">${esc(i.contact_email)}</span></td><td>${tag(i.active ? 'Activa' : 'Inactiva', i.active ? '' : 'neutral')}</td><td><button class="link-button" data-edit-institution="${esc(i.id)}">${can('reviewer') ? 'Consultar' : 'Editar'} ↗</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No hay instituciones para estos filtros.</div>');
  }
  function openInstitution(identity) {
    const item = institutions.find(i=>i.id === identity);
    editing = {type:'institution',item};
    const readonly = can('reviewer'), metadataDisabled = !can('admin');
    const fieldsDisabled = !can('admin');
    const value = key => item?.[key] ?? '';
    document.querySelector('#detail-body').innerHTML = `<p class="eyebrow">Catálogo institucional</p><h2>${item ? (readonly ? 'Ficha de institución' : 'Editar institución') : 'Nueva institución'}</h2><form id="institution-form" class="admin-form"><div class="admin-form-grid">${input('code','Siglas de referencia',value('code'),{required:true,max:20,disabled:metadataDisabled})}${input('name','Nombre institucional',value('name'),{required:true,min:3,max:240,disabled:fieldsDisabled})}${input('province','Provincia',value('province'),{required:true,min:2,max:100,disabled:fieldsDisabled})}${select('kind','Tipo de entidad',auth.institution_kinds.map(k=>[k,k]),item?.kind || 'Universidad',fieldsDisabled)}${select('active','Estado',[[true,'Activa'],[false,'Inactiva']],item?.active ?? true,fieldsDisabled)}<div class="field"><label for="admin-aliases">Variantes anteriores · una por línea</label><textarea id="admin-aliases" name="aliases" ${fieldsDisabled ? 'disabled' : ''} rows="4">${esc(item?.aliases.join('\n') || '')}</textarea></div>${input('contact_name','Persona de contacto',value('contact_name'),{disabled:readonly})}${input('contact_email','Correo de contacto',value('contact_email'),{type:'email',max:254,disabled:readonly})}<div class="field full"><label for="admin-notes">Notas de gestión</label><textarea id="admin-notes" name="notes" maxlength="4000" ${readonly ? 'disabled' : ''} rows="4">${esc(value('notes'))}</textarea></div></div><p class="source">${item ? 'El identificador institucional conserva los vínculos con los registros. Los nombres y las siglas anteriores se guardan como variantes.' : 'La institución recibirá un identificador permanente y podrá tener usuarios y registros asociados.'}</p>${readonly ? '<button class="button" type="button" data-admin-close>Cerrar</button>' : formFooter('Guardar institución')}</form>`;
    dialog.showModal();
  }
  function userList() {
    document.querySelector('#admin-content').innerHTML = `${sectionTitle('Usuarios y permisos','Asigne roles e instituciones. Desactive las cuentas que ya no deban acceder.')}<div class="admin-toolbar"><p class="source">${users.length} cuentas registradas · Las contraseñas nunca se muestran.</p><button class="button primary" data-new-user>Nuevo usuario</button></div><div class="table-wrap"><table><thead><tr><th>Persona y usuario</th><th>Rol</th><th>Institución asignada</th><th>Estado</th><th></th></tr></thead><tbody>${users.map(u=>`<tr><td><strong>${esc(u.full_name)}</strong><span class="sub">${esc(u.username)}</span></td><td>${esc(roleLabel(u.role))}</td><td>${esc(u.institution_id ? entityName(u.institution_id) : 'Ámbito general')}</td><td>${tag(u.active ? 'Activa' : 'Inactiva',u.active ? '' : 'neutral')}</td><td><button class="link-button" data-edit-user="${esc(u.id)}">Editar ↗</button></td></tr>`).join('')}</tbody></table></div><section class="panel role-guide"><h3>Alcance de cada rol</h3><p><strong>Administrador MES:</strong> instituciones, cuentas, contenidos, reglas del cuadro de mando y revisión independiente, e historial completo. <strong>Coordinador:</strong> contactos y notas de su institución, preparación y envío de sus contenidos y mediciones e historial institucional. <strong>Revisor:</strong> consulta de instituciones, revisión de contenidos y mediciones, validación o devolución con observaciones e historial. <strong>Lector:</strong> consulta del catálogo y gestión de su contraseña.</p></section>`;
  }
  function openUser(identity) {
    const item = users.find(u=>u.id === identity);
    editing = {type:'user',item};
    const self = item?.id === auth.user.id;
    const options = [['','Sin institución asignada'],...state.overview.institution_registry.filter(i=>i.active || i.id === item?.institution_id).map(i=>[i.id,`${i.code} · ${i.name}`])];
    document.querySelector('#detail-body').innerHTML = `<p class="eyebrow">Usuarios y permisos</p><h2>${item ? 'Editar usuario' : 'Nuevo usuario'}</h2><form id="user-form" class="admin-form"><div class="admin-form-grid">${input('full_name','Nombre completo',item?.full_name || '',{required:true,min:2})}${input('username','Usuario',item?.username || '',{required:true,min:3,max:80,autocomplete:'off'})}${select('role','Rol',Object.entries(auth.roles),item?.role || 'coordinator',self)}${select('institution_id','Institución asignada',options,item?.institution_id || '')}${select('active','Estado de la cuenta',[[true,'Activa'],[false,'Inactiva']],item?.active ?? true,self)}${!self ? input('password',item ? 'Nueva contraseña · opcional' : 'Contraseña inicial','',{type:'password',required:!item,min:12,max:1024,autocomplete:'new-password'}) : ''}</div><p class="source">${self ? 'Su rol y el estado de su cuenta están protegidos. Cambie su contraseña desde «Mi cuenta».' : 'Los coordinadores requieren una institución activa. Cambiar contraseña, rol, institución o estado cierra las sesiones anteriores de esa cuenta.'}</p>${formFooter('Guardar usuario')}</form>`;
    dialog.showModal();
  }
  const date = timestamp => new Intl.DateTimeFormat('es',{dateStyle:'medium',timeStyle:'short'}).format(new Date(timestamp));
  function auditList() {
    document.querySelector('#admin-content').innerHTML = `${sectionTitle('Historial de cambios','Quién realizó cada operación, cuándo y qué valores cambiaron.')}` +
      (audit.items.length ? `<div class="table-wrap"><table><thead><tr><th>Operación</th><th>Responsable</th><th>Fecha y hora</th><th></th></tr></thead><tbody>${audit.items.map(item=>`<tr><td><strong>${esc(item.action)}</strong><span class="sub">${esc(item.after?.name || item.after?.full_name || item.after?.data?.title || item.before?.name || item.before?.data?.title || ({institution:'Institución',user:'Cuenta de usuario',session:'Acceso al sistema',project:'Proyecto institucional'}[item.entity_type]))}</span></td><td>${esc(item.actor_name)}</td><td>${esc(date(item.created_at))}</td><td><button class="link-button" data-audit="${item.id}">Ver detalle ↗</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Todavía no hay operaciones registradas en este ámbito.</div>') +
      `<div class="pagination"><span>Página ${audit.page} de ${Math.max(1,Math.ceil(audit.total/audit.limit))} · ${audit.total} operaciones</span><div><button class="button" data-audit-page="${audit.page-1}" ${audit.page === 1 ? 'disabled' : ''}>← Anterior</button><button class="button" data-audit-page="${audit.page+1}" ${audit.page*audit.limit >= audit.total ? 'disabled' : ''}>Siguiente →</button></div></div>`;
  }
  function displayValue(key,value) {
    if (value === undefined || value === null || value === '') return '—';
    if (key === 'active') return value ? 'Activa' : 'Inactiva';
    if (key === 'role') return roleLabel(value);
    if (key === 'institution_id') return entityName(value);
    if (typeof value === 'object') return JSON.stringify(value,null,2);
    return Array.isArray(value) ? value.join(', ') : String(value);
  }
  function openAudit(id) {
    const item = audit.items.find(i=>i.id === Number(id));
    const keys = [...new Set([...Object.keys(item.before || {}),...Object.keys(item.after || {})])].filter(key=>key !== 'id' && JSON.stringify(item.before?.[key]) !== JSON.stringify(item.after?.[key]));
    document.querySelector('#detail-body').innerHTML = `<p class="eyebrow">Historial de cambios</p><h2>${esc(item.action)}</h2><p class="intro">${esc(item.actor_name)} · ${esc(date(item.created_at))}</p>${keys.length ? `<div class="table-wrap audit-diff"><table><thead><tr><th>Campo</th><th>Antes</th><th>Después</th></tr></thead><tbody>${keys.map(key=>`<tr><td>${esc(fieldLabels[key] || key)}</td><td>${esc(displayValue(key,item.before?.[key]))}</td><td>${esc(displayValue(key,item.after?.[key]))}</td></tr>`).join('')}</tbody></table></div>` : '<p class="source">Operación de acceso o de credenciales. No se guardan contraseñas ni tokens en el historial.</p>'}`;
    dialog.showModal();
  }
  function account() {
    document.querySelector('#admin-content').innerHTML = `<section class="panel account-panel"><h2>Mi cuenta</h2><dl class="detail-grid"><div class="detail-field"><dt>Persona</dt><dd>${esc(auth.user.full_name)}</dd></div><div class="detail-field"><dt>Usuario</dt><dd>${esc(auth.user.username)}</dd></div><div class="detail-field"><dt>Rol</dt><dd>${esc(roleLabel(auth.user.role))}</dd></div><div class="detail-field"><dt>Institución</dt><dd>${esc(auth.user.institution_id ? entityName(auth.user.institution_id) : 'Ámbito general')}</dd></div></dl><h3>Cambiar mi contraseña</h3><form id="password-form" class="admin-form">${input('current_password','Contraseña actual','',{type:'password',required:true,max:1024,autocomplete:'current-password'})}${input('password','Nueva contraseña','',{type:'password',required:true,min:12,max:1024,autocomplete:'new-password'})}${input('confirm_password','Repita la nueva contraseña','',{type:'password',required:true,min:12,max:1024,autocomplete:'new-password'})}<p class="source">Use al menos 12 caracteres. Al cambiarla se cerrarán sus otras sesiones.</p><p class="form-error" role="alert" hidden></p><button class="button primary" type="submit">Cambiar contraseña</button></form></section>`;
  }
  async function refresh(message) {
    flash = message;
    state.overview = await api('/api/overview');
    if (state.section === 'admin') await render();
    document.querySelector('#announcement').textContent = message;
  }
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!['auth-form','institution-form','user-form','password-form','institution-search'].includes(form.id)) return;
    event.preventDefault();
    if (form.id === 'institution-search') {
      institutionQuery = document.querySelector('#institution-query').value.trim();
      province = document.querySelector('#province-filter').value;
      activeFilter = document.querySelector('#active-filter').value;
      institutionRows(); return;
    }
    const submit = form.querySelector('[type="submit"]');
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(form));
      if ('confirm_password' in data && data.confirm_password !== data.password) throw new Error('Las contraseñas no coinciden.');
      delete data.confirm_password;
      if (form.id === 'auth-form') {
        auth = await request(`/api/auth/${form.dataset.setup === 'true' ? 'setup' : 'login'}`,'POST',data);
        flash = 'Acceso iniciado correctamente.'; await refresh(flash);
      } else if (form.id === 'password-form') {
        auth = await request('/api/auth/password','POST',data); await refresh('Contraseña actualizada. Las otras sesiones se han cerrado.');
      } else {
        const old = editing.item;
        const type = form.id === 'institution-form' ? 'institutions' : 'users';
        if (type === 'institutions') {
          data.aliases = 'aliases' in data ? data.aliases.split('\n').map(x=>x.trim()).filter(Boolean) : old.aliases;
          if (can('coordinator')) { delete data.aliases; }
        }
        if ('active' in data) data.active = data.active === 'true';
        if (data.password === '') delete data.password;
        const payload = {...(old || {}),...data};
        delete payload.id;
        await request(`/api/admin/${type}${old ? '/' + old.id : ''}`,old ? 'PATCH' : 'POST',payload);
        dialog.close(); await refresh(type === 'institutions' ? 'Institución guardada. El cambio quedó registrado en el historial.' : 'Usuario guardado con sus permisos actualizados.');
      }
    } catch(error) { formError(form,error); }
    finally { submit.disabled = false; }
  });
  document.addEventListener('change', event => {
    if (['province-filter','active-filter'].includes(event.target.id)) document.querySelector('#institution-search').requestSubmit();
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button) return;
    try {
      if (button.hasAttribute('data-admin-close')) dialog.close();
      else if (button.hasAttribute('data-admin-logout')) { await request('/api/auth/logout','POST',{}); auth.user=null; institutions=[]; users=[]; editing=null; audit={items:[],page:1,total:0,limit:20}; flash=''; await render(); }
      else if (button.dataset.adminTab) { tab=button.dataset.adminTab; flash=''; await render(); }
      else if (button.hasAttribute('data-new-institution')) openInstitution();
      else if (button.dataset.editInstitution) openInstitution(button.dataset.editInstitution);
      else if (button.hasAttribute('data-new-user')) openUser();
      else if (button.dataset.editUser) openUser(button.dataset.editUser);
      else if (button.dataset.audit) openAudit(button.dataset.audit);
      else if (button.dataset.auditPage) { audit.page=Number(button.dataset.auditPage); await render(); }
      else if (button.dataset.relatedKind) { tab=button.dataset.relatedKind;dialog.close();await render();if(tab==='projects')await ProjectUI.open(button.dataset.relatedId);else await RegistryUI.open(button.dataset.relatedId); }
    } catch(error) { const target = document.querySelector('#admin-content'); if (target) target.innerHTML=`<div class="error" role="alert">${esc(error.message)} <button class="button" data-admin-tab="${esc(tab)}">Volver a intentar</button></div>`; }
  });
  return {loadSession, render};
})();
