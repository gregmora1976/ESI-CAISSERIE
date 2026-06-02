let CAISSES=[];let SELECTED=null;let LAST_QUOTE=null;let WEEK_START=startOfWeek(new Date());
const euro=v=>Number(v||0).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})+' €';
const norm=s=>(s||'').toLowerCase().replaceAll(' ','_').replace('é','e').replace('ê','e').replace('è','e').replace('à','a');
async function api(url,opt){const r=await fetch(url,opt);return await r.json();}
async function loadCaisses(){CAISSES=await api('/api/caisses');return CAISSES;}
function card(c){return `<div class="card ${norm(c.statut)}" onclick="selectAtelier('${c.id}')"><h4>${c.id} • ${c.numero_dossier||'-'}</h4><p>Colis ${c.numero_colis||'-'} • ${c.client||'-'}</p><p>${c.longueur||'-'} × ${c.largeur||'-'} × ${c.hauteur||'-'} cm</p><span class="badge">${c.statut}</span></div>`}
async function initEmballage(){await loadCaisses();renderKanban();document.getElementById('caisseForm')?.addEventListener('submit',async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target).entries());await api('/api/caisses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});e.target.reset();await loadCaisses();renderKanban();});}
function renderKanban(){const el=document.getElementById('kanban');if(!el)return;const cols=['A créer','En cours','Caisse prête','Annulée'];el.innerHTML=cols.map(st=>`<div class="lane"><h3>${st}</h3>${CAISSES.filter(c=>c.statut===st).map(card).join('')||'<div class="empty">Aucune</div>'}</div>`).join('');}
async function initDevis(){await loadPrices();}
async function loadPrices(){const p=await api('/api/prices');const labels={cp_m2:'CP €/m²',barres_ml:'Barres €/ml',chevrons_ml:'Chevrons €/ml',consommables:'Consommables €',taux_horaire:'Main œuvre €/h',heures:'Temps h',frais_generaux:'Frais généraux %',marge:'Marge %'};const box=document.getElementById('priceForm');if(box)box.innerHTML=Object.entries(labels).map(([k,l])=>`<label>${l}<input id="price_${k}" type="number" step="0.01" value="${p[k]??''}"></label>`).join('');}
async function savePrices(){const keys=['cp_m2','barres_ml','chevrons_ml','consommables','taux_horaire','heures','frais_generaux','marge'];let data={};keys.forEach(k=>data[k]=document.getElementById('price_'+k).value);await api('/api/prices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});alert('Tarifs enregistrés');}
async function calculateQuote(){const form=document.getElementById('devisForm');const data=Object.fromEntries(new FormData(form).entries());LAST_QUOTE={...data};const q=await api('/api/devis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});LAST_QUOTE.prix_achat=q.prix_achat;LAST_QUOTE.prix_cession=q.prix_cession;document.getElementById('quoteResult').innerHTML=`<div class="box"><h3>Prix de cession estimé</h3><div class="quote-total">${euro(q.prix_cession)}</div><p>Prix achat / revient : <strong>${euro(q.prix_achat)}</strong></p></div><table class="table"><tr><th>Matière</th><th>Quantité</th></tr><tr><td>CP</td><td>${q.matieres.cp_m2} m²</td></tr><tr><td>Barres</td><td>${q.matieres.barres_ml} ml</td></tr><tr><td>Chevrons</td><td>${q.matieres.chevrons_ml} ml</td></tr></table><table class="table"><tr><th>Poste</th><th>Total</th></tr>${Object.entries(q.detail).map(([k,v])=>`<tr><td>${k}</td><td>${euro(v)}</td></tr>`).join('')}</table>`;}
async function createFromQuote(){if(!LAST_QUOTE)await calculateQuote();await api('/api/caisses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(LAST_QUOTE)});alert('Demande créée depuis le devis');location.href='/emballage';}
async function loadAtelier(filter=''){await loadCaisses();const items=filter?CAISSES.filter(c=>c.statut===filter):CAISSES;const box=document.getElementById('atelierList');if(box)box.innerHTML=items.map(card).join('')||'<div class="empty">Aucune demande</div>';}
async function selectAtelier(id){SELECTED=id;const c=CAISSES.find(x=>x.id===id)||await api('/api/caisses/'+id);const debit=await api('/api/caisses/'+id+'/debit');const box=document.getElementById('atelierDetail');if(!box)return;box.innerHTML=`<div class="detail-grid"><div class="box"><h3>${c.id} • ${c.numero_dossier||'-'}</h3><p><b>Client :</b> ${c.client||'-'}</p><p><b>Chargé :</b> ${c.charge_projet||'-'}</p><p><b>Type :</b> ${c.type_caisse||'-'}</p><p><b>Dims int :</b> ${c.longueur||'-'} × ${c.largeur||'-'} × ${c.hauteur||'-'} cm</p><p><b>Délai :</b> ${c.delai_demande||'-'}</p></div><div class="box"><label>Caissier<input id="edit_caissier" value="${c.caissier||''}"></label><label>Atelier<select id="edit_atelier"><option ${c.atelier==='Secobois'?'selected':''}>Secobois</option><option ${c.atelier==='Arckx'?'selected':''}>Arckx</option></select></label><label>Date prévue<input id="edit_date" type="date" value="${c.date_prevue||''}"></label><label>Commentaire<textarea id="edit_commentaire">${c.commentaire_atelier||''}</textarea></label><button class="secondary" onclick="saveAtelier()">Enregistrer</button></div></div><div class="filters"><button onclick="setStatus('A créer')">À créer</button><button onclick="setStatus('En cours')">En cours</button><button class="success" onclick="setStatus('Caisse prête')">Caisse prête</button><button class="danger" onclick="setStatus('Annulée')">Annuler</button></div><h3>Dimensions extérieures</h3>${debit.ok?`<div class="box">${debit.dims_ext.longueur} × ${debit.dims_ext.largeur} × ${debit.dims_ext.hauteur} cm</div>`:`<div class="empty">${debit.message}</div>`}<h3>Débit</h3><table class="table"><tr><th>Famille</th><th>Pièce</th><th>Qté</th><th>Longueur</th><th>Largeur</th><th>Ép.</th></tr>${(debit.lignes||[]).map(l=>`<tr><td>${l.famille}</td><td>${l.piece}</td><td>${l.quantite}</td><td>${l.longueur}</td><td>${l.largeur}</td><td>${l.epaisseur}</td></tr>`).join('')}</table>`;}
async function saveAtelier(){await api('/api/caisses/'+SELECTED,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({caissier:document.getElementById('edit_caissier').value,atelier:document.getElementById('edit_atelier').value,date_prevue:document.getElementById('edit_date').value,commentaire_atelier:document.getElementById('edit_commentaire').value})});await loadAtelier();await selectAtelier(SELECTED);}
async function setStatus(st){await api('/api/caisses/'+SELECTED+'/status',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({statut:st})});await loadAtelier();await selectAtelier(SELECTED);}
async function initSuperviseur(){const s=await api('/api/stats');document.getElementById('statsCards').innerHTML=[['Total',s.total],['À créer',s.a_creer],['En cours',s.en_cours],['Prêtes',s.pretes],['Retards',s.retards]].map(x=>`<div class="stat">${x[0]}<strong>${x[1]}</strong></div>`).join('');document.getElementById('materialStats').innerHTML=`<table class="table"><tr><th>Matière</th><th>Cumul caisses prêtes</th></tr><tr><td>CP</td><td>${s.matieres.cp_m2} m²</td></tr><tr><td>Barres</td><td>${s.matieres.barres_ml} ml</td></tr><tr><td>Chevrons</td><td>${s.matieres.chevrons_ml} ml</td></tr><tr><td>Autres</td><td>${s.matieres.autres}</td></tr></table>`;document.getElementById('typeStats').innerHTML=`<table class="table"><tr><th>Type</th><th>Nombre</th></tr>${Object.entries(s.par_type).map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>`;}
async function loadDemoData(){await api('/api/demo',{method:'POST'});location.reload();}

let PLANNING_MODE = 'week';
let CURRENT_MONTH = new Date(WEEK_START);

function startOfWeek(d){
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  x.setHours(0,0,0,0);
  return x;
}

function addDays(d,n){
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function iso(d){
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2,'0');
  const day = String(d.getDate()).padStart(2,'0');
  return `${y}-${m}-${day}`;
}

function planningDate(c){
  return c.date_prevue || c.delai_demande || '';
}

function planningStatusClass(statut){
  if(statut === 'A créer') return 'planning-a-creer';
  if(statut === 'En cours') return 'planning-en-cours';
  if(statut === 'Caisse prête') return 'planning-prete';
  if(statut === 'Annulée') return 'planning-annulee';
  return 'planning-default';
}

function planningStatusColor(statut){
  if(statut === 'A créer') return '#2563eb';
  if(statut === 'En cours') return '#f97316';
  if(statut === 'Caisse prête') return '#16a34a';
  if(statut === 'Annulée') return '#64748b';
  return '#0284c7';
}

function planningEvent(c){
  return `<div class="event ${planningStatusClass(c.statut)}" style="background:${planningStatusColor(c.statut)};color:white;">
    <b>${c.numero_dossier || c.id}</b> - colis ${c.numero_colis || '-'}<br>
    ${c.longueur || '-'}×${c.largeur || '-'}×${c.hauteur || '-'} / ${c.caissier || 'non affecté'}<br>
    ${c.charge_projet || '-'}
  </div>`;
}

async function initPlanning(){
  await loadCaisses();
  renderPlanning();
}

function setPlanningMode(mode){
  PLANNING_MODE = mode;
  renderPlanning();
}

function changePeriod(direction){
  if(PLANNING_MODE === 'month'){
    CURRENT_MONTH.setMonth(CURRENT_MONTH.getMonth() + direction);
  }else{
    WEEK_START = addDays(WEEK_START, direction * 7);
    CURRENT_MONTH = new Date(WEEK_START);
  }
  renderPlanning();
}

function changeWeek(n){
  WEEK_START = addDays(WEEK_START, n);
  CURRENT_MONTH = new Date(WEEK_START);
  renderPlanning();
}

function filteredItemsForDate(dateIso, q){
  return CAISSES
    .filter(c => planningDate(c) === dateIso)
    .filter(c => JSON.stringify(c).toLowerCase().includes(q));
}

function renderPlanning(){
  const grid = document.getElementById('planningGrid');
  if(!grid) return;

  const q = (document.getElementById('searchPlanning')?.value || '').toLowerCase();

  const btnWeek = document.getElementById('btnWeek');
  const btnMonth = document.getElementById('btnMonth');
  if(btnWeek) btnWeek.classList.toggle('active', PLANNING_MODE === 'week');
  if(btnMonth) btnMonth.classList.toggle('active', PLANNING_MODE === 'month');

  if(PLANNING_MODE === 'month'){
    renderPlanningMonth(grid, q);
  }else{
    renderPlanningWeek(grid, q);
  }
}

function renderPlanningWeek(grid, q){
  const label = document.getElementById('weekLabel');
  if(label) label.textContent = `Semaine du ${WEEK_START.toLocaleDateString('fr-FR')}`;

  grid.className = 'planning planning-week';

  grid.innerHTML = [0,1,2,3,4].map(i=>{
    const d = addDays(WEEK_START, i);
    const dayItems = filteredItemsForDate(iso(d), q);
    return `<div class="day">
      <h3>${d.toLocaleDateString('fr-FR',{weekday:'long',day:'2-digit',month:'2-digit'})}</h3>
      ${dayItems.map(planningEvent).join('') || '<div class="empty">Libre</div>'}
    </div>`;
  }).join('');
}

function renderPlanningMonth(grid, q){
  const year = CURRENT_MONTH.getFullYear();
  const month = CURRENT_MONTH.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const start = startOfWeek(firstDay);
  const end = addDays(startOfWeek(lastDay), 6);

  const label = document.getElementById('weekLabel');
  if(label) label.textContent = CURRENT_MONTH.toLocaleDateString('fr-FR',{month:'long',year:'numeric'});

  grid.className = 'planning planning-month';

  const heads = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']
    .map(h => `<div class="month-head">${h}</div>`)
    .join('');

  const days = [];
  for(let d = new Date(start); d <= end; d = addDays(d, 1)){
    days.push(new Date(d));
  }

  const cells = days.map(d=>{
    const isCurrentMonth = d.getMonth() === month;
    const dayItems = filteredItemsForDate(iso(d), q);
    return `<div class="day month-day" style="${isCurrentMonth ? '' : 'opacity:.45;'}">
      <h3>${d.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})}</h3>
      ${dayItems.map(planningEvent).join('') || '<div class="empty">Libre</div>'}
    </div>`;
  }).join('');

  grid.innerHTML = heads + cells;
}

document.addEventListener('DOMContentLoaded',()=>{const p=document.body.dataset.page;if(p==='emballage')initEmballage();if(p==='devis')initDevis();if(p==='caisserie')loadAtelier('');if(p==='superviseur')initSuperviseur();if(p==='planning')initPlanning();});

