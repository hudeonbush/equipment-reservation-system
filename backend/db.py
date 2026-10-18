"""实验设备预约系统 —— 数据库层（双库设计，SQLAlchemy 驱动）。

两个数据库，职责彻底分离：
  - admin 库（本地 admin.db / 云端 Postgres schema `admin`）
        管理员账号(admin_users)、设备目录(equipment)、系统设置(settings)
  - app   库（本地 app.db   / 云端 Postgres schema `app`）
        预约人账号(users)、登录会话(sessions)、真实预约记录(reservations)

设计要点：
  * 本地默认使用两个 SQLite 文件，开箱即用、可持久化到磁盘。
  * 设置 DATABASE_URL（指向 Supabase 等托管 Postgres）后，自动切换到云端双 schema，
    数据持久化、不受部署回收影响（解决“每次更新要重新注册 / 只有模板数据”的问题）。
  * 管理员与预约人物理隔离：客户前台永远碰不到管理员账号；管理员审批的是 app 库里
    真实预约人的预约，而不是模板。
"""
import os
import ssl
import secrets
import hashlib
from datetime import datetime, timedelta

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Text,
    select, insert, update, delete, func, or_, and_, text,
)
from sqlalchemy.engine import Engine

BASE_DIR = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# 配置解析：优先环境变量，其次本地 .env（发布到云端时把 Supabase 连接串放这里）
# ---------------------------------------------------------------------------
def _load_dotenv() -> None:
    p = os.path.join(BASE_DIR, ".env")
    if not os.path.isfile(p):
        return
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


_load_dotenv()

DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
# 兼容 Render 等平台的 postgres:// 连接串（统一为 pg8000 认识的 postgresql://）
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
USE_PG = DATABASE_URL.startswith("postgresql")

ADMIN_SCHEMA = "admin" if USE_PG else None
APP_SCHEMA = "app" if USE_PG else None

SALT = "ers_salt_v2"
TOKEN_TTL_DAYS = 7


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _make_engine(url: str) -> Engine:
    if not USE_PG:
        return create_engine(f"sqlite:///{os.path.join(BASE_DIR, url)}", future=True)
    # 显式指定 pg8000 驱动（requirements 仅装 pg8000；SQLAlchemy 默认会找 psycopg2）
    if url.startswith("postgresql://"):
        url = "postgresql+pg8000://" + url[len("postgresql://"):]
    connect_args: dict = {}
    if "supabase.co" in url or "sslmode" in url:
        try:
            connect_args["ssl_context"] = ssl.create_default_context()
        except Exception:
            pass
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


# 本地：url 作为文件名；云端：两个引擎指向同一 Postgres（靠 schema 区分两张表集合）
if USE_PG:
    admin_engine = _make_engine(DATABASE_URL)
    app_engine = _make_engine(DATABASE_URL)
else:
    admin_engine = _make_engine("admin.db")
    app_engine = _make_engine("app.db")

admin_meta = MetaData(schema=ADMIN_SCHEMA)
app_meta = MetaData(schema=APP_SCHEMA)


# ----------------------------- admin 库表 -----------------------------
admin_users = Table(
    "admin_users", admin_meta,
    Column("id", Integer, primary_key=True),
    Column("username", String(64), unique=True, nullable=False),
    Column("password_hash", String(200), nullable=False),
    Column("display_name", String(64)),
    Column("created_at", String(20)),
)
equipment = Table(
    "equipment", admin_meta,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("category", String(40), server_default="其他"),  # 设备分类（借鉴毕设设备类别管理）
    Column("model", String(120)),
    Column("location", String(120)),
    Column("status", String(20), server_default="available"),
    Column("manager", String(64)),
    Column("description", Text),
    Column("created_at", String(20)),
)
settings = Table(
    "settings", admin_meta,
    Column("key", String(64), primary_key=True),
    Column("value", Text),
    Column("updated_at", String(20)),
)
announcements = Table(
    "announcements", admin_meta,
    Column("id", Integer, primary_key=True),
    Column("title", String(120), nullable=False),
    Column("content", Text),
    Column("active", Integer, server_default="1"),  # 1 展示中 / 0 已停用
    Column("created_at", String(20)),
    Column("updated_at", String(20)),
)


