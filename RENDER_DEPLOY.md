# Render 免费部署（一条龙：应用 + PostgreSQL 云数据库，0 元、免绑卡）

想让系统**公网可访问 + 账号密码存云端**，又暂时没有自己的服务器？
用 **Render 免费档**即可：Web 服务（FastAPI）+ PostgreSQL 云数据库都在云端，
自动 HTTPS、免费公网域名（`xxx.onrender.com`），无需信用卡。

> 说明：免费 Web 服务 15 分钟无人访问会休眠，再次访问约等 10~50 秒唤醒（可接受，先跑通验证）。
> 免费数据库建议仅用于测试；正式长期使用推荐 SELF_HOSTING.md 自有服务器方案。

---

## 准备

1. **GitHub 账号**（可选）：把项目推到 GitHub 仓库，部署最快；
   没有也能用，把项目打成 zip 上传。
2. 邮箱一个（注册 Render 用）。

## 方式 A：GitHub + Blueprint（推荐，一条命令建好应用+数据库）

1. 项目根目录已有 `render.yaml`（自动创建 Web 服务 + 免费 Postgres + 环境变量）。
2. 把项目推送到 GitHub：
   ```bash
   cd equipment-reservation-system
   git init && git add -A && git commit -m "v4"
   git remote add origin https://github.com/你的用户名/equipment-reservation.git
   git push -u origin main
   ```
3. 打开 <https://dashboard.render.com> → 右上角 **New + → Blueprint** → 选择该仓库。
4. Render 自动创建：
   - Web 服务 `equipment-reservation`（free plan）
   - 数据库 `equipment-db`（free Postgres，自动注入 `DATABASE_URL`）
   - 首次部署自动建表（admin/app 两个 schema 自动创建）
5. 等构建完成（约 3~6 分钟），点服务页顶部链接 `https://equipment-reservation.onrender.com` 即可访问。

## 方式 B：无 GitHub（手动上传）

1. <https://dashboard.render.com> → **New + → Web Service** → 选 **Upload a folder**（或把项目打成 zip 上传）。
2. 填：Name=equipment-reservation，Runtime=Python 3，Build Command=`pip install -r backend/requirements.txt`，
   Start Command=`cd backend && python main.py`，Instance Type=Free。
3. **Environment → Add Environment Variable**：
   - `DATABASE_URL`：先按方式 C 建免费 Postgres，把它的 Internal Database URL 填进来
   - `ADMIN_PASSWORD`：管理员初始密码
4. Deploy。首次构建后访问 `https://equipment-reservation.onrender.com`。

## 方式 C：单独建免费 Postgres

Dashboard → **New + → PostgreSQL** → plan=Free → Create。
创建后在 **Connections** 面板复制 **Internal Database URL**（形如 `postgres://...`，程序已兼容）。
把它填到 Web 服务的 `DATABASE_URL` 环境变量。

---

## 部署后必须做的

| 步骤 | 操作 |
|------|------|
| 1. 管理员密码 | 设置 `ADMIN_PASSWORD` 环境变量（服务重启生效，仅首次建库用） |
| 2. 邮箱验证 | 在 Environment 添加 `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/MAIL_FROM`（QQ/163 授权码，见 SUPABASE_SETUP.md） |
| 3. 验证云端 | 注册一个新账号 → Render 控制台 → 数据库 → Run SQL 查 `app.users` 有记录 |
| 4. 公告/报修 | 管理后台 `https://xxx.onrender.com/admin.html` 用管理员登录体验 |

## 常见问题

**Q：免费 Postgres 会被删吗？**
免费数据库会在创建 30 天后被 Render 暂停（数据保留，续费/升级后恢复）。测试期够用；正式用请按 SELF_HOSTING.md 换自有服务器 + Supabase/本机 PG。

**Q：国内访问慢？**
onrender.com 在国内速度一般（时快时慢）。仅测试没问题；正式对外建议自有服务器（SELF_HOSTING.md）或国内云（阿里云轻量等）。

**Q：数据库表怎么自动建的？**
`db.py` 检测到 `DATABASE_URL` 后自动进入云端模式：建 `admin`/`app` 两个 schema，幂等迁移全部表（users/equipment/reservation/favorites/verify_codes/repairs/announcements/…），无需手动执行 SQL。
