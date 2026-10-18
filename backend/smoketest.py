"""端到端冒烟测试：覆盖登录、模糊查询、预约冲突、审批、统计。"""
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
    s, d = req("/api/admin/login", "POST", body={"username": u, "password": p})
    assert s == 200, f"admin login {u} failed: {s} {d}"
    return d["token"]


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        global FAILED
        FAILED = True


FAILED = False

# 1) 等待服务
req("/api/equipment", tries=40)
print("server up")

# 2) 管理员登录（独立入口 /api/admin/login，密码见 ADMIN_PASSWORD.txt）
at = admin_login("admin", ADMIN_PWD)
check("管理员登录", bool(at))

# 3) 模糊查询：显微镜 应命中 扫描电子显微镜 & 激光共聚焦显微镜
s, d = req("/api/equipment?kw=" + urllib.parse.quote("显微镜"), token=at)
names = [e["name"] for e in d]
check("模糊查询'显微镜'", any("扫描电子显微镜" in n for n in names) and any("激光共聚焦" in n for n in names), str(names))

# 4) 模糊查询：离心 应命中 高速冷冻离心机
s, d = req("/api/equipment?kw=" + urllib.parse.quote("离心"), token=at)
check("模糊查询'离心'", any("高速冷冻离心机" in e["name"] for e in d), str([e["name"] for e in d]))

# 5) 动态注册一个校内测试用户并登录（避免依赖演示账号；邮箱验证走开发模式）
uname = f"smoke{int(time.time()) % 100000}"
s, d = req("/api/send-code", "POST", body={"email": f"{uname}@test.com", "purpose": "register"})
code = d.get("dev_code")
s, d = req("/api/register", "POST", body={
    "username": uname, "password": "123456",
    "real_name": "冒烟测试", "user_type": "internal", "department": "测试院系",
    "email": f"{uname}@test.com", "email_code": code,
})
check("注册校内测试用户", s == 200, f"{s} {d}")
ut = login(uname, "123456")
check("测试用户登录", bool(ut))
uid = d["user_id"]

# 6) 提交不冲突预约（设备1，2026-09-25 09:00~11:00）
s, d = req("/api/reservations", "POST", ut, {"equipment_id": 1, "start_time": "2026-09-25 09:00", "end_time": "2026-09-25 11:00", "purpose": "测试"})
check("提交预约成功", s == 200, f"{s} {d}")

# 7) 冲突预约（10:00~12:00 与上面重叠）应 409
s, d = req("/api/reservations", "POST", ut, {"equipment_id": 1, "start_time": "2026-09-25 10:00", "end_time": "2026-09-25 12:00", "purpose": "冲突"})
check("冲突被拦截(409)", s == 409, f"{s} {d.get('detail')}")

# 8) 结束早于开始应 400
s, d = req("/api/reservations", "POST", ut, {"equipment_id": 1, "start_time": "2026-09-26 12:00", "end_time": "2026-09-26 11:00"})
check("时间校验(400)", s == 400, f"{s}")

# 9) 管理员审批第一条 pending
s, d = req("/api/reservations?status=pending", token=at)
pend = [r for r in d if r["user_id"] == uid]
rid = pend[0]["id"] if pend else None
check("存在待审预约", rid is not None)
if rid:
    s, d = req(f"/api/reservations/{rid}/approve", "POST", at, {"note": ""})
    check("审批通过", s == 200, f"{s} {d}")

# 10) 管理员统计
s, d = req("/api/stats", token=at)
check("统计接口", s == 200 and "total_reservations" in d, str({k: d.get(k) for k in ["total_equipment", "total_users", "total_reservations"]}))

# 11) 我的预约
s, d = req("/api/reservations/mine", token=ut)
check("我的预约列表", s == 200 and len(d) >= 1, f"count={len(d)}")

# 12) 注册新用户（邮箱验证）
s, d = req("/api/send-code", "POST", body={"email": "testuser@test.com", "purpose": "register"})
code = d.get("dev_code")
s, d = req("/api/register", "POST", body={
    "username": "testuser", "password": "123456", "real_name": "测试",
    "email": "testuser@test.com", "email_code": code,
})
check("注册新用户", s == 200, f"{s} {d}")

# 13) 无 token 访问受保护接口应 401
s, d = req("/api/equipment")
check("未授权拦截(401)", s == 401, f"{s}")

print("\n=== 结果:", "全部通过" if not FAILED else "存在失败 ===")