# ----------------------------- app 库表 -----------------------------
users = Table(
    "users", app_meta,
    Column("id", Integer, primary_key=True),
    Column("username", String(64), unique=True, nullable=False),
    Column("password_hash", String(200), nullable=False),
    Column("real_name", String(64)),
    Column("phone", String(32)),
    Column("email", String(120)),
    # 用户类型：internal 校内用户 / external 校外用户（借鉴高校共享平台三角色体系）
    Column("user_type", String(20), server_default="internal"),
    # 账号状态：active 正常 / pending 待审核(校外注册) / disabled 已禁用 / rejected 审核驳回
    Column("status", String(20), server_default="active"),
    Column("org_name", String(120)),    # 校外：单位/公司名称
    Column("org_type", String(40)),     # 校外：单位类型（高校/科研院所/企业/其他）
    Column("department", String(80)),   # 校内：院系/部门
    Column("student_id", String(40)),   # 校内：学号/工号
    Column("supervisor", String(64)),   # 导师/课题组负责人
    # 邮箱验证（账号安全）：邮箱是否已验证（验证码存 verify_codes 表）
    Column("email_verified", Integer, server_default="0"),
    # 登录安全（借鉴毕设登录日志与防爆破）：连续失败次数 + 锁定截止时间
    Column("failed_attempts", Integer, server_default="0"),
    Column("locked_until", String(20)),
    Column("created_at", String(20)),
)
repairs = Table(
    "repairs", app_meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False),   # 报修人
    Column("equipment_id", Integer, nullable=False),
    Column("equipment_name", String(120)),        # 设备名快照（设备可能被改/删）
    Column("issue", Text, nullable=False),        # 故障描述
    Column("status", String(20), server_default="pending"),
    # pending 待处理 / handling 处理中 / fixed 已修复 / closed 已关闭
    Column("handler", String(64)),                # 处理人（管理员）
    Column("handle_note", Text),                  # 处理说明
    Column("created_at", String(20)),
    Column("handled_at", String(20)),
)
favorites = Table(
    "favorites", app_meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False),
    Column("equipment_id", Integer, nullable=False),
    Column("created_at", String(20)),
)
verify_codes = Table(
    "verify_codes", app_meta,
    Column("id", Integer, primary_key=True),
    Column("email", String(120), nullable=False, index=True),
    Column("purpose", String(20), nullable=False),  # register 注册 / reset 找回密码
    Column("code_hash", String(200), nullable=False),
    Column("expires_at", String(20), nullable=False),
    Column("created_at", String(20)),
)
sessions = Table(
    "sessions", app_meta,
    Column("token", String(80), primary_key=True),
    Column("user_id", Integer, nullable=False),
    Column("role", String(20), nullable=False),  # 'admin' | 'user'
    Column("created_at", String(20)),
    Column("expires_at", String(20)),
)
reservations = Table(
    "reservations", app_meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False),
    Column("equipment_id", Integer, nullable=False),
    Column("equipment_name", String(120)),       # 设备名快照，避免跨库 join
    Column("start_time", String(20), nullable=False),
    Column("end_time", String(20), nullable=False),
    Column("purpose", Text),
    Column("status", String(20), server_default="pending"),
    Column("approver_id", Integer),
    Column("approve_note", Text),
    Column("approved_at", String(20)),
    Column("checkin_at", String(20)),
    Column("checkout_at", String(20)),
    Column("created_at", String(20)),
)


# ----------------------------- 密码 / 令牌 -----------------------------
def hash_pwd(p: str) -> str:
    return f"{SALT}:{hashlib.sha256((SALT + p).encode()).hexdigest()}"


def verify_pwd(p: str, stored: str) -> bool:
    return hash_pwd(p) == (stored or "")


def new_token() -> str:
    return secrets.token_hex(32)


