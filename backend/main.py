"""实验设备预约系统 —— 后端 API（FastAPI + SQLAlchemy 双库）。

入口：
  - /api/*   业务接口
  - /         前端页面（由 FastAPI 直接托管 frontend 目录）

角色与库映射：
  - admin  管理员：账号在 admin 库；通过 /api/admin/login 独立登录；负责设备管理、预约审批、统计
  - user   预约人：账号在 app 库；通过 /api/register + /api/login；浏览设备、提交预约、查看我的预约

管理员审批的是 app 库里真实预约人的预约，不是模板数据。
"""
import os
import hashlib
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

import db
import mailer

db.init_db()

app = FastAPI(title="实验设备预约系统", version="2.0.0")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """健康检查（Render 等平台探活用）。"""
    return {"ok": True, "service": "equipment-reservation"}


# ----------------------------- 鉴权辅助 -----------------------------
def _extract_token(authorization: str = "", x_auth_token: str = "") -> str:
    """令牌放在自定义头 X-Auth-Token（部署平台会覆盖 Authorization，故不用它）；
    本地开发仍兼容 Authorization: Bearer <token>。"""
    raw = (x_auth_token or "").strip() or (authorization or "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    if raw.startswith("Bearer "):
        raw = raw[7:].strip()
    return raw


def get_current_user(
    authorization: str = Header(default=""), x_auth_token: str = Header(default="")
) -> dict:
    token = _extract_token(authorization, x_auth_token)
    s = db.get_session(token)
    if not s:
        raise HTTPException(status_code=401, detail="会话无效")
    if s["expires_at"] and s["expires_at"] < db.now_str():
        raise HTTPException(status_code=401, detail="登录已过期")
    # 按角色从正确的库取主体
    subject = db.get_admin_by_id(s["user_id"]) if s["role"] == "admin" else db.get_user_by_id(s["user_id"])
    if not subject:
        raise HTTPException(status_code=401, detail="用户不存在")
    subject["role"] = s["role"]
    return subject


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ----------------------------- 请求体 -----------------------------
class RegisterIn(BaseModel):
    username: str
    password: str
    real_name: str = ""
    phone: str = ""
    email: str
    email_code: str
    user_type: str = "internal"  # internal 校内 / external 校外
    org_name: str = ""           # 校外：单位名称
    org_type: str = ""           # 校外：单位类型（高校/科研院所/企业/其他）
    department: str = ""         # 校内：院系
    student_id: str = ""         # 校内：学号/工号
    supervisor: str = ""         # 导师/课题组负责人

    @field_validator("username")
    @classmethod
    def _u(cls, v):
        if len(v) < 3:
            raise ValueError("用户名至少 3 个字符")
        return v

    @field_validator("password")
    @classmethod
    def _p(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少 6 个字符")
        return v

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        if not v or "@" not in v or "." not in v:
            raise ValueError("请填写有效邮箱")
        return v.strip().lower()

    @field_validator("email_code")
    @classmethod
    def _c(cls, v):
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError("验证码为 6 位数字")
        return v

    @field_validator("user_type")
    @classmethod
    def _t(cls, v):
        if v not in ("internal", "external"):
            raise ValueError("用户类型必须为 internal(校内) 或 external(校外)")
        return v


class LoginIn(BaseModel):
    username: str
    password: str


class EquipmentIn(BaseModel):
    name: str
    category: str = "其他"
    model: str = ""
    location: str = ""
    status: str = "available"
    manager: str = ""
    description: str = ""


class ReservationIn(BaseModel):
    equipment_id: int
    start_time: str
    end_time: str
    purpose: str = ""


class ApproveIn(BaseModel):
    note: str = ""


def _equip_fields(body: EquipmentIn) -> dict:
    return {
        "name": body.name, "category": body.category, "model": body.model,
        "location": body.location, "status": body.status, "manager": body.manager,
        "description": body.description,
    }


# ----------------------------- 鉴权接口 -----------------------------
def _code_hash(code: str) -> str:
    return hashlib.sha256(f"ers_code:{code}".encode()).hexdigest()


class SendCodeIn(BaseModel):
    email: str
    purpose: str = "register"  # register 注册 / reset 找回密码

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        if not v or "@" not in v or "." not in v:
            raise ValueError("请填写有效邮箱")
        return v.strip().lower()

    @field_validator("purpose")
    @classmethod
    def _p(cls, v):
        if v not in ("register", "reset"):
            raise ValueError("purpose 必须为 register 或 reset")
        return v


@app.post("/api/send-code")
def send_code(body: SendCodeIn):
    """发送邮箱验证码（注册 / 找回密码）。

    未配置 SMTP 时进入开发模式：验证码打印到日志并随响应返回 dev_code，
    配置 SMTP 后走真实邮件（见 backend/.env 的 SMTP_* 配置）。
    """
    email = body.email
    if body.purpose == "register":
        if db.get_user_by_email(email):
            raise HTTPException(status_code=409, detail="该邮箱已被注册，可直接登录或找回密码")
    else:
        if not db.get_user_by_email(email):
            raise HTTPException(status_code=404, detail="该邮箱未注册")
    code = mailer.gen_code()
    expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    db.set_verify_code(email, body.purpose, _code_hash(code), expires)
    sent = mailer.send_code(email, code, body.purpose)
    resp = {"ok": True, "message": "验证码已发送，10 分钟内有效", "dev_mode": not sent}
    if not sent:
        resp["dev_code"] = code  # 仅开发模式（未配置 SMTP）返回，便于本地联调
    return resp


@app.post("/api/register")
def register(body: RegisterIn):
    """注册预约账号（需邮箱验证码）。

    借鉴高校大型仪器共享平台（清华/武大）的校外用户审核机制：
      - 校内用户（internal）：邮箱验证通过即生效，可直接预约；
      - 校外用户（external）：邮箱验证通过后进入「待审核」，需管理员审核激活后才能预约。
    """
    if db.username_exists(body.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    if db.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="该邮箱已被注册")
    if not db.check_verify_code(body.email, "register", _code_hash(body.email_code)):
        raise HTTPException(status_code=400, detail="验证码错误或已过期，请重新获取")
    is_external = body.user_type == "external"
    status = "pending" if is_external else "active"
    uid = db.create_user(
        body.username, body.password, body.real_name, body.phone,
        user_type=body.user_type, status=status, email=body.email,
        org_name=body.org_name, org_type=body.org_type,
        department=body.department, student_id=body.student_id,
        supervisor=body.supervisor,
    )
    db.set_email_verified(uid)
    msg = (
        "注册成功，请等待管理员审核激活后预约"
        if is_external else "注册成功，请登录"
    )
    return {"ok": True, "user_id": uid, "message": msg, "status": status}


class ForgotPasswordIn(BaseModel):
    email: str
    code: str
    new_password: str

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        if not v or "@" not in v or "." not in v:
            raise ValueError("请填写有效邮箱")
        return v.strip().lower()

    @field_validator("code")
    @classmethod
    def _c(cls, v):
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError("验证码为 6 位数字")
        return v

    @field_validator("new_password")
    @classmethod
    def _p(cls, v):
        if len(v) < 6:
            raise ValueError("新密码至少 6 个字符")
        return v


@app.post("/api/forgot-password")
def forgot_password(body: SendCodeIn):
    """忘记密码：向注册邮箱发送重置验证码。"""
    u = db.get_user_by_email(body.email)
    if not u:
        raise HTTPException(status_code=404, detail="该邮箱未注册")
    code = mailer.gen_code()
    expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    db.set_verify_code(body.email, "reset", _code_hash(code), expires)
    sent = mailer.send_code(body.email, code, "reset")
    resp = {"ok": True, "message": "重置验证码已发送，10 分钟内有效", "dev_mode": not sent}
    if not sent:
        resp["dev_code"] = code
    return resp


@app.post("/api/reset-password")
def reset_password(body: ForgotPasswordIn):
    """重置密码：验证邮箱验证码后设置新密码。"""
    u = db.get_user_by_email(body.email)
    if not u:
        raise HTTPException(status_code=404, detail="该邮箱未注册")
    if not db.check_verify_code(body.email, "reset", _code_hash(body.code)):
        raise HTTPException(status_code=400, detail="验证码错误或已过期，请重新获取")
    db.reset_user_password(u["id"], body.new_password)
    return {"ok": True, "message": "密码已重置，请用新密码登录"}


@app.post("/api/login")
def login(body: LoginIn):
    """预约人登录（只校验 app 库用户，管理员无法从此入口登录）。

    账号安全（借鉴毕设登录日志与防爆破）：连续 5 次密码错误锁定 15 分钟。
    """
    u = db.get_user(body.username)
    if not u:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if db.user_locked(u):
        raise HTTPException(status_code=403, detail="账号已锁定（多次密码错误），请 15 分钟后再试")
    if not db.verify_pwd(body.password, u["password_hash"]):
        locked = db.record_login_fail(u["id"])
        msg = "账号已锁定 15 分钟（多次密码错误）" if locked else "用户名或密码错误"
        raise HTTPException(status_code=401, detail=msg)
    db.reset_login_fails(u["id"])
    if u["status"] == "pending":
        raise HTTPException(status_code=403, detail="账号正在审核中，请等待管理员激活")
    if u["status"] == "rejected":
        raise HTTPException(status_code=403, detail="注册申请未通过审核，请联系管理员")
    if u["status"] == "disabled":
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
    token = db.new_token()
    db.create_session(token, u["id"], "user")
    u["role"] = "user"
    return {"token": token, "user": u}


@app.post("/api/admin/login")
def admin_login(body: LoginIn):
    """管理员独立登录（校验 admin 库账号）。"""
    a = db.get_admin(body.username)
    if not a or not db.verify_pwd(body.password, a["password_hash"]):
        raise HTTPException(status_code=401, detail="管理员账号或密码错误")
    token = db.new_token()
    db.create_session(token, a["id"], "admin")
    a["role"] = "admin"
    return {"token": token, "user": a}


@app.post("/api/logout")
def logout(authorization: str = Header(default=""), x_auth_token: str = Header(default="")):
    raw = (x_auth_token or "").strip() or (authorization or "").strip()
    if raw:
        if raw.startswith("Bearer "):
            raw = raw[7:].strip()
        db.delete_session(raw)
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return user


# ----------------------------- 用户管理（管理员，借鉴佰能「用户管理」/ NEMO Accounts） -----------------------------
@app.get("/api/users")
def list_users(
    user_type: str = "", status: str = "", kw: str = "", admin: dict = Depends(require_admin)
):
    """管理员查看全部预约账号，可按 类型(校内/校外)/状态/关键词 筛选。"""
    return db.list_users(user_type, status, kw)


@app.post("/api/users/{uid}/approve")
def approve_user(uid: int, admin: dict = Depends(require_admin)):
    """审核通过：激活校外用户（pending -> active）。"""
    u = db.get_user_by_id(uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u["status"] != "pending":
        raise HTTPException(status_code=400, detail="仅待审核账号可激活")
    db.set_user_status(uid, "active")
    return {"ok": True, "message": f"已激活 {u['real_name'] or u['username']} 的账号"}


@app.post("/api/users/{uid}/reject")
def reject_user(uid: int, admin: dict = Depends(require_admin)):
    """驳回校外注册申请（pending -> rejected）。"""
    u = db.get_user_by_id(uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u["status"] != "pending":
        raise HTTPException(status_code=400, detail="仅待审核账号可驳回")
    db.set_user_status(uid, "rejected")
    return {"ok": True, "message": "已驳回该注册申请"}


@app.post("/api/users/{uid}/toggle")
def toggle_user(uid: int, admin: dict = Depends(require_admin)):
    """启用 / 禁用账号（active <-> disabled）。"""
    u = db.get_user_by_id(uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    new_status = "active" if u["status"] == "disabled" else "disabled"
    db.set_user_status(uid, new_status)
    return {"ok": True, "status": new_status, "message": "已启用" if new_status == "active" else "已禁用"}


class ResetPwdIn(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _p(cls, v):
        if len(v) < 6:
            raise ValueError("新密码至少 6 个字符")
        return v


@app.post("/api/users/{uid}/reset-password")
def reset_password(uid: int, body: ResetPwdIn, admin: dict = Depends(require_admin)):
    """管理员重置用户密码。"""
    u = db.get_user_by_id(uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.reset_user_password(uid, body.new_password)
    return {"ok": True, "message": f"已重置 {u['real_name'] or u['username']} 的密码"}


# ----------------------------- 设备收藏（借鉴佰能「设备收藏」红心） -----------------------------
@app.get("/api/favorites")
def my_favorites(user: dict = Depends(get_current_user)):
    """当前用户收藏的设备 id 列表。"""
    return {"ids": db.list_favorites(user["id"])}


@app.post("/api/favorites/{eid}")
def add_favorite(eid: int, user: dict = Depends(get_current_user)):
    eq = db.get_equipment(eid)
    if not eq:
        raise HTTPException(status_code=404, detail="设备不存在")
    if not db.is_favorite(user["id"], eid):
        db.add_favorite(user["id"], eid)
    return {"ok": True}


@app.delete("/api/favorites/{eid}")
def remove_favorite(eid: int, user: dict = Depends(get_current_user)):
    db.remove_favorite(user["id"], eid)
    return {"ok": True}


# ----------------------------- 设备接口（目录在 admin 库） -----------------------------
@app.get("/api/equipment")
def list_equipment(kw: str = "", status: str = "", category: str = "", user: dict = Depends(get_current_user)):
    return db.list_equipment(kw, status, category)


@app.get("/api/equipment-categories")
def equipment_categories(user: dict = Depends(get_current_user)):
    return {"categories": db.equipment_categories()}


@app.get("/api/equipment/{eid}")
def equipment_detail(eid: int, user: dict = Depends(get_current_user)):
    """设备详情：基本信息 + 未来排期 + 使用历史（预约冲突可视化）。"""
    eq = db.get_equipment(eid)
    if not eq:
        raise HTTPException(status_code=404, detail="设备不存在")
    eq["schedule"] = db.equipment_schedule(eid)
    eq["usage_history"] = db.equipment_usage_history(eid)
    return eq


@app.post("/api/equipment")
def create_equipment(body: EquipmentIn, admin: dict = Depends(require_admin)):
    return {"ok": True, "id": db.create_equipment(**_equip_fields(body))}


@app.put("/api/equipment/{eid}")
def update_equipment(eid: int, body: EquipmentIn, admin: dict = Depends(require_admin)):
    rc = db.update_equipment(eid, **_equip_fields(body))
    if rc == 0:
        raise HTTPException(status_code=404, detail="设备不存在")
    return {"ok": True}


@app.delete("/api/equipment/{eid}")
def delete_equipment(eid: int, admin: dict = Depends(require_admin)):
    if db.has_active_reservations(eid):
        raise HTTPException(status_code=409, detail="该设备存在进行中的预约，无法删除")
    db.delete_equipment_row(eid)
    return {"ok": True}


# ----------------------------- 通知公告（借鉴毕设公告模块） -----------------------------
class AnnouncementIn(BaseModel):
    title: str
    content: str = ""


@app.get("/api/announcements")
def announcements(user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        return {"list": db.list_announcements(active_only=False)}
    return {"list": db.list_announcements(active_only=True)}


@app.post("/api/announcements")
def create_announcement(body: AnnouncementIn, admin: dict = Depends(require_admin)):
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="公告标题不能为空")
    return {"ok": True, "id": db.create_announcement(body.title.strip(), body.content)}


@app.put("/api/announcements/{aid}/toggle")
def toggle_announcement(aid: int, admin: dict = Depends(require_admin)):
    a = db.get_announcement(aid)
    if not a:
        raise HTTPException(status_code=404, detail="公告不存在")
    db.set_announcement_active(aid, 0 if a["active"] else 1)
    return {"ok": True}


@app.delete("/api/announcements/{aid}")
def delete_announcement(aid: int, admin: dict = Depends(require_admin)):
    db.delete_announcement(aid)
    return {"ok": True}


# ----------------------------- 设备报修（借鉴毕设设备报障流程） -----------------------------
class RepairIn(BaseModel):
    equipment_id: int
    issue: str


class RepairHandleIn(BaseModel):
    note: str = ""
    status: str = "handling"  # handling 处理中 / fixed 已修复（恢复设备可用）


@app.post("/api/repairs")
def create_repair(body: RepairIn, user: dict = Depends(get_current_user)):
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="账号未激活，暂不能报修")
    if not body.issue.strip():
        raise HTTPException(status_code=400, detail="请填写故障描述")
    eq = db.get_equipment(body.equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="设备不存在")
    rid = db.create_repair(user["id"], eq["id"], eq["name"], body.issue.strip())
    # 报修即标记设备维护中，避免他人继续预约故障设备
    if eq["status"] == "available":
        db.update_equipment(eq["id"], status="maintenance")
    return {"ok": True, "id": rid, "message": "报修已提交，设备将暂停预约等待维修"}


@app.get("/api/repairs")
def repairs(status: str = "", user: dict = Depends(get_current_user)):
    """管理员：全部报修（可筛选）；普通用户：自己的报修。"""
    if user.get("role") == "admin":
        rows = db.list_repairs(status)
        for r in rows:
            u = db.get_user_by_id(r["user_id"])
            r["user_name"] = (u or {}).get("real_name", "")
        return {"list": rows}
    return {"list": db.list_my_repairs(user["id"])}


@app.put("/api/repairs/{rid}/handle")
def handle_repair(rid: int, body: RepairHandleIn, admin: dict = Depends(require_admin)):
    """处理报修：处理中 / 已修复（修复后设备恢复可预约）。"""
    r = db.get_repair(rid)
    if not r:
        raise HTTPException(status_code=404, detail="报修记录不存在")
    db.set_repair_status(rid, body.status, handler=admin.get("display_name") or admin.get("username", ""), note=body.note)
    if body.status == "fixed":
        db.update_equipment(r["equipment_id"], status="available")
    elif body.status == "handling":
        db.update_equipment(r["equipment_id"], status="maintenance")
    return {"ok": True, "message": "已修复" if body.status == "fixed" else "已开始处理"}


# ----------------------------- 预约接口（预约在 app 库） -----------------------------
@app.post("/api/reservations")
def create_reservation(body: ReservationIn, user: dict = Depends(get_current_user)):
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="账号未激活，暂不能提交预约")
    if body.end_time <= body.start_time:
        raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")
    eq = db.get_equipment(body.equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="设备不存在")
    if eq["status"] != "available":
        raise HTTPException(status_code=400, detail=f"设备当前状态为「{eq['status']}」，不可预约")
    conflict = db.check_conflict(body.equipment_id, body.start_time, body.end_time)
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"时间冲突：{conflict['real_name']} 已预约 {conflict['start_time']} ~ {conflict['end_time']}",
        )
    rid = db.create_reservation(
        user["id"], body.equipment_id, eq["name"], body.start_time, body.end_time, body.purpose
    )
    return {"ok": True, "id": rid, "message": "预约已提交，等待管理员审核"}


@app.get("/api/reservations/mine")
def my_reservations(status: str = "", kw: str = "", user: dict = Depends(get_current_user)):
    return db.list_my(user["id"], status, kw)


@app.get("/api/reservations")
def list_reservations(
    status: str = "", equipment_id: int = 0, kw: str = "", admin: dict = Depends(require_admin)
):
    """管理员视图：按状态/设备/关键词(预约人/设备名/用途)模糊查询真实预约。"""
    return db.list_all(status, equipment_id, kw)


@app.post("/api/reservations/{rid}/approve")
def approve(rid: int, body: ApproveIn, admin: dict = Depends(require_admin)):
    r = db.get_reservation(rid)
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r["status"] != "pending":
        raise HTTPException(status_code=400, detail="仅待审核预约可审批")
    db.set_reservation_status(
        rid, "approved", approver_id=admin["id"], approve_note=body.note, approved_at=db.now_str()
    )
    return {"ok": True, "message": "已通过"}


@app.post("/api/reservations/{rid}/reject")
def reject(rid: int, body: ApproveIn, admin: dict = Depends(require_admin)):
    r = db.get_reservation(rid)
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r["status"] != "pending":
        raise HTTPException(status_code=400, detail="仅待审核预约可审批")
    db.set_reservation_status(
        rid, "rejected", approver_id=admin["id"], approve_note=body.note, approved_at=db.now_str()
    )
    return {"ok": True, "message": "已驳回"}


@app.post("/api/reservations/{rid}/cancel")
def cancel(rid: int, user: dict = Depends(get_current_user)):
    r = db.get_reservation(rid)
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="无权取消该预约")
    if r["status"] in ("used", "cancelled"):
        raise HTTPException(status_code=400, detail="该预约已结束，无法取消")
    db.set_reservation_status(rid, "cancelled")
    return {"ok": True, "message": "已取消"}


@app.post("/api/reservations/{rid}/complete")
def complete(rid: int, admin: dict = Depends(require_admin)):
    r = db.get_reservation(rid)
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r["status"] not in ("approved", "in_use"):
        raise HTTPException(status_code=400, detail="仅已通过/使用中的预约可标记完成")
    db.set_reservation_status(rid, "used")
    return {"ok": True, "message": "已标记完成"}


# ----------------------------- 设备登录（签到 / 签退） -----------------------------
@app.post("/api/reservations/{rid}/checkin")
def checkin(rid: int, user: dict = Depends(get_current_user)):
    r = db.get_reservation(rid)
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="无权操作该预约")
    if r["status"] != "approved":
        raise HTTPException(status_code=400, detail="仅已通过预约可登录设备")
    db.set_reservation_status(rid, "in_use", checkin_at=db.now_str())
    return {"ok": True, "message": "已登录设备，开始使用"}


@app.post("/api/reservations/{rid}/checkout")
def checkout(rid: int, user: dict = Depends(get_current_user)):
    r = db.get_reservation(rid)
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="无权操作该预约")
    if r["status"] != "in_use":
        raise HTTPException(status_code=400, detail="仅使用中的预约可结束")
    db.set_reservation_status(rid, "used", checkout_at=db.now_str())
    return {"ok": True, "message": "已结束使用"}


# ----------------------------- 统计看板 -----------------------------
@app.get("/api/stats")
def stats(admin: dict = Depends(require_admin)):
    return {
        "total_equipment": db.count_equipment(),
        "total_users": db.count_users(),
        "total_reservations": db.count_reservations(),
        "pending_users": db.count_pending_users(),
        "pending_repairs": db.count_pending_repairs(),
        "by_status": db.res_by_status(),
        "equip_status": db.equip_by_status(),
        "top_equipment": db.top_equipment(),
        "recent": db.recent_reservations(),
        "in_use": db.list_in_use(),
    }


# ----------------------------- 托管前端 -----------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    # 端口优先读环境变量 PORT（云平台/发布服务注入），本地默认 8000
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
