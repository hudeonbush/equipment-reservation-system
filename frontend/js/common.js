// 通用前端工具：鉴权、API 请求、状态映射
const TOKEN_KEY = "ers_token";
const USER_KEY = "ers_user";

const RES_STATUS = { pending: "待审核", approved: "已通过", in_use: "使用中", rejected: "已驳回", cancelled: "已取消", used: "已完成" };
const RES_TAG = { pending: "orange", approved: "green", in_use: "inuse", rejected: "red", cancelled: "gray", used: "gray" };
const EQUIP_STATUS = { available: "可用", maintenance: "维护中", disabled: "停用" };
const EQUIP_TAG = { available: "green", maintenance: "orange", disabled: "red" };
// 三角色账号体系：用户类型 + 账号状态（借鉴高校共享平台）
const USER_TYPE = { internal: "校内用户", external: "校外用户" };
const USER_TYPE_TAG = { internal: "green", external: "inuse" };
const USER_STATUS = { active: "正常", pending: "待审核", rejected: "已驳回", disabled: "已禁用" };
const USER_STATUS_TAG = { active: "green", pending: "orange", rejected: "red", disabled: "gray" };

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function getUser() { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch (e) { return null; } }
function setAuth(token, user) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); }
function clearAuth() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); }

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  const t = getToken();
  if (t) headers["X-Auth-Token"] = t;
  const res = await fetch(path, Object.assign({ headers }, opts));
  if (res.status === 401) {
    clearAuth();
    if (!location.pathname.endsWith("index.html") && location.pathname !== "/") {
      location.href = "/index.html";
    }
    throw new Error("登录已过期，请重新登录");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "请求失败");
  return data;
}

// 进入页面时校验身份；role 指定必需角色。返回 user 或跳转首页。
function requireAuth(role) {
  const user = getUser();
  const token = getToken();
  if (!user || !token) { location.href = "/index.html"; return null; }
  if (role && user.role !== role) {
    location.href = user.role === "admin" ? "/admin.html" : "/user.html";
    return null;
  }
  return user;
}

function logout() {
  api("/api/logout", { method: "POST" }).catch(() => {});
  clearAuth();
  location.href = "/index.html";
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function resTag(status) {
  return `<span class="tag ${RES_TAG[status] || "gray"}">${RES_STATUS[status] || status}</span>`;
}
function equipTag(status) {
  return `<span class="tag ${EQUIP_TAG[status] || "gray"}">${EQUIP_STATUS[status] || status}</span>`;
}
function userTypeTag(t) {
  return `<span class="tag ${USER_TYPE_TAG[t] || "gray"}">${USER_TYPE[t] || t || "-"}</span>`;
}
function userStatusTag(s) {
  return `<span class="tag ${USER_STATUS_TAG[s] || "gray"}">${USER_STATUS[s] || s || "-"}</span>`;
}
