// 预约人门户逻辑
let user = requireAuth();
let favIds = new Set(); // 收藏的设备 id 集合

if (user) {
  if (user.role === "admin") { location.href = "/admin.html"; }
  else {
    const typeName = USER_TYPE[user.user_type] || "";
    document.getElementById("who").textContent = `${user.real_name || user.username}（${typeName}）`;
  }
}

function switchPanel(p) {
  document.querySelectorAll(".tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.p === p));
  document.querySelectorAll(".panel").forEach((el) => el.classList.toggle("active", el.id === "p-" + p));
  if (p === "mine") loadMine();
  if (p === "favorites") loadFavorites();
  if (p === "repairs") loadMyRepairs();
}

// 通知公告（借鉴毕设公告模块）
async function loadAnnouncements() {
  try {
    const r = await api("/api/announcements");
    const list = (r.list || []).filter((a) => a.active);
    const box = document.getElementById("announceBox");
    if (!list.length) { box.style.display = "none"; return; }
    box.innerHTML = list.map((a) =>
      `<div class="announce-item"><b>📢 ${esc(a.title)}</b><span>${esc(a.content || "")}</span></div>`).join("");
    box.style.display = "block";
  } catch (e) { /* 无公告不展示 */ }
}

// 设备分类筛选（借鉴毕设设备类别管理）
async function loadCats() {
  try {
    const r = await api("/api/equipment-categories");
    const sel = document.getElementById("bCat");
    sel.innerHTML = `<option value="">全部分类</option>` +
      (r.categories || []).map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  } catch (e) { /* 分类加载失败不阻塞 */ }
}

// 收藏状态（借鉴佰能「设备收藏」）
async function loadFavIds() {
  try {
    const r = await api("/api/favorites");
    favIds = new Set(r.ids || []);
  } catch (e) { favIds = new Set(); }
}

async function toggleFav(eid, ev) {
  if (ev) { ev.stopPropagation(); ev.preventDefault(); }
  try {
    if (favIds.has(eid)) {
      await api(`/api/favorites/${eid}`, { method: "DELETE" });
      favIds.delete(eid);
    } else {
      await api(`/api/favorites/${eid}`, { method: "POST" });
      favIds.add(eid);
    }
    // 刷新当前可见列表
    if (document.getElementById("p-browse").classList.contains("active")) loadEquip();
    else loadFavorites();
  } catch (err) { alert(err.message); }
}

function favBtn(eid) {
  const on = favIds.has(eid);
  return `<button class="fav ${on ? "on" : ""}" title="${on ? "取消收藏" : "收藏设备"}" onclick="toggleFav(${eid}, event)">${on ? "♥" : "♡"}</button>`;
}

function renderEquipTable(list, bodyId, emptyText) {
  const body = document.getElementById(bodyId);
  if (!list.length) { body.innerHTML = `<tr><td colspan="9" class="empty">${emptyText}</td></tr>`; return; }
  body.innerHTML = list.map((e) => {
    const canBook = e.status === "available";
    const btn = canBook
      ? `<button class="btn sm primary" onclick="openResModal(${e.id}, '${esc(e.name)}')">预约</button>`
      : `<span class="tag ${EQUIP_TAG[e.status]}">${EQUIP_STATUS[e.status]}</span>`;
    return `<tr>
      <td>${favBtn(e.id)}</td>
      <td><a href="javascript:void(0)" onclick="openEquipDetail(${e.id})">${esc(e.name)}</a></td>
      <td>${esc(e.category || "其他")}</td>
      <td>${esc(e.model)}</td>
      <td>${esc(e.location)}</td>
      <td>${equipTag(e.status)}</td>
      <td>${esc(e.manager)}</td>
      <td>${esc(e.description)}</td>
      <td>${btn}</td>
    </tr>`;
  }).join("");
}

// 设备详情（借鉴 NEMO Tool Details：基本信息 + 排期 + 使用历史）
let curDetail = null; // 当前查看的设备（供报修）
async function openEquipDetail(id) {
  const d = await api(`/api/equipment/${id}`);
  curDetail = d;
  document.getElementById("detailName").textContent = d.name;
  document.getElementById("detailInfo").innerHTML = `
    <div class="d-item"><span class="d-k">分类</span><span class="d-v">${esc(d.category || "其他")}</span></div>
    <div class="d-item"><span class="d-k">型号</span><span class="d-v">${esc(d.model || "-")}</span></div>
    <div class="d-item"><span class="d-k">位置</span><span class="d-v">${esc(d.location || "-")}</span></div>
    <div class="d-item"><span class="d-k">状态</span><span class="d-v">${equipTag(d.status)}</span></div>
    <div class="d-item"><span class="d-k">负责人</span><span class="d-v">${esc(d.manager || "-")}</span></div>
    <div class="d-item full"><span class="d-k">描述</span><span class="d-v">${esc(d.description || "-")}</span></div>`;
  const sch = document.getElementById("detailSchedule");
  if (!d.schedule.length) {
    sch.innerHTML = `<div class="empty">未来暂无占用时段</div>`;
  } else {
    sch.innerHTML = d.schedule.map((r) => `
      <div class="s-row ${r.status === "in_use" ? "busy" : ""}">
        <span class="s-time">${esc(r.start_time)} ~ ${esc(r.end_time)}</span>
        <span>${esc(r.user_name)}</span>${userTypeTag(r.user_type)}${resTag(r.status)}
      </div>`).join("");
  }
  const hist = document.getElementById("detailHistory");
  if (!d.usage_history.length) {
    hist.innerHTML = `<div class="empty">暂无使用记录</div>`;
  } else {
    hist.innerHTML = d.usage_history.map((r) => `
      <div class="s-row">
        <span class="s-time">${esc(r.start_time)} ~ ${esc(r.end_time)}</span>
        <span>${esc(r.user_name)}</span>${userTypeTag(r.user_type)}${resTag(r.status)}
      </div>`).join("");
  }
  document.getElementById("detailModal").classList.add("show");
}
function closeDetailModal() { document.getElementById("detailModal").classList.remove("show"); }

// 设备排期加载（预约冲突可视化，借鉴 NEMO 日历 / 佰能排期查看）
async function loadSchedule(eid) {
  const box = document.getElementById("scheduleList");
  const hint = document.getElementById("scheduleHint");
  box.innerHTML = `<div class="empty">加载排期中…</div>`;
  try {
    const d = await api(`/api/equipment/${eid}`);
    hint.textContent = `（未来 ${d.schedule.length} 个时段已被占用，请避开）`;
    if (!d.schedule.length) {
      box.innerHTML = `<div class="empty">未来暂无占用，可自由预约</div>`;
      return;
    }
    box.innerHTML = d.schedule.map((r) => `
      <div class="s-row ${r.status === "in_use" ? "busy" : ""}">
        <span class="s-time">${esc(r.start_time)} ~ ${esc(r.end_time)}</span>
        <span>${esc(r.user_name)}</span>${resTag(r.status)}
      </div>`).join("");
  } catch (err) {
    box.innerHTML = `<div class="empty">排期加载失败</div>`;
  }
}

// 设备查询
async function loadEquip() {
  const kw = document.getElementById("bKw").value.trim();
  const status = document.getElementById("bStatus").value;
  const category = document.getElementById("bCat").value;
  const list = await api(`/api/equipment?kw=${encodeURIComponent(kw)}&status=${status}&category=${encodeURIComponent(category)}`);
  renderEquipTable(list, "browseBody", "未找到设备");
}

// 我的收藏
async function loadFavorites() {
  const list = await api(`/api/equipment`);
  const favs = list.filter((e) => favIds.has(e.id));
  renderEquipTable(favs, "favBody", "还没有收藏设备，去设备查询页点 ♥ 收藏吧");
}

// 预约弹窗
function openResModal(id, name) {
  document.getElementById("resEqId").value = id;
  document.getElementById("resEqName").textContent = name;
  document.getElementById("resMsg").className = "msg";
  document.getElementById("resStart").value = "";
  document.getElementById("resEnd").value = "";
  document.getElementById("resPurpose").value = "";
  document.getElementById("resModal").classList.add("show");
  loadSchedule(id); // 打开即显示设备排期
}
function closeResModal() { document.getElementById("resModal").classList.remove("show"); }

function fmt(dt) { return dt.replace("T", " "); } // datetime-local -> 'YYYY-MM-DD HH:MM'

async function submitRes() {
  const payload = {
    equipment_id: parseInt(document.getElementById("resEqId").value, 10),
    start_time: fmt(document.getElementById("resStart").value),
    end_time: fmt(document.getElementById("resEnd").value),
    purpose: document.getElementById("resPurpose").value.trim(),
  };
  const msg = document.getElementById("resMsg");
  if (!payload.start_time || !payload.end_time) { msg.className = "msg err"; msg.textContent = "请选择起止时间"; return; }
  try {
    const r = await api("/api/reservations", { method: "POST", body: JSON.stringify(payload) });
    closeResModal();
    alert(r.message);
    loadEquip();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = err.message;
  }
}

// 我的预约（分类视图，借鉴佰能「预约记录/使用记录/申请记录」）
let mineCat = ""; // '' 全部 | active 进行中 | history 历史

function pickMineCat(v) {
  mineCat = v;
  document.querySelectorAll(".sub-tabs .sub-tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.v === v));
  loadMine();
}

async function loadMine() {
  const kw = document.getElementById("mKw").value.trim();
  const status = document.getElementById("mStatus").value;
  let list = await api(`/api/reservations/mine?kw=${encodeURIComponent(kw)}&status=${status}`);
  // 分类过滤（进行中 = 待审核/已通过/使用中；历史 = 驳回/取消/完成）
  if (mineCat === "active") {
    list = list.filter((r) => ["pending", "approved", "in_use"].includes(r.status));
  } else if (mineCat === "history") {
    list = list.filter((r) => ["rejected", "cancelled", "used"].includes(r.status));
  }
  const body = document.getElementById("mineBody");
  if (!list.length) { body.innerHTML = `<tr><td colspan="7" class="empty">暂无预约</td></tr>`; return; }
  body.innerHTML = list.map((r) => {
    let btn = "-";
    if (r.status === "pending" || r.status === "approved" || r.status === "in_use") {
      const login = r.status === "approved"
        ? `<button class="btn sm primary" onclick="checkin(${r.id})">登录设备</button>`
        : "";
      const finish = r.status === "in_use"
        ? `<button class="btn sm primary" onclick="checkout(${r.id})">结束使用</button>`
        : "";
      btn = login + finish + `<button class="btn sm danger" onclick="cancelMine(${r.id})">取消</button>`;
    }
    return `<tr>
      <td>${r.id}</td>
      <td>${esc(r.equipment_name)}</td>
      <td>${esc(r.start_time)}</td>
      <td>${esc(r.end_time)}</td>
      <td>${esc(r.purpose)}</td>
      <td>${resTag(r.status)}</td>
      <td>${btn}</td>
    </tr>`;
  }).join("");
}

async function cancelMine(id) {
  if (!confirm("确认取消该预约？")) return;
  try { await api(`/api/reservations/${id}/cancel`, { method: "POST" }); loadMine(); }
  catch (err) { alert(err.message); }
}

// 设备报修（借鉴毕设设备报障流程）
function openRepairModal() {
  if (!curDetail) return;
  document.getElementById("repairEqId").value = curDetail.id;
  document.getElementById("repairEqName").textContent = curDetail.name;
  document.getElementById("repairIssue").value = "";
  document.getElementById("repairMsg").className = "msg";
  document.getElementById("repairModal").classList.add("show");
}
function closeRepairModal() { document.getElementById("repairModal").classList.remove("show"); }

async function submitRepair() {
  const issue = document.getElementById("repairIssue").value.trim();
  const msg = document.getElementById("repairMsg");
  if (!issue) { msg.className = "msg err"; msg.textContent = "请填写故障描述"; return; }
  try {
    const r = await api("/api/repairs", {
      method: "POST",
      body: JSON.stringify({ equipment_id: parseInt(document.getElementById("repairEqId").value, 10), issue }),
    });
    closeRepairModal();
    alert(r.message);
    loadEquip();
  } catch (err) {
    msg.className = "msg err"; msg.textContent = err.message;
  }
}

const REPAIR_STATUS = { pending: "待处理", handling: "处理中", fixed: "已修复", closed: "已关闭" };

function repairTag(s) {
  const cls = { pending: "warn", handling: "info", fixed: "ok", closed: "muted" }[s] || "muted";
  return `<span class="tag ${cls}">${REPAIR_STATUS[s] || s}</span>`;
}

async function loadMyRepairs() {
  const r = await api("/api/repairs");
  const body = document.getElementById("repairBody");
  const list = r.list || [];
  if (!list.length) { body.innerHTML = `<tr><td colspan="7" class="empty">暂无报修记录</td></tr>`; return; }
  body.innerHTML = list.map((x) => `<tr>
    <td>${x.id}</td>
    <td>${esc(x.equipment_name)}</td>
    <td>${esc(x.issue)}</td>
    <td>${repairTag(x.status)}</td>
    <td>${esc(x.handler || "-")}</td>
    <td>${esc(x.handle_note || "-")}</td>
    <td>${esc(x.created_at)}</td>
  </tr>`).join("");
}

// 启动：公告 + 分类 + 收藏状态 + 设备列表
loadAnnouncements();
loadCats();
loadFavIds().then(() => loadEquip());
