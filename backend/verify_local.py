"""本地全链路验证（双库）：用 FastAPI TestClient 跑通真实 HTTP 流程。"""
import sys, os
from datetime import datetime, timedelta

P = os.path.join(os.path.dirname(__file__))
sys.path.insert(0, P)

import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

def H(tok=None):
    return {"X-Auth-Token": tok} if tok else {}

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (("  " + extra) if extra else ""))
    if not cond:
        ok = False

# 1) 管理员初始密码
pw = open(os.path.join(P, "ADMIN_PASSWORD.txt"), encoding="utf-8").read().strip()
check("管理员密码文件存在", bool(pw), pw)

# 2) 管理员独立登录
r = client.post("/api/admin/login", json={"username": "admin", "password": pw})
check("管理员登录 200", r.status_code == 200, str(r.status_code))
admin_tok = r.json().get("token")
check("管理员令牌返回", bool(admin_tok))

# 3) 管理员无法通过预约人登录入口登录（库物理隔离）
r2 = client.post("/api/login", json={"username": "admin", "password": pw})
check("管理员不能从客户入口登录(401)", r2.status_code == 401, str(r2.status_code))

# 4) 预约人注册 + 登录
u = "wangwu_" + datetime.now().strftime("%H%M%S")
r = client.post("/api/register", json={"username": u, "password": "123456", "real_name": "王五", "phone": "139"})
check("预约人注册 200", r.status_code == 200, str(r.status_code))
r = client.post("/api/login", json={"username": u, "password": "123456"})
check("预约人登录 200", r.status_code == 200)
user_tok = r.json().get("token")
check("预约人令牌返回", bool(user_tok))

# 5) 设备目录（用户可见）
r = client.get("/api/equipment", headers=H(user_tok))
eqs = r.json()
check("设备列表>=6", isinstance(eqs, list) and len(eqs) >= 6, f"n={len(eqs)}")

# 6) 提交预约（设备1，未来时间）
start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d") + " 09:00"
end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d") + " 11:00"
r = client.post("/api/reservations", headers=H(user_tok),
                json={"equipment_id": 1, "start_time": start, "end_time": end, "purpose": "样品形貌表征"})
check("提交预约 200", r.status_code == 200, str(r.status_code))
rid = r.json().get("id")
check("预约 id 返回", bool(rid), f"rid={rid}")

# 7) 时间冲突（同一设备重叠）
r = client.post("/api/reservations", headers=H(user_tok),
                json={"equipment_id": 1, "start_time": start[:11] + "09:30", "end_time": start[:11] + "10:30", "purpose": "冲突"})
check("冲突检测 409", r.status_code == 409, str(r.status_code))

# 8) 管理员看到真实预约人的预约（不是模板）
r = client.get("/api/reservations", headers=H(admin_tok))
allres = r.json()
mine = [x for x in allres if x.get("user_name") == "王五"]
check("管理员审批列表含真实预约人", len(mine) >= 1, f"count={len(mine)}")
check("预约人姓名正确", mine and mine[0]["user_name"] == "王五")

# 9) 管理员审批
r = client.post(f"/api/reservations/{rid}/approve", headers=H(admin_tok), json={"note": "同意"})
check("审批 200", r.status_code == 200, str(r.status_code))

# 10) 预约人登录设备（签到）/签退
r = client.post(f"/api/reservations/{rid}/checkin", headers=H(user_tok))
check("签到 200", r.status_code == 200)
r = client.post(f"/api/reservations/{rid}/checkout", headers=H(user_tok))
check("签退 200", r.status_code == 200)

# 11) 模糊查询
r = client.get("/api/reservations?kw=王五", headers=H(admin_tok))
check("模糊查询命中", isinstance(r.json(), list) and len(r.json()) >= 1, f"n={len(r.json())}")

# 12) 统计看板
r = client.get("/api/stats", headers=H(admin_tok))
s = r.json()
check("统计:预约人数>=1", s["total_users"] >= 1, f"users={s['total_users']}")
check("统计:预约总数>=1", s["total_reservations"] >= 1, f"res={s['total_reservations']}")

# 13) 双库分离确认
import db as D
check("admin 库存管理员账号", D.get_admin("admin") is not None)
check("app 库存预约人", D.get_user(u) is not None)
check("app 库无管理员账号", D.get_user("admin") is None)
check("admin 库无预约人账号", D.get_admin(u) is None)

print("\n结果:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
