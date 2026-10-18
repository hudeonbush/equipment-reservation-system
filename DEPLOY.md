# 实验设备预约系统 —— 部署与分享教程（双库版 v2）

## 本次重构解决了什么

| 你反馈的问题 | 原因 | 修复 |
|--------------|------|------|
| 管理员账号不能让客户知道 | 旧版把 `admin` 当成一个 `role='admin'` 的用户，和预约人放在**同一张表**，登录页还直接印着 `admin / admin123` | 管理员独立成 **admin 库**，独立登录接口 `/api/admin/login`；客户登录页已删除提示，且管理员**无法**从客户入口登录 |
| 用户注册后每次更新都要重新注册 | 部署沙箱会在回收/重启时**清空运行时生成的 SQLite 文件** | 改为可接**外部托管数据库（Supabase）**，数据在云端，回收不丢 |
| 没有保管用户数据和数据库 | 同上，SQLite 被清空 | 同上；本地则落盘为 `admin.db` / `app.db` 两个文件，重启仍在 |
| 管理员审批的只是模板不是用户数据 | 库被清空后只剩种子数据 | 预约全部落在 **app 库**，管理员审批的就是真实预约人的行 |
| 需要两个数据库 | 旧版只有一个库 | 已拆分为 **admin 库** + **app 库**（见下） |

---

## 双数据库设计

```
admin 库（本地 admin.db / 云端 Postgres schema `admin`）
  ├── admin_users   管理员账号（客户侧完全不可见）
  ├── equipment     设备目录（管理员增删改）
  └── settings      系统设置（含初始化管理员密码）

app 库（本地 app.db / 云端 Postgres schema `app`）
  ├── users         预约人账号（真实注册用户）
  ├── sessions      登录会话（role 字段区分 admin / user）
  └── reservations  真实预约记录（含设备名快照，避免跨库 join）
```

- 预约人注册/登录 → 只写 **app 库**
- 管理员登录 → 只查 **admin 库**
- 管理员审批/登录设备/签退 → 读写 **app 库里真实预约人的预约**
- 两个库通过 SQLAlchemy 双引擎管理，**云端共用同一个 Postgres 连接串，靠 schema 区分**

---

## 账号与入口

| 角色 | 入口 | 说明 |
|------|------|------|
| 预约人 | `index.html`（根地址） | 注册 / 登录 → `user.html`。页面上**没有任何**管理员信息 |
| 管理员 | 直接访问 `admin.html` | 独立登录框，POST `/api/admin/login`。**该入口不在客户页面做任何链接**，且密码是首次初始化随机生成的强密码 |

管理员初始密码生成在：`backend/ADMIN_PASSWORD.txt`（同时存入 admin 库 `settings` 表以便云端持久）。

> 本地当前生成的密码示例：`966F4CF29165A3C3`（以你本机该文件内容为准）
> 想自定义：在 `backend/.env` 里写 `ADMIN_PASSWORD=你的强密码`，**首次初始化前**设置生效。

---

## 数据持久化（重要）

- **本地运行**：使用 `admin.db` / `app.db` 两个 SQLite 文件，写在磁盘上，重启/更新代码都不丢。
- **发布到云端（WorkBuddy 发布为应用）**：沙箱只有一个 HTTP 端口，且会**回收运行时文件**，
  SQLite 会在回收后丢失。要真正持久化，**必须接 Supabase**（托管 Postgres，沙箱可访问外网）。

### 接 Supabase 步骤

1. 打开 https://supabase.com → 新建项目（免费档即可）。
2. 进入 **Project Settings → Database → Connection string → URI**，复制连接串，形如：
   ```
   postgresql://postgres:<你的密码>@db.<项目ID>.supabase.co:5432/postgres
   ```
3. 把 `backend/.env.example` 复制为 `backend/.env`，填入：
   ```
   DATABASE_URL=postgresql://postgres:<你的密码>@db.<项目ID>.supabase.co:5432/postgres
   ADMIN_PASSWORD=你想设的管理员强密码
   ```
