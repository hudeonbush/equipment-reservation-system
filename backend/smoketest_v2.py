"""V2 冒烟测试：三角色账号管理（校内/校外/管理员）+ 设备收藏 + 预约权限。

覆盖：
  1) 服务可用
  2) 管理员登录（密码从 ADMIN_PASSWORD.txt 读取）
  3) 校内用户注册 -> 直接 active -> 可登录 -> 可预约
  4) 校外用户注册 -> pending -> 登录被拒(403)
  5) 管理员用户列表 / 审核激活校外用户 -> 可登录 -> 可预约
  6) 管理员 禁用/启用 用户
  7) 管理员重置密码
  8) 设备收藏 增/删/查
  9) 统计接口含 pending_users / in_use
  10) 预约人列表带 user_type（校内/校外标签）
"""
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse

BASE = "http://127.0.0.1:8000"
ADMIN_PWD = open(os.path.join(os.path.dirname(__file__), "ADMIN_PASSWORD.txt"), encoding="utf-8").read().strip()


def req(path, method="GET", token=None, body=None, tries=30):
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for _ in range(tries):
        try:
            r = urllib.request.Request(BASE + path, data=data, method=method)
            if data is not None:
                r.add_header("Content-Type", "application/json")
            if token:
                r.add_header("Authorization", "Bearer " + token)
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except Exception:
                return e.code, {}
        except Exception as e:
            last = e
            time.sleep(0.4)
    raise RuntimeError(f"server not reachable: {last}")


def login(u, p):
    s, d = req("/api/login", "POST", body={"username": u, "password": p})
    assert s == 200, f"login {u} failed: {s} {d}"
    return d["token"]


def admin_login(u, p):
    """管理员走独立入口 /api/admin/login（与预约人物理隔离）。"""
    s, d = req("/api/admin/login", "POST", body={"username": u, "password": p})
    assert s == 200, f"admin login {u} failed: {s} {d}"
    return d["token"]


def send_code(email, purpose):
    """发送验证码（开发模式：接口返回 dev_code）。"""
    s, d = req("/api/send-code", "POST", body={"email": email, "purpose": purpose})
    assert s == 200, f"send-code {purpose} failed: {s} {d}"
    assert "dev_code" in d, f"开发模式应返回 dev_code: {d}"
    return d["dev_code"]


def register_user(**kw):
    """带邮箱验证码注册（开发模式）。"""
    email = kw.pop("email")
    code = send_code(email, "register")
    s, d = req("/api/register", "POST", body={**kw, "email": email, "email_code": code})
    assert s == 200, f"register {kw.get('username')} failed: {s} {d}"
    return d


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        global FAILED
        FAILED = True


FAILED = False
SUF = str(int(time.time()))[-6:]  # 唯一后缀，避免测试数据与真实数据混淆

# 1) 服务可用
req("/api/equipment", tries=40)
print("server up")

# 2) 管理员登录
at = admin_login("admin", ADMIN_PWD)
check("管理员登录", bool(at))

# 3) 校内用户注册（邮箱验证）-> active
un = f"nei{SUF}"
em = f"{un}@test.com"
d = register_user(
    username=un, password="123456", real_name="校内测试", email=em,
    user_type="internal", department="材料学院", student_id="2026" + SUF,
    supervisor="王教授",
)
check("校内用户注册", d.get("status") == "active", f"{d}")
uid_nei = d["user_id"]
ut = login(un, "123456")
check("校内用户可登录", bool(ut))
s, d = req("/api/me", token=ut)
check("me 返回用户类型", d.get("user_type") == "internal" and d.get("status") == "active", f"{d.get('user_type')}/{d.get('status')}")

# 4) 校外用户注册（邮箱验证）-> pending -> 不能登录
ux = f"wai{SUF}"
emx = f"{ux}@test.com"
d = register_user(
    username=ux, password="123456", real_name="校外测试", email=emx,
    user_type="external", org_name="某某科技有限公司", org_type="企业",
    supervisor="李老师",
)
check("校外用户注册进入待审核", d.get("status") == "pending", f"{d}")
s, d = req("/api/login", "POST", body={"username": ux, "password": "123456"})
check("待审核用户登录被拒(403)", s == 403, f"{s} {d.get('detail')}")

# 4.1) 邮箱重复注册应 409；错误验证码注册应 400
s, d = req("/api/register", "POST", body={
    "username": f"dup{SUF}", "password": "123456", "real_name": "重复", "email": emx, "email_code": "000000",
})
check("邮箱重复注册被拒(409)", s == 409, f"{s} {d.get('detail')}")
s, d = req("/api/register", "POST", body={
    "username": f"bad{SUF}", "password": "123456", "real_name": "错码",
    "email": f"bad{SUF}@test.com", "email_code": "000000",
})
check("错误验证码注册被拒(400)", s == 400, f"{s} {d.get('detail')}")

