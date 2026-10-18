"""设备登录(签到/签退)流程端到端测试。"""
import json, time, urllib.request, urllib.error

B = "http://127.0.0.1:8000"
FAILED = False


def req(p, m="GET", token=None, body=None, tries=40):
    d = json.dumps(body).encode() if body is not None else None
    for _ in range(tries):
        try:
            r = urllib.request.Request(B + p, data=d, method=m)
            if d is not None:
                r.add_header("Content-Type", "application/json")
            if token:
                r.add_header("Authorization", "Bearer " + token)
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            time.sleep(0.4)
    raise RuntimeError("server down")


def login(u, p):
    s, d = req("/api/login", "POST", body={"username": u, "password": p})
    assert s == 200, f"login {u} {s}"
    return d["token"]


def ck(name, cond, extra=""):
    global FAILED
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILED = True


ut = login("zhangsan", "123456")
at = login("admin", "admin123")

# 选一台当前空闲设备(紫外可见分光光度计 id=2)
s, d = req("/api/reservations", "POST", ut, {"equipment_id": 2, "start_time": "2027-06-01 09:00", "end_time": "2027-06-01 11:00", "purpose": "设备登录流程测试"})
ck("提交预约", s == 200, str(d))
rid = d["id"]

# 管理员审核通过
s, d = req(f"/api/reservations/{rid}/approve", "POST", at, {"note": ""})
ck("管理员通过", s == 200, f"{s}")

# 预约人登录设备(开始使用) -> in_use
s, d = req(f"/api/reservations/{rid}/checkin", "POST", ut)
ck("登录设备(in_use)", s == 200, f"{s} {d}")

s, mine = req("/api/reservations/mine?status=in_use", token=ut)
ck("我的预约出现'使用中'", any(r["id"] == rid for r in mine), f"in_use数={len(mine)}")

# 使用中应阻止同设备新预约(冲突校验覆盖 in_use)
s, d = req("/api/reservations", "POST", ut, {"equipment_id": 2, "start_time": "2027-06-01 10:00", "end_time": "2027-06-01 12:00"})
ck("使用中冲突拦截(409)", s == 409, f"{s} {d.get('detail')}")

# 结束使用(签退) -> used
s, d = req(f"/api/reservations/{rid}/checkout", "POST", ut)
ck("结束使用(used)", s == 200, f"{s} {d}")

s, mine = req("/api/reservations/mine?status=used", token=ut)
ck("我的预约出现'已完成'", any(r["id"] == rid for r in mine))

# 异常路径:非本人不能登录别人的预约
s2 = login("lisi", "123456")
s, d = req(f"/api/reservations/{rid}/checkin", "POST", s2)
ck("他人不可登录(403)", s == 403, f"{s}")

# 统计看板应含 in_use 维度
s, st = req("/api/stats", token=at)
ck("统计接口正常", s == 200)
print("\n=== 设备登录流程:", "全部通过" if not FAILED else "存在失败 ===")
