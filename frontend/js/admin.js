// 管理后台逻辑
function showLogin() {
  document.getElementById("adminLogin").style.display = "flex";
  document.getElementById("adminDash").style.display = "none";
}
function showDash() {
  document.getElementById("adminLogin").style.display = "none";
  document.getElementById("adminDash").style.display = "block";
}

// 启动：有有效管理员令牌则直接进入后台，否则显示独立登录框
async function bootAdmin() {
  const token = getToken();
  if (token) {
    try {
      const me = await api("/api/me");
      if (me.role === "admin") {
        document.getElementById("who").textContent = `${me.display_name || me.username}（管理员）`;
        showDash();
        loadStats(); loadEquip(); loadReservations(); loadUsers(); loadRepairs(); loadNotices();
        return;
      }
    } catch (e) { /* 令牌失效，走登录 */ }
  }
  showLogin();
}

async function adminDoLogin(e) {
  e.preventDefault();
  const msg = document.getElementById("adminLoginMsg");
  msg.className = "msg";
  try {
    const data = await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("adminUser").value.trim(),
        password: document.getElementById("adminPwd").value,
      }),
    });
    setAuth(data.token, data.user);
    msg.className = "msg ok";
    msg.textContent = "登录成功，正在进入后台…";
    bootAdmin();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = err.message;
  }
  return false;
}