# 5) 管理员用户列表 -> 审核激活校外用户
s, d = req(f"/api/users?kw={ux}", token=at)
check("管理员用户列表可查到校外用户", s == 200 and any(u["username"] == ux for u in d), f"s={s}")
uid = next(u["id"] for u in d if u["username"] == ux)
s, d = req(f"/api/users/{uid}/approve", "POST", at)
check("审核激活校外用户", s == 200, f"{s} {d}")
xt = login(ux, "123456")
check("激活后可登录", bool(xt))

# 6) 校外用户激活后可预约（设备1）
s, d = req("/api/reservations", "POST", xt, {
    "equipment_id": 1, "start_time": f"2026-12-{1:02d} 09:00",
    "end_time": f"2026-12-{1:02d} 11:00", "purpose": "校外用户预约测试",
})
check("校外用户可提交预约", s == 200, f"{s} {d}")

# 7) 禁用 -> 不能登录（先登录一次创建会话，再禁用后老会话仍有效但新登录被拒）
s, d = req(f"/api/users/{uid}/toggle", "POST", at)
check("禁用用户", s == 200 and d.get("status") == "disabled", f"{s} {d}")
s, d = req("/api/login", "POST", body={"username": ux, "password": "123456"})
check("禁用用户登录被拒(403)", s == 403, f"{s} {d.get('detail')}")
s, d = req(f"/api/users/{uid}/toggle", "POST", at)
check("重新启用用户", s == 200 and d.get("status") == "active", f"{s} {d}")

# 8) 管理员重置密码
s, d = req(f"/api/users/{uid}/reset-password", "POST", at, {"new_password": "654321"})
check("重置密码", s == 200, f"{s} {d}")
s, d = req("/api/login", "POST", body={"username": ux, "password": "654321"})
check("新密码可登录", s == 200, f"{s}")

# 9) 设备收藏 增/删/查
s, d = req("/api/favorites", token=ut)
check("收藏列表初始为空", s == 200 and d.get("ids") == [], f"{d}")
s, d = req("/api/favorites/1", "POST", ut)
check("收藏设备1", s == 200, f"{s}")
s, d = req("/api/favorites/2", "POST", ut)
s, d = req("/api/favorites", token=ut)
check("收藏列表含 1,2", s == 200 and set(d.get("ids")) == {1, 2}, f"{d}")
s, d = req("/api/favorites/1", "DELETE", ut)
s, d = req("/api/favorites", token=ut)
check("取消收藏设备1", s == 200 and d.get("ids") == [2], f"{d}")
s, d = req("/api/favorites/999", "POST", ut)
check("收藏不存在设备(404)", s == 404, f"{s}")

# 10) 统计含 pending_users / in_use
s, d = req("/api/stats", token=at)
check("统计含待审核用户数", s == 200 and "pending_users" in d, f"pending_users={d.get('pending_users')}")
check("统计含使用中设备", s == 200 and "in_use" in d, f"in_use={len(d.get('in_use', []))}")

# 11) 预约人列表带 user_type
s, d = req("/api/reservations", token=at)
check("管理员预约列表带用户类型", s == 200 and len(d) >= 1 and "user_type" in d[0], f"{d[0] if d else 'empty'}")

# 12) 校外用户注册信息完整保留
s, d = req(f"/api/users?kw={ux}", token=at)
u = next((x for x in d if x["username"] == ux), None)
check("校外用户单位信息保存", u and u["org_name"] == "某某科技有限公司" and u["user_type"] == "external", f"{u}")

# 13) 设备详情 + 排期可视化（预约冲突可视化）
s, d = req("/api/equipment/1", token=ut)
check("设备详情接口", s == 200 and "schedule" in d and "usage_history" in d, f"s={s}")
check("排期含未完成预约", any(r["user_name"] == "校外测试" for r in d["schedule"]), f"{[r['user_name'] for r in d['schedule']]}")

# 14) 设备详情中设备不存在应 404
s, d = req("/api/equipment/999", token=ut)
check("设备详情不存在(404)", s == 404, f"{s}")

# 15) 我的预约分类数据完整性（校外用户有 pending 预约）
s, d = req("/api/reservations/mine", token=xt)
statuses = {r["status"] for r in d}
check("我的预约含进行中状态", "pending" in statuses, f"{statuses}")

