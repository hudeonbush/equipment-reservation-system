"""清理冒烟测试产生的测试数据（仅删除测试标记的数据）。"""
import sqlalchemy as sa
import db

with db.app_engine.begin() as c:
    r1 = c.execute(sa.text("DELETE FROM reservations WHERE purpose = '校外用户预约测试' OR purpose = '测试' OR purpose = '冲突'"))
    r2 = c.execute(sa.text("DELETE FROM users WHERE username LIKE 'nei%' OR username LIKE 'wai%' OR username LIKE 'smoke%' OR username LIKE 'ui%' OR username = 'testuser' OR email LIKE '%@test.com'"))
    r3 = c.execute(sa.text("DELETE FROM favorites"))
    r4 = c.execute(sa.text("DELETE FROM verify_codes"))
    r5 = c.execute(sa.text("DELETE FROM repairs WHERE issue = '开机无响应' OR equipment_name LIKE '测试%'"))
with db.admin_engine.begin() as c:
    r6 = c.execute(sa.text("DELETE FROM equipment WHERE name LIKE '测试%'"))
    r7 = c.execute(sa.text("DELETE FROM announcements WHERE title = '测试公告'"))
    print(f"清理完成: 预约 {r1.rowcount} 条, 用户 {r2.rowcount} 个, 收藏 {r3.rowcount} 条, 验证码 {r4.rowcount} 条, 报修 {r5.rowcount} 条, 设备 {r6.rowcount} 台, 公告 {r7.rowcount} 条")

print("剩余用户:")
for u in db.list_users("", "", ""):
    print(" ", u["id"], u["username"], u["real_name"], u["user_type"], u["status"])