function switchPanel(p) {
  document.querySelectorAll(".tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.p === p));
  document.querySelectorAll(".panel").forEach((el) => el.classList.toggle("active", el.id === "p-" + p));
  if (p === "board") loadStats(true);
  if (p === "users") loadUsers();
  if (p === "repairs") loadRepairs();
  if (p === "notice") loadNotices();
}

// 统计卡片
async function loadStats(refreshBoard) {
  const s = await api("/api/stats");
  document.getElementById("stEquip").textContent = s.total_equipment;
  document.getElementById("stUsers").textContent = s.total_users;
  document.getElementById("stRes").textContent = s.total_reservations;
  document.getElementById("stPending").textContent = s.by_status.pending || 0;
  document.getElementById("stPendingUsers").textContent = s.pending_users || 0;
  // 待处理报修角标（借鉴毕设待办提醒）
  const badge = document.getElementById("repairBadge");
  if (s.pending_repairs > 0) {
    badge.style.display = "inline-block";
    badge.textContent = s.pending_repairs;
  } else {
    badge.style.display = "none";
  }
  if (refreshBoard) renderBoard(s);
}

// 设备管理
async function loadEquip() {
  const kw = document.getElementById("eqKw").value.trim();
  const status = document.getElementById("eqStatus").value;
  const list = await api(`/api/equipment?kw=${encodeURIComponent(kw)}&status=${status}`);
  const body = document.getElementById("equipBody");
  if (!list.length) { body.innerHTML = `<tr><td colspan="8" class="empty">暂无设备</td></tr>`; return; }
  body.innerHTML = list.map((e) => `
    <tr>
      <td>${e.id}</td>
      <td>${esc(e.name)}</td>
      <td>${esc(e.category || "其他")}</td>
      <td>${esc(e.model)}</td>
      <td>${esc(e.location)}</td>
      <td>${equipTag(e.status)}</td>
      <td>${esc(e.manager)}</td>
      <td>
        <button class="btn sm" onclick="openEquipModal(${e.id})">编辑</button>
        <button class="btn sm danger" onclick="deleteEquip(${e.id})">删除</button>
      </td>
    </tr>`).join("");
}

function openEquipModal(id) {
  const m = document.getElementById("eqModal");
  document.getElementById("eqMsg").className = "msg";
  if (id) {
    api(`/api/equipment`).then((list) => {
      const e = list.find((x) => x.id === id);
      if (!e) return;
      document.getElementById("eqModalTitle").textContent = "编辑设备";
      document.getElementById("eqId").value = e.id;
      document.getElementById("eqName").value = e.name;
      document.getElementById("eqCategory").value = e.category || "";
      document.getElementById("eqModel").value = e.model || "";
      document.getElementById("eqLocation").value = e.location || "";
      document.getElementById("eqState").value = e.status;
      document.getElementById("eqManager").value = e.manager || "";
      document.getElementById("eqDesc").value = e.description || "";
    });
  } else {
    document.getElementById("eqModalTitle").textContent = "新增设备";
    ["eqId", "eqName", "eqCategory", "eqModel", "eqLocation", "eqManager", "eqDesc"].forEach((i) => (document.getElementById(i).value = ""));
    document.getElementById("eqState").value = "available";
  }
  m.classList.add("show");
}
function closeEqModal() { document.getElementById("eqModal").classList.remove("show"); }

async function saveEquip() {
  const id = document.getElementById("eqId").value;
  const payload = {
    name: document.getElementById("eqName").value.trim(),
    category: document.getElementById("eqCategory").value.trim() || "其他",
    model: document.getElementById("eqModel").value.trim(),
    location: document.getElementById("eqLocation").value.trim(),
    status: document.getElementById("eqState").value,
    manager: document.getElementById("eqManager").value.trim(),
    description: document.getElementById("eqDesc").value.trim(),
  };
  const msg = document.getElementById("eqMsg");
  if (!payload.name) { msg.className = "msg err"; msg.textContent = "设备名称必填"; return; }
  try {
    if (id) {
      await api(`/api/equipment/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api(`/api/equipment`, { method: "POST", body: JSON.stringify(payload) });
    }
    closeEqModal();
    loadEquip(); loadStats();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = err.message;
  }
}

async function deleteEquip(id) {
  if (!confirm(`确认删除设备 #${id}？`)) return;
  try {
    await api(`/api/equipment/${id}`, { method: "DELETE" });
    loadEquip(); loadStats();
  } catch (err) { alert(err.message); }
}

// 预约审批
async function loadReservations() {
  const kw = document.getElementById("resKw").value.trim();
  const status = document.getElementById("resStatus").value;
  const list = await api(`/api/reservations?kw=${encodeURIComponent(kw)}&status=${status}`);
  const body = document.getElementById("resBody");
  if (!list.length) { body.innerHTML = `<tr><td colspan="9" class="empty">暂无预约</td></tr>`; return; }
  body.innerHTML = list.map((r) => {
    let acts = "-";
    if (r.status === "pending") {
      acts = `<button class="btn sm primary" onclick="approve(${r.id})">通过</button>
              <button class="btn sm danger" onclick="openRejModal(${r.id})">驳回</button>`;
    } else if (r.status === "approved") {
      acts = `<button class="btn sm" onclick="checkin(${r.id})">登录设备</button>
              <button class="btn sm" onclick="complete(${r.id})">标记完成</button>
              <button class="btn sm danger" onclick="cancel(${r.id})">取消</button>`;
    } else if (r.status === "in_use") {
      acts = `<button class="btn sm primary" onclick="checkout(${r.id})">结束使用</button>
              <button class="btn sm danger" onclick="cancel(${r.id})">取消</button>`;
    }
    return `<tr>
      <td>${r.id}</td>
      <td>${esc(r.equipment_name)}</td>
      <td>${esc(r.user_name)}</td>
      <td>${userTypeTag(r.user_type)}</td>
      <td>${esc(r.start_time)}</td>
      <td>${esc(r.end_time)}</td>
      <td>${esc(r.purpose)}</td>
      <td>${resTag(r.status)}</td>
      <td>${acts}</td>
    </tr>`;
  }).join("");
}

// 账号管理（借鉴佰能「用户管理」）
async function loadUsers() {
  const kw = document.getElementById("uKw").value.trim();
  const ut = document.getElementById("uType").value;
  const st = document.getElementById("uStatus").value;
  const list = await api(`/api/users?kw=${encodeURIComponent(kw)}&user_type=${ut}&status=${st}`);
  const body = document.getElementById("userBody");
  if (!list.length) { body.innerHTML = `<tr><td colspan="9" class="empty">暂无用户</td></tr>`; return; }
  body.innerHTML = list.map((u) => {
    const org = u.user_type === "external"
      ? `${esc(u.org_name || "-")}${u.org_type ? "（" + esc(u.org_type) + "）" : ""}`
      : esc(u.department || "-");
    const idinfo = u.user_type === "external"
      ? `导师：${esc(u.supervisor || "-")}`
      : `学号：${esc(u.student_id || "-")}${u.supervisor ? " · 导师：" + esc(u.supervisor) : ""}`;
    let acts = "-";
    if (u.status === "pending") {
      acts = `<button class="btn sm primary" onclick="approveUser(${u.id})">激活</button>
              <button class="btn sm danger" onclick="rejectUser(${u.id})">驳回</button>`;
    } else {
      const toggle = u.status === "disabled"
        ? `<button class="btn sm" onclick="toggleUser(${u.id})">启用</button>`
        : `<button class="btn sm danger" onclick="toggleUser(${u.id})">禁用</button>`;
      acts = `${toggle}<button class="btn sm" onclick="openPwdModal(${u.id}, '${esc(u.real_name || u.username)}')">重置密码</button>`;
    }
    return `<tr>
      <td>${u.id}</td>
      <td>${esc(u.username)}</td>
      <td>${esc(u.real_name || "-")}</td>
      <td>${userTypeTag(u.user_type)}</td>
      <td>${org}</td>
      <td>${idinfo}</td>
      <td>${userStatusTag(u.status)}</td>
      <td>${esc(u.created_at || "-")}</td>
      <td>${acts}</td>
    </tr>`;
  }).join("");
}

async function approveUser(id) {
  try {
    const r = await api(`/api/users/${id}/approve`, { method: "POST" });
    alert(r.message); loadUsers(); loadStats();
  } catch (err) { alert(err.message); }
}
async function rejectUser(id) {
  if (!confirm(`确认驳回该用户的注册申请？驳回后该账号将无法登录。`)) return;
  try {
    await api(`/api/users/${id}/reject`, { method: "POST" });
    loadUsers(); loadStats();
  } catch (err) { alert(err.message); }
}
async function toggleUser(id) {
  try {
    const r = await api(`/api/users/${id}/toggle`, { method: "POST" });
    alert(r.message); loadUsers(); loadStats();
  } catch (err) { alert(err.message); }
}
function openPwdModal(id, name) {
  document.getElementById("pwdUid").value = id;
  document.getElementById("pwdUserName").textContent = name;
  document.getElementById("pwdNew").value = "";
  document.getElementById("pwdModal").classList.add("show");
}
function closePwdModal() { document.getElementById("pwdModal").classList.remove("show"); }
async function confirmResetPwd() {
  const id = document.getElementById("pwdUid").value;
  const np = document.getElementById("pwdNew").value;
  if (np.length < 6) { alert("新密码至少 6 位"); return; }
  try {
    const r = await api(`/api/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ new_password: np }) });
    alert(r.message); closePwdModal();
  } catch (err) { alert(err.message); }
}

async function approve(id) {
  try { await api(`/api/reservations/${id}/approve`, { method: "POST", body: JSON.stringify({ note: "" }) }); loadReservations(); loadStats(); }
  catch (err) { alert(err.message); }
}
function openRejModal(id) {
  document.getElementById("rejRid").value = id;
  document.getElementById("rejId").textContent = id;
  document.getElementById("rejNote").value = "";
  document.getElementById("rejModal").classList.add("show");
}
function closeRejModal() { document.getElementById("rejModal").classList.remove("show"); }
async function confirmReject() {
  const id = document.getElementById("rejRid").value;
  try {
    await api(`/api/reservations/${id}/reject`, { method: "POST", body: JSON.stringify({ note: document.getElementById("rejNote").value.trim() }) });
    closeRejModal(); loadReservations(); loadStats();
  } catch (err) { alert(err.message); }
}
async function complete(id) {
  try { await api(`/api/reservations/${id}/complete`, { method: "POST" }); loadReservations(); loadStats(); }
  catch (err) { alert(err.message); }
}
async function cancel(id) {
  if (!confirm("确认取消该预约？")) return;
  try { await api(`/api/reservations/${id}/cancel`, { method: "POST" }); loadReservations(); loadStats(); }
  catch (err) { alert(err.message); }
}
async function checkin(id) {
  if (!confirm("确认代预约人登录设备？")) return;
  try { await api(`/api/reservations/${id}/checkin`, { method: "POST" }); loadReservations(); loadStats(); }
  catch (err) { alert(err.message); }
}
async function checkout(id) {
  if (!confirm("确认结束该设备使用？")) return;
  try { await api(`/api/reservations/${id}/checkout`, { method: "POST" }); loadReservations(); loadStats(); }
  catch (err) { alert(err.message); }
}

// 设备报修（借鉴毕设设备报障流程）
const REPAIR_STATUS = { pending: "待处理", handling: "处理中", fixed: "已修复", closed: "已关闭" };

function repairTag(s) {
  const cls = { pending: "warn", handling: "info", fixed: "ok", closed: "muted" }[s] || "muted";
  return `<span class="tag ${cls}">${REPAIR_STATUS[s] || s}</span>`;
}

async function loadRepairs() {
  const status = document.getElementById("rpStatus").value;
  const r = await api(`/api/repairs?status=${status}`);
  const body = document.getElementById("repairAdminBody");
  const list = r.list || [];
  window._repairList = list; // 供处理弹窗读取设备名
  if (!list.length) { body.innerHTML = `<tr><td colspan="7" class="empty">暂无报修记录</td></tr>`; return; }
  body.innerHTML = list.map((x) => {
    let acts = "-";
    if (x.status === "pending" || x.status === "handling") {
      acts = `<button class="btn sm primary" onclick="openRpHandleModal(${x.id})">处理</button>`;
    }
    return `<tr>
      <td>${x.id}</td>
      <td>${esc(x.equipment_name)}</td>
      <td>${esc(x.user_name || "-")}</td>
      <td>${esc(x.issue)}</td>
      <td>${repairTag(x.status)}</td>
      <td>${esc(x.created_at)}</td>
      <td>${acts}</td>
    </tr>`;
  }).join("");
}

function openRpHandleModal(id) {
  const list = (window._repairList || []);
  const x = list.find((r) => r.id === id);
  document.getElementById("rpHandleRid").value = id;
  document.getElementById("rpHandleId").textContent = id;
  document.getElementById("rpHandleEq").textContent = x ? x.equipment_name : "";
  document.getElementById("rpHandleNote").value = "";
  document.getElementById("rpMsg").className = "msg";
  document.getElementById("rpHandleModal").classList.add("show");
}
function closeRpHandleModal() { document.getElementById("rpHandleModal").classList.remove("show"); }

async function submitRpHandle(st) {
  const rid = document.getElementById("rpHandleRid").value;
  const msg = document.getElementById("rpMsg");
  try {
    const r = await api(`/api/repairs/${rid}/handle`, {
      method: "PUT",
      body: JSON.stringify({ status: st, note: document.getElementById("rpHandleNote").value.trim() }),
    });
    closeRpHandleModal();
    alert(r.message);
    loadRepairs(); loadStats();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = err.message;
  }
}

// 通知公告（借鉴毕设公告模块）
async function loadNotices() {
  // 管理员看全部（含停用）：先拉全部公告
  const r = await api(`/api/announcements`);
  const all = r.list || [];
  window._allNotices = all;
  const body = document.getElementById("noticeBody");
  if (!all.length) { body.innerHTML = `<tr><td colspan="6" class="empty">暂无公告，点击右上角发布第一条</td></tr>`; return; }
  body.innerHTML = all.map((a) => `<tr>
    <td>${a.id}</td>
    <td>${esc(a.title)}</td>
    <td>${esc(a.content || "-")}</td>
    <td>${a.active ? `<span class="tag ok">展示中</span>` : `<span class="tag muted">已停用</span>`}</td>
    <td>${esc(a.created_at)}</td>
    <td>
      <button class="btn sm" onclick="toggleNotice(${a.id})">${a.active ? "停用" : "启用"}</button>
      <button class="btn sm danger" onclick="deleteNotice(${a.id})">删除</button>
    </td>
  </tr>`).join("");
}

function openNoticeModal() {
  document.getElementById("ntTitle").value = "";
  document.getElementById("ntContent").value = "";
  document.getElementById("ntMsg").className = "msg";
  document.getElementById("noticeModal").classList.add("show");
}
function closeNoticeModal() { document.getElementById("noticeModal").classList.remove("show"); }

async function saveNotice() {
  const title = document.getElementById("ntTitle").value.trim();
  const msg = document.getElementById("ntMsg");
  if (!title) { msg.className = "msg err"; msg.textContent = "公告标题不能为空"; return; }
  try {
    await api("/api/announcements", {
      method: "POST",
      body: JSON.stringify({ title, content: document.getElementById("ntContent").value.trim() }),
    });
    closeNoticeModal();
    loadNotices();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = err.message;
  }
}

async function toggleNotice(id) {
  try {
    await api(`/api/announcements/${id}/toggle`, { method: "PUT" });
    loadNotices();
  } catch (err) { alert(err.message); }
}
async function deleteNotice(id) {
  if (!confirm(`确认删除公告 #${id}？`)) return;
  try {
    await api(`/api/announcements/${id}`, { method: "DELETE" });
    loadNotices();
  } catch (err) { alert(err.message); }
}

// 数据看板
function renderBoard(s) {
  const maxTop = Math.max(1, ...s.top_equipment.map((x) => x.c));
  document.getElementById("topEquip").innerHTML = s.top_equipment.length
    ? s.top_equipment.map((x) => `
      <div class="bar-row"><div class="name" title="${esc(x.name)}">${esc(x.name)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${(x.c / maxTop) * 100}%"></div></div>
      <div class="num">${x.c}</div></div>`).join("")
    : `<div class="empty">暂无数据</div>`;

  const order = ["pending", "approved", "in_use", "rejected", "cancelled", "used"];
  const maxS = Math.max(1, ...order.map((k) => s.by_status[k] || 0));
  document.getElementById("statusDist").innerHTML = order.map((k) => {
    const c = s.by_status[k] || 0;
    return `<div class="bar-row"><div class="name">${RES_STATUS[k]}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${(c / maxS) * 100}%"></div></div>
      <div class="num">${c}</div></div>`;
  }).join("");

  const eqOrder = ["available", "maintenance", "disabled"];
  const maxE = Math.max(1, ...eqOrder.map((k) => s.equip_status[k] || 0));
  document.getElementById("equipDist").innerHTML = eqOrder.map((k) => {
    const c = s.equip_status[k] || 0;
    return `<div class="bar-row"><div class="name">${EQUIP_STATUS[k]}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${(c / maxE) * 100}%"></div></div>
      <div class="num">${c}</div></div>`;
  }).join("");

  const rb = document.getElementById("recentBody");
  if (!s.recent.length) { rb.innerHTML = `<tr><td colspan="5" class="empty">暂无预约</td></tr>`; return; }
  rb.innerHTML = s.recent.map((r) => `<tr>
    <td>${esc(r.equipment_name)}</td><td>${esc(r.user_name)}</td>
    <td>${userTypeTag(r.user_type)}</td>
    <td>${esc(r.start_time)} ~ ${esc(r.end_time)}</td><td>${resTag(r.status)}</td></tr>`).join("");

  const ib = document.getElementById("inUseBody");
  if (!s.in_use.length) { ib.innerHTML = `<tr><td colspan="5" class="empty">当前没有设备在使用中</td></tr>`; return; }
  ib.innerHTML = s.in_use.map((r) => `<tr>
    <td>${esc(r.equipment_name)}</td><td>${esc(r.user_name)}</td>
    <td>${userTypeTag(r.user_type)}</td>
    <td>${esc(r.checkin_at || "-")}</td>
    <td>${esc(r.start_time)} ~ ${esc(r.end_time)}</td></tr>`).join("");
}

// 初始化
bootAdmin();