# ----------------------------- 会话（app 库） -----------------------------
def create_session(token: str, user_id: int, role: str) -> None:
    expires = (datetime.now() + timedelta(days=TOKEN_TTL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    with app_engine.begin() as c:
        c.execute(insert(sessions).values(
            token=token, user_id=user_id, role=role,
            created_at=now_str(), expires_at=expires,
        ))


def get_session(token: str):
    with app_engine.connect() as c:
        r = c.execute(select(sessions).where(sessions.c.token == token)).mappings().first()
    return dict(r) if r else None


def delete_session(token: str) -> None:
    with app_engine.begin() as c:
        c.execute(delete(sessions).where(sessions.c.token == token))


# ----------------------------- 管理员（admin 库） -----------------------------
def get_admin(username: str):
    with admin_engine.connect() as c:
        r = c.execute(select(admin_users).where(admin_users.c.username == username)).mappings().first()
    return dict(r) if r else None


def get_admin_by_id(uid: int):
    with admin_engine.connect() as c:
        r = c.execute(select(admin_users).where(admin_users.c.id == uid)).mappings().first()
    return dict(r) if r else None


# ----------------------------- 预约人（app 库） -----------------------------
def username_exists(username: str) -> bool:
    with app_engine.connect() as c:
        r = c.execute(select(users.c.id).where(users.c.username == username)).first()
    return r is not None


def create_user(
    username: str, password: str, real_name: str = "", phone: str = "",
    user_type: str = "internal", status: str = "active", email: str = "",
    org_name: str = "", org_type: str = "", department: str = "",
    student_id: str = "", supervisor: str = "",
) -> int:
    with app_engine.begin() as c:
        res = c.execute(insert(users).values(
            username=username, password_hash=hash_pwd(password),
            real_name=real_name, phone=phone, email=email,
            user_type=user_type, status=status,
            org_name=org_name, org_type=org_type,
            department=department, student_id=student_id, supervisor=supervisor,
            created_at=now_str(),
        ))
        return res.inserted_primary_key[0]


def get_user(username: str):
    with app_engine.connect() as c:
        r = c.execute(select(users).where(users.c.username == username)).mappings().first()
    return dict(r) if r else None


def get_user_by_id(uid: int):
    with app_engine.connect() as c:
        r = c.execute(select(users).where(users.c.id == uid)).mappings().first()
    return dict(r) if r else None


def count_users() -> int:
    with app_engine.connect() as c:
        return c.execute(select(func.count()).select_from(users)).scalar() or 0


# ----------------------------- 用户管理（管理员，借鉴佰能"用户管理"） -----------------------------
def list_users(user_type: str = "", status: str = "", kw: str = "") -> list:
    """管理员视角用户列表：可按类型/状态/关键词(用户名/姓名/单位/院系)筛选。"""
    stmt = select(users)
    if user_type:
        stmt = stmt.where(users.c.user_type == user_type)
    if status:
        stmt = stmt.where(users.c.status == status)
    if kw:
        like = f"%{kw}%"
        stmt = stmt.where(or_(
            users.c.username.like(like), users.c.real_name.like(like),
            users.c.org_name.like(like), users.c.department.like(like),
            users.c.student_id.like(like),
        ))
    stmt = stmt.order_by(users.c.id.desc())
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def set_user_status(uid: int, status: str) -> int:
    """启用/禁用/驳回用户账号。"""
    with app_engine.begin() as c:
        return c.execute(update(users).where(users.c.id == uid).values(status=status)).rowcount


def set_user_type(uid: int, user_type: str) -> int:
    with app_engine.begin() as c:
        return c.execute(update(users).where(users.c.id == uid).values(user_type=user_type)).rowcount


def reset_user_password(uid: int, password: str) -> int:
    """重置密码（管理员/忘记密码），同时清除登录失败锁定，实现账号解锁。"""
    with app_engine.begin() as c:
        return c.execute(
            update(users).where(users.c.id == uid).values(
                password_hash=hash_pwd(password), failed_attempts=0, locked_until=None,
            )
        ).rowcount


def count_pending_users() -> int:
    with app_engine.connect() as c:
        return c.execute(
            select(func.count()).select_from(users).where(users.c.status == "pending")
        ).scalar() or 0


# ----------------------------- 设备收藏（借鉴佰能"设备收藏"红心） -----------------------------
def list_favorites(user_id: int) -> list:
    """当前用户收藏的设备 id 集合。"""
    stmt = select(favorites.c.equipment_id).where(favorites.c.user_id == user_id)
    with app_engine.connect() as c:
        return [r[0] for r in c.execute(stmt).all()]


def is_favorite(user_id: int, eid: int) -> bool:
    with app_engine.connect() as c:
        r = c.execute(select(favorites.c.id).where(and_(
            favorites.c.user_id == user_id, favorites.c.equipment_id == eid,
        )).limit(1)).first()
    return r is not None


def add_favorite(user_id: int, eid: int) -> None:
    with app_engine.begin() as c:
        c.execute(insert(favorites).values(user_id=user_id, equipment_id=eid, created_at=now_str()))


def remove_favorite(user_id: int, eid: int) -> None:
    with app_engine.begin() as c:
        c.execute(delete(favorites).where(and_(
            favorites.c.user_id == user_id, favorites.c.equipment_id == eid,
        )))


# ----------------------------- 邮箱验证码（账号安全） -----------------------------
def get_user_by_email(email: str):
    if not email:
        return None
    with app_engine.connect() as c:
        r = c.execute(select(users).where(users.c.email == email)).mappings().first()
    return dict(r) if r else None


def set_verify_code(email: str, purpose: str, code_hash: str, expires_at: str) -> None:
    """写入（或覆盖）邮箱验证码，仅保留最新一条。"""
    with app_engine.begin() as c:
        c.execute(delete(verify_codes).where(and_(
            verify_codes.c.email == email, verify_codes.c.purpose == purpose,
        )))
        c.execute(insert(verify_codes).values(
            email=email, purpose=purpose, code_hash=code_hash,
            expires_at=expires_at, created_at=now_str(),
        ))


def check_verify_code(email: str, purpose: str, code: str) -> bool:
    """校验验证码：哈希一致且未过期。校验通过后删除该条记录（一次性）。"""
    now = now_str()
    with app_engine.begin() as c:
        r = c.execute(
            select(verify_codes).where(and_(
                verify_codes.c.email == email, verify_codes.c.purpose == purpose,
            )).order_by(verify_codes.c.id.desc()).limit(1)
        ).mappings().first()
        if not r:
            return False
        if r["expires_at"] < now:
            return False
        if r["code_hash"] != code:  # code 传入前由调用方哈希
            return False
        c.execute(delete(verify_codes).where(verify_codes.c.id == r["id"]))
        return True


def set_email_verified(uid: int) -> None:
    with app_engine.begin() as c:
        c.execute(update(users).where(users.c.id == uid).values(email_verified=1))


def set_user_email(uid: int, email: str) -> None:
    with app_engine.begin() as c:
        c.execute(update(users).where(users.c.id == uid).values(email=email))


# ----------------------------- 登录安全（防爆破锁定） -----------------------------
MAX_LOGIN_ATTEMPTS = 5
LOCK_MINUTES = 15


def record_login_fail(uid: int) -> bool:
    """登录失败：计数 +1；达到阈值返回 True（触发锁定）。"""
    with app_engine.begin() as c:
        r = c.execute(select(users.c.failed_attempts).where(users.c.id == uid)).scalar() or 0
        n = r + 1
        if n >= MAX_LOGIN_ATTEMPTS:
            locked = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
            c.execute(update(users).where(users.c.id == uid).values(failed_attempts=0, locked_until=locked))
            return True
        c.execute(update(users).where(users.c.id == uid).values(failed_attempts=n))
        return False


def reset_login_fails(uid: int) -> None:
    with app_engine.begin() as c:
        c.execute(update(users).where(users.c.id == uid).values(failed_attempts=0, locked_until=None))


def user_locked(u: dict) -> bool:
    return bool(u.get("locked_until")) and u["locked_until"] > now_str()


# ----------------------------- 通知公告（admin 库） -----------------------------
def list_announcements(active_only: bool = False) -> list:
    stmt = select(announcements)
    if active_only:
        stmt = stmt.where(announcements.c.active == 1)
    stmt = stmt.order_by(announcements.c.id.desc()).limit(10)
    with admin_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def get_announcement(aid: int):
    with admin_engine.connect() as c:
        r = c.execute(select(announcements).where(announcements.c.id == aid)).mappings().first()
    return dict(r) if r else None


def create_announcement(title: str, content: str) -> int:
    with admin_engine.begin() as c:
        r = c.execute(insert(announcements).values(
            title=title, content=content, active=1,
            created_at=now_str(), updated_at=now_str(),
        ))
        return r.inserted_primary_key[0]


def set_announcement_active(aid: int, active: int) -> None:
    with admin_engine.begin() as c:
        c.execute(update(announcements).where(announcements.c.id == aid).values(active=active, updated_at=now_str()))


def delete_announcement(aid: int) -> None:
    with admin_engine.begin() as c:
        c.execute(delete(announcements).where(announcements.c.id == aid))


# ----------------------------- 设备报修（app 库，借鉴毕设设备报障流程） -----------------------------
def create_repair(user_id: int, equipment_id: int, equipment_name: str, issue: str) -> int:
    with app_engine.begin() as c:
        r = c.execute(insert(repairs).values(
            user_id=user_id, equipment_id=equipment_id,
            equipment_name=equipment_name, issue=issue,
            status="pending", created_at=now_str(),
        ))
        return r.inserted_primary_key[0]


def get_repair(rid: int):
    with app_engine.connect() as c:
        r = c.execute(select(repairs).where(repairs.c.id == rid)).mappings().first()
    return dict(r) if r else None


def list_repairs(status: str = "") -> list:
    stmt = select(repairs)
    if status:
        stmt = stmt.where(repairs.c.status == status)
    stmt = stmt.order_by(repairs.c.id.desc())
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def list_my_repairs(user_id: int) -> list:
    stmt = select(repairs).where(repairs.c.user_id == user_id).order_by(repairs.c.id.desc())
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def set_repair_status(rid: int, status: str, handler: str = "", note: str = "") -> None:
    vals = {"status": status, "handled_at": now_str()}
    if handler:
        vals["handler"] = handler
    if note:
        vals["handle_note"] = note
    with app_engine.begin() as c:
        c.execute(update(repairs).where(repairs.c.id == rid).values(**vals))


def count_pending_repairs() -> int:
    with app_engine.connect() as c:
        return c.execute(select(func.count()).select_from(repairs).where(repairs.c.status == "pending")).scalar() or 0


# ----------------------------- 设备目录（admin 库） -----------------------------
def list_equipment(kw: str = "", status: str = "", category: str = "") -> list:
    stmt = select(equipment)
    if kw:
        like = f"%{kw}%"
        stmt = stmt.where(or_(
            equipment.c.name.like(like), equipment.c.model.like(like),
            equipment.c.location.like(like), equipment.c.manager.like(like),
        ))
    if status:
        stmt = stmt.where(equipment.c.status == status)
    if category:
        stmt = stmt.where(equipment.c.category == category)
    stmt = stmt.order_by(equipment.c.id.desc())
    with admin_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def equipment_categories() -> list:
    """所有设备分类（去重），用于筛选下拉。"""
    with admin_engine.connect() as c:
        rows = c.execute(select(equipment.c.category).distinct().order_by(equipment.c.category)).scalars().all()
    return [r for r in rows if r] or ["其他"]


def get_equipment(eid: int):
    with admin_engine.connect() as c:
        r = c.execute(select(equipment).where(equipment.c.id == eid)).mappings().first()
    return dict(r) if r else None


def equipment_schedule(eid: int, days: int = 7) -> list:
    """设备未来 N 天的占用时段（pending/approved/in_use），用于预约冲突可视化。

    借鉴 NEMO 日历预约：预约前先看设备排期，避免提交后才冲突。
    """
    stmt = (
        select(
            reservations.c.id, reservations.c.start_time, reservations.c.end_time,
            reservations.c.status, reservations.c.purpose,
            users.c.real_name.label("user_name"), users.c.user_type.label("user_type"),
        )
        .select_from(reservations.join(users, users.c.id == reservations.c.user_id))
        .where(and_(
            reservations.c.equipment_id == eid,
            reservations.c.status.in_(["pending", "approved", "in_use"]),
        ))
        .order_by(reservations.c.start_time.asc())
    )
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def equipment_usage_history(eid: int, limit: int = 10) -> list:
    """设备已使用记录（含使用中/已完成），用于设备详情页。"""
    stmt = (
        select(
            reservations.c.id, reservations.c.start_time, reservations.c.end_time,
            reservations.c.status, reservations.c.purpose, reservations.c.checkin_at,
            reservations.c.checkout_at,
            users.c.real_name.label("user_name"), users.c.user_type.label("user_type"),
        )
        .select_from(reservations.join(users, users.c.id == reservations.c.user_id))
        .where(and_(
            reservations.c.equipment_id == eid,
            reservations.c.status.in_(["in_use", "used", "rejected", "cancelled"]),
        ))
        .order_by(reservations.c.start_time.desc()).limit(limit)
    )
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def create_equipment(**fields) -> int:
    fields.setdefault("created_at", now_str())
    with admin_engine.begin() as c:
        res = c.execute(insert(equipment).values(**fields))
        return res.inserted_primary_key[0]


def update_equipment(eid: int, **fields) -> int:
    with admin_engine.begin() as c:
        res = c.execute(update(equipment).where(equipment.c.id == eid).values(**fields))
        return res.rowcount


def delete_equipment_row(eid: int) -> None:
    with admin_engine.begin() as c:
        c.execute(delete(equipment).where(equipment.c.id == eid))


def count_equipment() -> int:
    with admin_engine.connect() as c:
        return c.execute(select(func.count()).select_from(equipment)).scalar() or 0


# ----------------------------- 预约（app 库） -----------------------------
def has_active_reservations(eid: int) -> bool:
    with app_engine.connect() as c:
        r = c.execute(select(reservations.c.id).where(and_(
            reservations.c.equipment_id == eid,
            reservations.c.status.in_(["pending", "approved", "in_use"]),
        )).limit(1)).first()
    return r is not None


def create_reservation(user_id: int, eid: int, ename: str, start: str, end: str, purpose: str) -> int:
    with app_engine.begin() as c:
        res = c.execute(insert(reservations).values(
            user_id=user_id, equipment_id=eid, equipment_name=ename,
            start_time=start, end_time=end, purpose=purpose,
            status="pending", created_at=now_str(),
        ))
        return res.inserted_primary_key[0]


def check_conflict(eid: int, start: str, end: str):
    stmt = (
        select(reservations.c.id, users.c.real_name, reservations.c.start_time, reservations.c.end_time)
        .select_from(reservations.join(users, users.c.id == reservations.c.user_id))
        .where(and_(
            reservations.c.equipment_id == eid,
            reservations.c.status.in_(["pending", "approved", "in_use"]),
            reservations.c.end_time > start,
            reservations.c.start_time < end,
        ))
    )
    with app_engine.connect() as c:
        r = c.execute(stmt).mappings().first()
    return dict(r) if r else None


def list_my(user_id: int, status: str = "", kw: str = "") -> list:
    stmt = select(reservations).where(reservations.c.user_id == user_id)
    if status:
        stmt = stmt.where(reservations.c.status == status)
    if kw:
        like = f"%{kw}%"
        stmt = stmt.where(or_(
            reservations.c.equipment_name.like(like), reservations.c.purpose.like(like)))
    stmt = stmt.order_by(reservations.c.start_time.desc())
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def list_all(status: str = "", eid: int = 0, kw: str = "") -> list:
    stmt = (
        select(
            reservations, users.c.real_name.label("user_name"),
            users.c.username.label("user_username"),
            users.c.user_type.label("user_type"), users.c.status.label("user_status"),
        )
        .select_from(reservations.join(users, users.c.id == reservations.c.user_id))
    )
    if status:
        stmt = stmt.where(reservations.c.status == status)
    if eid:
        stmt = stmt.where(reservations.c.equipment_id == eid)
    if kw:
        like = f"%{kw}%"
        stmt = stmt.where(or_(
            users.c.real_name.like(like), users.c.username.like(like),
            reservations.c.equipment_name.like(like), reservations.c.purpose.like(like)))
    stmt = stmt.order_by(reservations.c.created_at.desc())
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def get_reservation(rid: int):
    with app_engine.connect() as c:
        r = c.execute(select(reservations).where(reservations.c.id == rid)).mappings().first()
    return dict(r) if r else None


def set_reservation_status(rid: int, status: str, **fields) -> None:
    fields["status"] = status
    with app_engine.begin() as c:
        c.execute(update(reservations).where(reservations.c.id == rid).values(**fields))


def count_reservations() -> int:
    with app_engine.connect() as c:
        return c.execute(select(func.count()).select_from(reservations)).scalar() or 0


def res_by_status() -> dict:
    with app_engine.connect() as c:
        rows = c.execute(
            select(reservations.c.status, func.count().label("c")).group_by(reservations.c.status)
        ).mappings().all()
    return {r["status"]: r["c"] for r in rows}


def equip_by_status() -> dict:
    with admin_engine.connect() as c:
        rows = c.execute(
            select(equipment.c.status, func.count().label("c")).group_by(equipment.c.status)
        ).mappings().all()
    return {r["status"]: r["c"] for r in rows}


def top_equipment() -> list:
    stmt = (
        select(reservations.c.equipment_name, func.count().label("c"))
        .group_by(reservations.c.equipment_id, reservations.c.equipment_name)
        .order_by(func.count().desc()).limit(5)
    )
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def recent_reservations() -> list:
    stmt = (
        select(
            reservations.c.id, reservations.c.start_time, reservations.c.end_time,
            reservations.c.status, reservations.c.equipment_name,
            users.c.real_name.label("user_name"), users.c.user_type.label("user_type"),
        )
        .select_from(reservations.join(users, users.c.id == reservations.c.user_id))
        .order_by(reservations.c.created_at.desc()).limit(8)
    )
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def list_in_use() -> list:
    """当前使用中的预约（管理员看板「当前使用的设备」）。"""
    stmt = (
        select(
            reservations.c.id, reservations.c.equipment_name, reservations.c.start_time,
            reservations.c.end_time, reservations.c.checkin_at,
            users.c.real_name.label("user_name"), users.c.user_type.label("user_type"),
        )
        .select_from(reservations.join(users, users.c.id == reservations.c.user_id))
        .where(reservations.c.status == "in_use")
        .order_by(reservations.c.checkin_at.desc())
    )
    with app_engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


# ----------------------------- 设置（admin 库） -----------------------------
def set_setting(key: str, value: str) -> None:
    with admin_engine.begin() as c:
        existing = c.execute(select(settings.c.key).where(settings.c.key == key)).first()
        if existing:
            c.execute(update(settings).where(settings.c.key == key).values(value=value, updated_at=now_str()))
        else:
            c.execute(insert(settings).values(key=key, value=value, updated_at=now_str()))


def get_setting(key: str):
    with admin_engine.connect() as c:
        r = c.execute(select(settings.c.value).where(settings.c.key == key)).first()
    return r.value if r else None


# ----------------------------- 初始化 / 种子 -----------------------------
def _columns(engine, table: str, schema: str = None) -> set:
    """返回某表当前列名集合（兼容 SQLite / Postgres）。"""
    if USE_PG:
        sch = schema or APP_SCHEMA
        with engine.connect() as c:
            rows = c.execute(text(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema='{sch}' AND table_name='{table}'"
            )).all()
        return {r[0] for r in rows}
    with engine.connect() as c:
        rows = c.execute(text(f"PRAGMA table_info({table})")).all()
    return {r[1] for r in rows}


def _migrate() -> None:
    """轻量迁移：为旧库 users/equipment 表补齐新列、创建新表（幂等，可重复执行）。"""
    # 新表：create_all 对已存在库也会自动补建
    favorites.create(app_engine, checkfirst=True)
    verify_codes.create(app_engine, checkfirst=True)
    repairs.create(app_engine, checkfirst=True)
    announcements.create(admin_engine, checkfirst=True)

    new_cols = {
        "email": "VARCHAR(120)",
        "user_type": "VARCHAR(20) DEFAULT 'internal'",
        "status": "VARCHAR(20) DEFAULT 'active'",
        "org_name": "VARCHAR(120)",
        "org_type": "VARCHAR(40)",
        "department": "VARCHAR(80)",
        "student_id": "VARCHAR(40)",
        "supervisor": "VARCHAR(64)",
        "email_verified": "INTEGER DEFAULT 0",
        "failed_attempts": "INTEGER DEFAULT 0",
        "locked_until": "VARCHAR(20)",
    }
    existing = _columns(app_engine, "users")
    for col, ddl in new_cols.items():
        if col in existing:
            continue
        with app_engine.begin() as c:
            if USE_PG:
                c.execute(text(f'ALTER TABLE "{APP_SCHEMA}"."users" ADD COLUMN {col} {ddl}'))
            else:
                c.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
        print(f"[migrate] users 表新增列: {col}")

    eq_existing = _columns(admin_engine, "equipment", ADMIN_SCHEMA)
    if "category" not in eq_existing:
        with admin_engine.begin() as c:
            if USE_PG:
                c.execute(text(f'ALTER TABLE "{ADMIN_SCHEMA}"."equipment" ADD COLUMN category VARCHAR(40) DEFAULT \'其他\''))
            else:
                c.execute(text("ALTER TABLE equipment ADD COLUMN category VARCHAR(40) DEFAULT '其他'"))
        print("[migrate] equipment 表新增列: category")


def init_db() -> None:
    if USE_PG:
        for sch in (ADMIN_SCHEMA, APP_SCHEMA):
            with admin_engine.begin() as c:
                c.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{sch}"'))
    admin_meta.create_all(admin_engine)
    app_meta.create_all(app_engine)
    _migrate()
    _seed()


def _seed() -> None:
    # 管理员：仅首次创建，生成强密码并持久化（解决“管理员账号不能让客户知道”）
    with admin_engine.connect() as c:
        has_admin = c.execute(select(admin_users.c.id).limit(1)).first()
    if not has_admin:
        pw = os.environ.get("ADMIN_PASSWORD") or secrets.token_hex(8).upper()
        with admin_engine.begin() as c:
            c.execute(insert(admin_users).values(
                username="admin", password_hash=hash_pwd(pw),
                display_name="系统管理员", created_at=now_str(),
            ))
        set_setting("admin_password", pw)
        try:
            with open(os.path.join(BASE_DIR, "ADMIN_PASSWORD.txt"), "w", encoding="utf-8") as f:
                f.write(pw)
        except Exception:
            pass
        print(f"[init] 管理员初始密码已生成：{pw}（已写入 ADMIN_PASSWORD.txt 与 admin 库 settings 表）")

    # 设备目录：仅首次填充示例设备（管理员可在后台任意增删改，属真实管理数据）
    with admin_engine.connect() as c:
        has_eq = c.execute(select(equipment.c.id).limit(1)).first()
    if not has_eq:
        sample = [
            ("扫描电子显微镜", "SU-70", "实验楼A座301", "available", "王教授", "高分辨形貌观测，需提前培训"),
            ("紫外可见分光光度计", "UV-2600", "实验楼B座102", "available", "陈老师", "常规吸光度测试"),
            ("高速冷冻离心机", "CF16RX", "实验楼B座105", "maintenance", "陈老师", "转子维护中，暂停预约"),
            ("核磁共振波谱仪", "Bruker 400M", "实验楼C座201", "available", "赵研究员", "有机物结构鉴定"),
            ("激光共聚焦显微镜", "LSM 880", "实验楼A座305", "available", "王教授", "活细胞成像"),
            ("气相色谱质谱联用仪", "GCMS-QP2020", "实验楼C座210", "disabled", "赵研究员", "待检定，暂不开放"),
        ]
        with admin_engine.begin() as c:
            for name, model, loc, st, mgr, desc in sample:
                c.execute(insert(equipment).values(
                    name=name, model=model, location=loc, status=st,
                    manager=mgr, description=desc, created_at=now_str(),
                ))


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成。use_pg =", USE_PG)