# 16) 忘记密码：邮箱验证码重置密码
code = send_code(emx, "reset")
s, d = req("/api/reset-password", "POST", body={"email": emx, "code": code, "new_password": "888888"})
check("邮箱验证码重置密码", s == 200, f"{s} {d}")
s, d = req("/api/login", "POST", body={"username": ux, "password": "888888"})
check("重置后新密码可登录", s == 200, f"{s}")
s, d = req("/api/forgot-password", "POST", body={"email": "nobody@none.com"})
check("未注册邮箱发码(404)", s == 404, f"{s}")

# 17) 错误重置验证码应 400
code2 = send_code(emx, "reset")
s, d = req("/api/reset-password", "POST", body={"email": emx, "code": "000000", "new_password": "999999"})
check("错误重置验证码被拒(400)", s == 400, f"{s} {d.get('detail')}")

# 18) 登录失败锁定（借鉴毕设防爆破）：连续 5 次错误密码 -> 锁定
for i in range(1, 5):
    s, d = req("/api/login", "POST", body={"username": un, "password": "wrong"})
    assert s == 401, f"第{i}次错误登录应401"
s, d = req("/api/login", "POST", body={"username": un, "password": "wrong"})
check("第5次错误密码触发锁定", s == 401 and "锁定" in d.get("detail", ""), f"{s} {d.get('detail')}")
s, d = req("/api/login", "POST", body={"username": un, "password": "123456"})
check("锁定期间正确密码也被拒(403)", s == 403 and "锁定" in d.get("detail", ""), f"{s} {d.get('detail')}")
s, d = req(f"/api/users/{uid_nei}/reset-password", "POST", at, {"new_password": "123456"})
check("管理员重置密码可解锁", s == 200, f"{s} {d}")
s, d = req("/api/login", "POST", body={"username": un, "password": "123456"})
check("解锁后可正常登录", s == 200, f"{s}")

# 19) 设备分类（借鉴毕设设备类别管理）
s, d = req("/api/equipment", "POST", at, {
    "name": "测试荧光光谱仪", "category": "光谱仪", "model": "FS-01",
    "location": "测试室", "status": "available", "manager": "测试员", "description": "分类测试",
})
check("管理员创建设备带分类", s == 200, f"{s} {d}")
s, d = req("/api/equipment?" + urllib.parse.urlencode({"category": "光谱仪"}), token=ut)
check("设备分类筛选", s == 200 and any(e["name"] == "测试荧光光谱仪" for e in d), f"{[e['name'] for e in d]}")

# 20) 通知公告（借鉴毕设公告模块）
s, d = req("/api/announcements", "POST", body={"title": "测试公告", "content": "本周六设备维护"}, token=at)
check("管理员发布公告", s == 200, f"{s} {d}")
aid = d["id"]
s, d = req("/api/announcements", token=ut)
check("用户可见公告", s == 200 and any(a["id"] == aid for a in d["list"]), f"{[a['title'] for a in d['list']]}")
s, d = req(f"/api/announcements/{aid}/toggle", "PUT", token=at)
check("停用公告", s == 200, f"{s}")
s, d = req("/api/announcements", token=ut)
check("停用后用户不可见", s == 200 and not any(a["id"] == aid for a in d["list"]), f"{[a['title'] for a in d['list']]}")

# 21) 设备报修（借鉴毕设设备报障流程）
s, d = req("/api/repairs", "POST", body={"equipment_id": 3, "issue": "开机无响应"}, token=ut)
check("用户提交报修", s == 200, f"{s} {d}")
rid = d["id"]
s, d = req("/api/equipment/3", token=ut)
check("报修后设备进入维护中", d["status"] == "maintenance", f"{d['status']}")
s, d = req("/api/repairs", token=at)
check("管理员可见报修列表", s == 200 and any(x["id"] == rid for x in d["list"]), f"{len(d['list'])}")
s, d = req(f"/api/repairs/{rid}/handle", "PUT", body={"status": "handling", "note": "已定位故障"}, token=at)
check("开始处理报修", s == 200, f"{s}")
s, d = req(f"/api/repairs/{rid}/handle", "PUT", body={"status": "fixed", "note": "已更换电源模块"}, token=at)
check("标记已修复", s == 200, f"{s}")
s, d = req("/api/equipment/3", token=ut)
check("修复后设备恢复可用", d["status"] == "available", f"{d['status']}")
s, d = req("/api/repairs", token=ut)
check("我的报修可见", s == 200 and any(x["id"] == rid for x in d["list"]), f"{[x['status'] for x in d['list']]}")
s, d = req("/api/stats", token=at)
check("统计含待处理报修字段", "pending_repairs" in d, f"{list(d.keys())}")

print("\n=== 结果:", "全部通过" if not FAILED else "存在失败 ===")
