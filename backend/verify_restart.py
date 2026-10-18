"""重启持久化验证（新进程读取已有库文件）：证明注册/预约数据在重启后仍在，且两个库物理分离。"""
import os, sqlite3, sys
P = os.path.dirname(__file__)
sys.path.insert(0, P)
import db as D

def tables_of(path):
    if not os.path.isfile(path):
        return None
    c = sqlite3.connect(path)
    try:
        return [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    finally:
        c.close()

for f in ("admin.db", "app.db"):
    p = os.path.join(P, f)
    print(f"{f:10s} size={os.path.getsize(p) if os.path.isfile(p) else 0:>7}B  tables={tables_of(p)}")

print()
print("重启后读取（模拟更新/重启）：")
print("  预约人数量 =", D.count_users())
print("  预约数量   =", D.count_reservations())
print("  设备数量   =", D.count_equipment())
print("  管理员存在 =", D.get_admin("admin") is not None)
print("  预约状态分布 =", D.res_by_status())
print()
print("结论:", "数据已持久化" if D.count_users() >= 1 and D.count_reservations() >= 1 else "数据丢失")