4. 重启服务，程序会自动在云端创建 `admin` / `app` 两个 schema 及全部表。
   之后所有用户注册、预约都会写入 Supabase，**回收/重新发布都不再丢数据**。

> 说明：发布平台的预检查允许「指向公网托管数据库的连接串」（如 Supabase），
> 但会拒绝指向 localhost / compose 服务名的连接串。
> 项目使用 `pg8000`（纯 Python Postgres 驱动）以免触发「额外数据库服务」的限制。

---

## 部署方式

### 方式一：局域网共享（0 成本，最快）

```bash
python backend/main.py
```
查本机 IP（Windows）：`ipconfig | findstr IPv4`，同 WiFi 的人访问 `http://<你的IP>:8000`。
若打不开，在防火墙「允许应用通过防火墙」里放行 python。

### 方式二：WorkBuddy「发布为应用」

- 已发布过一次，得到分享链接；管理入口：WorkBuddy「设置 — 数据管理 — 发布的应用」。
- 改了代码后让我「把改动同步到线上」，我会重新发布并覆盖旧链接。
- **接了 Supabase 后，重新发布不会丢数据**（数据在 Supabase，不在沙箱里）。

### 方式三：ngrok 临时隧道

```bash
python backend/main.py
ngrok http 8000
```
免费版地址每次会变，适合临时演示。

### 方式四：Render / 自有服务器

项目已附 `Procfile`、`render.yaml`、`runtime.txt`：
- Build: `pip install -r backend/requirements.txt`
- Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- 若用 Render，把 `DATABASE_URL` 配到环境变量即可接 Supabase。

---

## 账号安全（邮箱验证）

- 注册需**邮箱验证码**（必填邮箱），忘记密码走**邮箱验证码重置**，验证码 10 分钟有效、一次性，库中只存哈希。
- 本地开发模式（未配置 SMTP）：验证码打印在服务端日志，并在接口响应 `dev_code` 字段返回。
- 上线真实邮件：在 `backend/.env`（或云端平台环境变量）配置：
  ```
  SMTP_HOST=smtp.qq.com
  SMTP_PORT=465
  SMTP_USER=发件邮箱
  SMTP_PASS=邮箱授权码（QQ/163 需在邮箱设置里开启 SMTP 生成）
  ```
  配置后重启即生效，验证码改走真实邮件。

## 安全提醒

1. **管理员密码**：首次初始化随机生成，**不要**把 `ADMIN_PASSWORD.txt` 或 `.env` 提交到 git（已在 `.gitignore` 中忽略）。
2. **不要**把 Supabase 连接串写进代码提交到公开仓库。
3. 当前密码使用固定盐 `SALT = "ers_salt_v2"` + SHA-256，属演示级别；
   正式公网运行建议改为随机盐（如 bcrypt/argon2）并加 HTTPS、限流。
4. 管理员入口虽然不在客户页暴露，但 `admin.html` 路径本身可被猜到，
   它**仍需密码**才能进入；如需进一步隐藏，可把文件改名为随机文件名。

---

## 目录结构

```
equipment-reservation-system/
├── backend/
│   ├── main.py             # FastAPI：admin/app 双库路由 + 独立管理员登录
│   ├── db.py               # SQLAlchemy 双引擎（admin 库 / app 库）
│   ├── requirements.txt    # fastapi / uvicorn / sqlalchemy / pg8000
│   ├── .env.example        # 云端数据库配置模板
│   ├── .env                # 你的真实配置（gitignore）
│   ├── ADMIN_PASSWORD.txt  # 首次生成的管理员密码（gitignore）
│   ├── admin.db / app.db   # 本地双 SQLite（gitignore）
│   ├── verify_local.py     # 全链路验证脚本
│   └── verify_restart.py   # 重启持久化验证脚本
├── frontend/
│   ├── index.html          # 客户登录/注册（无管理员信息）
│   ├── admin.html          # 管理后台 + 独立登录闸门
│   └── user.html           # 预约人门户
└── DEPLOY.md
```
