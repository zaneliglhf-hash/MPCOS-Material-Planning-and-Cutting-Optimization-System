'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rich = s => esc(s).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
const states = {draft:'草稿',queued:'排队中',running:'计算中',pending:'待负责人复核',approved:'已复核通过',rejected:'已退回',failed:'计算失败',interrupted:'任务中断'};
const events = {order_created:'建立订单',parameters_confirmed:'确认参数并提交',plan_generated:'生成方案',plan_approved:'复核通过',plan_rejected:'退回修改',plan_failed:'计算失败',task_interrupted:'启动时恢复中断记录',chat_ok:'Agent 整理需求',chat_error:'模型请求未完成'};
let moreOrders = false, searchTimer, workspaceEpoch = 0, ordersEpoch = 0;
let me, orders = [], current = null, detail = null, selected = null, poll = null, toastTimer, requestKey = null;
function toast(text) { $('#toast').textContent=text; $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,6000); }
async function api(path, data) {
 const session = me;
 const options = {credentials:'same-origin',headers:{'Content-Type':'application/json','X-MPCOS-Client':'workbench','X-CSRF-Token':me?.csrf || ''}};
 if(data !== undefined) {options.method='POST';options.body=JSON.stringify(data);}
 const r=await fetch('/api'+path,options); const value=await r.json();
 if(!r.ok) {if(r.status===401 && path!=='/login' && me===session) loginPage(); throw Error(typeof value.detail==='string'?value.detail:'请检查必填项、输入格式和确认勾选。');} return value;
}
const badge = status => `<span class="badge ${esc(status || 'draft')}">${states[status] || '草稿'}</span>`;
const date = timestamp => new Date(timestamp*1000).toLocaleString('zh-CN',{hour12:false});
function loginPage() {
 workspaceEpoch++; ordersEpoch++; me=null; current=null; detail=null; selected=null; requestKey=null; clearTimeout(poll);
 $('#app').innerHTML=`<main class="login"><section class="login-brand"><div class="brand">MPCOS<small>MANUFACTURING INTELLIGENCE</small></div><div><div class="eyebrow">从订单，到可核对的下料方案</div><h1>让每一次下料，<br>有据可循。</h1><p>用中文整理需求，以确定性计算生成方案。<br>参数确认、版本留档、人工复核，在一个工作台完成。</p><div class="bars" aria-hidden="true"><i></i><i></i><i></i><i></i></div></div><p>内部工作台 · 型材长度下料</p></section><form id="login" class="login-form"><div class="eyebrow">WORKSPACE ACCESS</div><h2>登录工作台</h2><p class="muted">使用维护人员为你开通的内部账号。</p><label for="username">账号</label><input id="username" name="username" autocomplete="username" required maxlength="40"><label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="256"><button>进入工作台 →</button><div id="login-error"></div><p class="muted">员工提交订单 · 负责人复核方案<br>账号问题请联系内部维护人员。</p></form></main>`;
 $('#login').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{await api('/login',{username:$('#username').value,password:$('#password').value});me=await api('/me');await shell();}catch(err){$('#login-error').textContent=err.message;button.disabled=false;}};
}
async function shell() {
 $('#app').innerHTML=`<div class="shell"><aside class="sidebar"><div class="brand">MPCOS<small>CUTTING WORKBENCH</small></div><button class="new" data-action="new">＋ 新建订单</button><div class="eyebrow">${me.role==='manager'?'全部订单 / 复核中心':'我的订单'}</div><input id="search" placeholder="搜索订单、材质、规格" aria-label="搜索订单"><nav class="order-list" id="orders"></nav><div class="account"><button data-action="logout">退出</button><strong>${esc(me.username)}</strong><br><span>${me.role==='manager'?'负责人':'员工'} · 内部账号</span></div></aside><main class="main"><div class="topline"><span>WORKSPACE / 下料订单</span><span class="live">内部工作台 · <span id="usage"></span></span></div><div id="workspace"></div></main></div>`;
 $('#search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>refreshOrders().catch(e=>toast(e.message)),250);};await refreshOrders();
 $('#workspace').innerHTML=`<div class="hero-empty"><div class="eyebrow">ONE ORDER. EVERY STEP.</div><h1>从一笔订单开始，<br>把需求变成可核对的方案。</h1><p>为同一材质、同一截面规格建立订单。Agent 会帮你整理中文需求，补齐参数，再交由计算工具生成方案。</p><button data-action="new">建立第一笔订单 →</button><div class="notice">参数经人工确认后计算；每次方案单独留档，交由负责人复核。</div></div>`;
 const match=location.hash.match(/^#order\/([a-f0-9]{32})$/); if(match) {try {await openOrder(match[1]);} catch(err) {toast(err.message);}}
}
async function refreshOrders(append=false){const epoch=++ordersEpoch,session=me;const query=$('#search')?.value || '';const data=await api('/orders?query='+encodeURIComponent(query)+'&offset='+(append?orders.length:0));if(!me || me!==session || epoch!==ordersEpoch || query!==($('#search')?.value || ''))return;orders=append?[...orders,...data.orders]:data.orders;moreOrders=data.has_more;$('#usage').textContent=`24h 模型请求 ${data.daily_model_calls}/${data.daily_limit}`;drawOrders();}
function drawOrders(){const query=($('#search')?.value || '').toLowerCase();$('#orders').innerHTML=orders.filter(o=>[o.title,o.material,o.profile].join(' ').toLowerCase().includes(query)).map(o=>`<button class="order-item ${o.id===current?'active':''}" data-order="${o.id}"><strong>${esc(o.title)}</strong><span>${esc(o.material)} · ${esc(o.profile)}<br>${states[o.status] || '草稿'} ${o.version?'· V'+o.version:''}</span></button>`).join('') || '<p class="muted">暂无匹配订单</p>';if(moreOrders)$('#orders').insertAdjacentHTML('beforeend','<button class="order-item" data-action="more">加载更早的订单 ↓</button>');}
function newOrder(){const overlay=document.createElement('div');overlay.className='overlay';overlay.innerHTML=`<form id="new-order" class="modal"><div class="eyebrow">NEW ORDER</div><h2>建立下料订单</h2><p class="muted">一笔订单只处理一种材质和一种截面规格。不同规格请分别建单。</p><label for="title">订单名称</label><input id="title" required maxlength="100" placeholder="例如：支架订单 · A组"><div class="two"><div><label for="material">材质</label><input id="material" required maxlength="100" placeholder="例如：Q235B"></div><div><label for="profile">截面规格</label><input id="profile" required maxlength="100" placeholder="例如：方管 40×40×3 mm"></div></div><div class="form-actions"><button type="button" class="secondary" data-action="close-modal">取消</button><button>建立订单</button></div></form>`;document.body.append(overlay);$('#title').focus();$('#new-order').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{const order=await api('/orders',{title:$('#title').value,material:$('#material').value,profile:$('#profile').value});overlay.remove();await refreshOrders();await openOrder(order.id);}catch(err){toast(err.message);e.submitter.disabled=false;}};}
async function refreshDetail(oid, epoch) {
 if(!me || current!==oid || workspaceEpoch!==epoch) return false;
 const next = await api('/orders/'+oid);
 if(!me || current!==oid || workspaceEpoch!==epoch) return false;
 detail=next; return true;
}
async function openOrder(oid) {
 const epoch=++workspaceEpoch;
 history.replaceState(null,'','#order/'+oid); clearTimeout(poll);
 current=oid; selected=null; requestKey=null; detail=null;
 $('#workspace').innerHTML='<div class="empty" role="status">正在读取订单…</div>';
 drawOrders();
 try {
  if(!await refreshDetail(oid,epoch)) return;
  drawDetail(); schedulePoll();
 } catch(err) {
  if(current!==oid || workspaceEpoch!==epoch) return;
  $('#workspace').innerHTML='<p class="error">'+esc(err.message)+'</p>';
  throw err;
 }
}
function invalidateConfirmation(event) {
 requestKey=null;
 if(event.target.id!=='confirm') $('#confirm').checked=false;
}
function lockForms(...selectors) {
 const controls=selectors.flatMap(selector=>Array.from($(selector)?.querySelectorAll('input,textarea,button') || []));
 const disabled=controls.map(control=>control.disabled);
 controls.forEach(control=>control.disabled=true);
 return ()=>controls.forEach((control,index)=>control.disabled=disabled[index]);
}
function drawDetail(){const o=detail.order,v=detail.versions[0],p=o.proposal || v?.parameters || {};$('#workspace').innerHTML=`<header class="heading"><div><div class="eyebrow">ORDER / ${o.id.slice(0,8)}</div><h1>${esc(o.title)}</h1><div class="metadata"><span>${esc(o.material)} · ${esc(o.profile)}</span><span>提交人 ${esc(o.owner_name)}</span><span>${date(o.created)}</span></div></div>${badge(v?.status)}</header><div class="workflow"><span class="done">01　建立订单</span><span class="${o.proposal || v?'done':''}">02　核对参数</span><span class="${v?.result?'done':''}">03　计算留档</span><span class="${v?.status==='approved'?'done':''}">04　人工复核</span></div><div class="content-grid ${me.role==='manager' && !o.can_edit?'manager-view':''}"><div><section class="panel"><div class="panel-title"><h2>订单助理</h2><span class="number">AGENT</span></div><div class="chat-intro">用中文描述零件长度和数量、可用原料长度、锯缝，以及经确认的最大叠切根数。<br>Agent 整理的参数会出现在右侧，需你核对后计算。</div><div id="messages" class="messages">${o.messages.map(m=>`<div class="message ${m.role}"><small>${m.role==='user'?'需求':'AGENT · 参数草稿'}</small>${rich(m.content)}</div>`).join('')}</div>${o.can_edit?'<form id="chat" class="chat-form"><label for="message">描述需求或补充参数</label><textarea id="message" required maxlength="2000" placeholder="例如：需要 1200 mm 的零件 6 件……请整理参数。"></textarea><button>发送给 Agent ↑</button></form>':'<p class="muted">负责人可查看完整需求。参数修改由订单提交人操作。</p>'}<p class="hint">模型仅整理草稿；方案和审批状态以计算记录为准。<br>对话会发送到已配置的 DeepSeek；请仅输入获准处理的业务信息。订单请求 ${o.model_calls}/40。</p></section><section class="panel audit-panel"><h2>操作记录</h2><div id="audit"></div></section></div><div><section class="panel parameters-panel"><div class="panel-title"><h2>参数核对</h2><span class="number">CONFIRM & GENERATE</span></div><p class="muted">所有长度单位为 mm。工艺参数需要明确来源；修改后将生成新版本。</p><form id="generate"><label for="demand">成品长度 × 数量（每行一项）</label><textarea id="demand" required placeholder="1200 × 6&#10;1800 × 4" ${o.can_edit?'':'disabled'}>${esc(Object.entries(p.demand || {}).map(([l,n])=>l+' × '+n).join('\n'))}</textarea><div class="two"><div><label for="stocks">可用原料长度（逗号分隔）</label><input id="stocks" required value="${esc((p.stock_lengths_mm || []).join(', '))}" placeholder="填写已确认的可用长度" ${o.can_edit?'':'disabled'}></div><div><label for="kerf">锯缝 mm</label><input id="kerf" type="number" min="0" max="100" step="1" required value="${esc(p.kerf_mm ?? '')}" ${o.can_edit?'':'disabled'}></div></div><div class="two"><div><label for="stack">设备最大叠切根数</label><input id="stack" type="number" min="1" max="100" step="1" required value="${esc(p.max_stack ?? '')}" ${o.can_edit?'':'disabled'}></div><div><label for="source">工艺参数来源 / 确认依据</label><input id="source" required minlength="3" maxlength="500" placeholder="如：设备作业卡版本、确认人员" value="${esc(v?.process_source || '')}" ${o.can_edit?'':'disabled'}></div></div>${Object.keys(p).some(k=>['min_bars','max_bars','baseline_batches','baseline_strokes'].includes(k))?`<details><summary>沿用的计算约束</summary><p class="muted">${esc(['min_bars','max_bars','baseline_batches','baseline_strokes'].filter(k=>p[k]!==undefined).map(k=>k+' = '+p[k]).join('；'))}。如需变更，请在对话中明确说明。</p></details>`:''}${o.can_edit?'<label class="checks"><input type="checkbox" id="confirm" required><span>我已核对为同材质、同规格的一组，长度、数量和工艺参数有依据。此次生成仅供复核。</span></label><div class="form-actions"><button id="generate-button">确认参数，生成'+(v?'新版本':'方案')+' →</button></div>':''}</form></section><section class="panel" id="results"></section><div class="notice">${esc(detail.notice)}</div></div></div>`;
 if(o.can_edit){$('#chat').onsubmit=chatSubmit;$('#generate').onsubmit=generateSubmit;$('#generate').oninput=invalidateConfirmation;}drawResults();drawAudit();const msgs=$('#messages');msgs.scrollTop=msgs.scrollHeight;}
function drawAudit(){$('#audit').innerHTML=detail.audit.map(a=>{let extra='';try{const d=JSON.parse(a.details);extra=d.note || '';}catch{}return `<div class="audit"><time>${date(a.at)}</time><b>${events[a.event] || esc(a.event)}</b><br>${esc(a.actor)}${extra?' · '+esc(extra):''}</div>`;}).join('');}
function drawResults(){const versions=detail.versions;const v=versions.find(x=>x.id===selected) || versions[0];if(!v){$('#results').innerHTML='<h2>方案与复核</h2><div class="empty">等待第一份方案<br><span class="muted">核对参数后，图纸、采购统计和版本记录会保存在这里。</span></div>';return;}
 selected=v.id;const r=v.result,s=r?.summary;$('#results').innerHTML=`<div class="version-head"><h2>方案与复核</h2><select id="version" aria-label="选择方案版本">${versions.map(x=>`<option value="${x.id}" ${x.id===selected?'selected':''}>V${x.number} · ${states[x.status]}</option>`).join('')}</select></div>${badge(v.status)} <span class="muted">${date(v.created)}</span>${v.error?`<p class="error">${esc(v.error)}</p>`:''}${s?`<div class="metrics"><div class="metric"><b>${s.bar_count}</b><small>采购原料 / 根</small></div><div class="metric"><b>${s.batch_count}</b><small>上下料 / 批</small></div><div class="metric"><b>${Number(s.utilization_percent).toFixed(2)}%</b><small>材料利用率</small></div></div><p class="hint">优化优先级：上下料批次 → 落锯次数 → 采购长度。<br>材料利用率不代表以节料为第一目标。</p><div class="summary-line">落锯 <strong>${s.saw_strokes}</strong> 次 · 成品总长度 <strong>${s.finished_length_mm}</strong> mm<br>采购 ${s.total_stock_mm} mm · 锯缝 ${s.kerf_total_mm} mm · 余料 ${s.offcut_mm} mm<br>原料采购：${Object.entries(s.procurement || {}).map(([l,n])=>l+' mm × '+n+' 根').join('，')}</div><div class="downloads"><a href="/api/orders/${current}/versions/${v.id}/record" target="_blank" rel="noopener">↓ 版本复核记录</a>${r.files.map((f,i)=>`<a href="/api/orders/${current}/versions/${v.id}/files/${i}" target="_blank" rel="noopener">↓ ${esc(f.kind==='images'?'A3 图纸 '+(i):f.kind.toUpperCase())}</a>`).join('')}</div><details><summary>查看逐批切割明细</summary><div class="table-wrap"><table><thead><tr><th>批次</th><th>原料 × 根数</th><th>每根切割 mm</th><th>每根余料</th></tr></thead><tbody>${r.batches.map(b=>`<tr><td>${b.batch}</td><td>${b.stock_length_mm} × ${b.bars}</td><td>${esc(b.cuts_mm.join(' + '))}</td><td>${b.offcut_per_bar_mm} mm</td></tr>`).join('')}</tbody></table></div></details>`:'<p class="muted">任务状态会自动更新。关闭页面不影响后台计算，重新登录可继续查看。</p>'}<details><summary>本版本确认参数与来源</summary><p class="muted">确认人：${esc(v.actor_name)}<br>依据：${esc(v.process_source)}<br>需求：${esc(Object.entries(v.parameters.demand).map(([l,n])=>l+' × '+n).join('；'))}<br>原料：${esc(v.parameters.stock_lengths_mm.join(', '))} mm；锯缝：${v.parameters.kerf_mm} mm；最大叠切：${v.parameters.max_stack} 根</p></details>${v.reviewer_name?`<div class="notice">复核人 ${esc(v.reviewer_name)} · ${date(v.reviewed_at)}<br>${esc(v.review_note)}</div>`:''}${me.role==='manager' && v.status==='pending' && v.id===versions[0].id && v.actor!==me.id?'<form id="review"><label for="review-note">复核意见（通过和退回均须填写）</label><textarea id="review-note" required minlength="3" maxlength="1000" placeholder="记录检查结果或需要修改的具体问题"></textarea><label class="checks"><input id="review-confirm" type="checkbox" required><span>我已检查本版本参数、工艺适用性和生成资料，并承担本次复核。</span></label><div class="form-actions"><button value="rejected" class="danger">退回修改</button><button value="approved">复核通过</button></div></form>':''}`;
 $('#version').onchange=e=>{selected=e.target.value;drawResults();};if($('#review'))$('#review').onsubmit=reviewSubmit;}
async function chatSubmit(e) {
 e.preventDefault(); const oid=current,epoch=workspaceEpoch,button=e.submitter;
 const text=$('#message').value, unlock=lockForms('#chat','#generate');
 button.textContent='正在整理需求…';
 try {
  const r=await api('/orders/'+oid+'/chat',{text});
  if(!await refreshDetail(oid,epoch)) return;
  drawDetail(); await refreshOrders(); if(r.status==='error') toast(r.answer);
 } catch(err) {if(current===oid && workspaceEpoch===epoch) toast(err.message);}
 finally {unlock(); button.textContent='发送给 Agent ↑';}
}
function integer(s){if(!/^\d+$/.test(s.trim()))throw Error('长度和数量需要填写整数。');return Number(s.trim());}
async function generateSubmit(e){e.preventDefault();const oid=current,epoch=workspaceEpoch;let unlock=()=>{};try{const demand={};for(const line of $('#demand').value.trim().split('\n')){const pair=line.trim().split(/\s*[×xX:*]\s*|\s+/);if(pair.length!==2)throw Error('每行请填写：长度 × 数量。');const length=integer(pair[0]),count=integer(pair[1]);if(demand[length]!==undefined)throw Error('同一长度请合并数量，只填写一行。');demand[length]=count;}
 const base=detail.order.proposal || detail.versions[0]?.parameters || {};const parameters={};for(const k of ['min_bars','max_bars','baseline_batches','baseline_strokes'])if(base[k]!==undefined)parameters[k]=base[k];Object.assign(parameters,{demand,stock_lengths_mm:$('#stocks').value.split(/[,，\s]+/).filter(Boolean).map(integer),kerf_mm:integer($('#kerf').value),max_stack:integer($('#stack').value)});
 requestKey ||= crypto.randomUUID();
 const payload={parameters,process_source:$('#source').value,confirmed:$('#confirm').checked,request_key:requestKey};
 unlock=lockForms('#chat','#generate');
 await api('/orders/'+oid+'/generate',payload);
 if(!await refreshDetail(oid,epoch)) return;
 toast('任务已提交，参数及确认来源已留档。');selected=null;drawDetail();await refreshOrders();schedulePoll();
 }catch(err){if(current===oid && workspaceEpoch===epoch)toast(err.message);}finally{unlock();}}
async function reviewSubmit(e) {
 e.preventDefault();const oid=current,epoch=workspaceEpoch,decision=e.submitter.value;
 const payload={decision,note:$('#review-note').value,confirmed:$('#review-confirm').checked};
 const unlock=lockForms('#review');
 try {
  await api('/orders/'+oid+'/versions/'+selected+'/review',payload);
  if(!await refreshDetail(oid,epoch)) return;
  drawDetail();await refreshOrders();toast(decision==='approved'?'本版本复核通过，记录已保存。':'已退回，意见已保存。');
 }catch(err){if(current===oid && workspaceEpoch===epoch)toast(err.message);}finally{unlock();}
}
function schedulePoll(){clearTimeout(poll);if(!detail?.versions.some(v=>['queued','running'].includes(v.status)))return;const oid=current,epoch=workspaceEpoch;poll=setTimeout(async()=>{try{if(!await refreshDetail(oid,epoch))return;drawResults();drawAudit();const latest=detail.versions[0];const head=$('.heading > .badge');if(head)head.outerHTML=badge(latest?.status);await refreshOrders();schedulePoll();}catch(err){toast(err.message);}},1800);}
document.addEventListener('click',async e=>{const order=e.target.closest('[data-order]');if(order){try{await openOrder(order.dataset.order);}catch(err){toast(err.message);}return;}const action=e.target.closest('[data-action]')?.dataset.action;try{if(action==='more')await refreshOrders(true);if(action==='new')newOrder();if(action==='close-modal')$('.overlay')?.remove();if(action==='logout'){await api('/logout',{});loginPage();}}catch(err){toast(err.message);}});
(async()=>{try{me=await api('/me');await shell();}catch{loginPage();}})();
