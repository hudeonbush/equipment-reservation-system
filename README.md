# 实验设备预约系统（Equipment Reservation System）

一个面向实验室/教研单位的**设备预约管理系统**，包含**管理员后台**与**预约人门户**双入口。
对标参考项目（Vue3 + SpringBoot 培训机构管理系统）的功能结构，但采用更轻量、零额外数据库依赖的技术栈，**一条命令即可在本机运行**。

---

## 功能一览

### 双入口
- **管理员后台**（`/admin.html`）：设备增删改查、预约审批（通过/驳回/标记完成/取消）、**账号管理**、数据看板。
- **预约人门户**（`/user.html`）：模糊查询浏览设备、**设备收藏**、提交预约、查看/取消自己的预约。
- 未登录自动跳转登录页（`/index.html`），支持自助注册。

### 三角色账号管理（v2 新增）
- **校内用户**：注册时填写学号/工号、院系、导师，注册即生效，可直接预约。
- **校外用户**：注册时填写单位名称、单位类型（高校/科研院所/企业）、邮箱，注册后进入**待审核**状态，需管理员审核激活后才能预约（借鉴清华/武大大型仪器共享平台的校外用户激活机制）。
- **管理员**：独立登录入口（`/api/admin/login`）与独立账号库，物理隔离于预约人前台。
- **账号状态机**：`active`（正常）/ `pending`（待审核）/ `disabled`（禁用）/ `rejected`（驳回）；未激活、被禁用、被驳回的账号无法登录与预约。

### 管理员账号管理（借鉴佰能预约助手「用户管理」）
- 用户列表：按类型（校内/校外）/状态/关键词（用户名/姓名/单位/院系/学号）筛选。
- 审核激活/驳回校外注册、启用/禁用账号、重置用户密码。
- 看板「待审核用户」卡片 + 待审核预约卡片，一键掌握待办。

### 设备收藏（借鉴佰能预约助手「设备收藏」红心）
- 设备列表点 ♡ 收藏常用设备，进「我的收藏」页快速预约。

### 邮箱验证与账号安全（v3 新增）
- **注册必填邮箱验证码**：注册时输入邮箱 → 点「发送验证码」→ 邮件收到 6 位验证码 → 填码注册，验证码 10 分钟有效、一次性。
- **忘记密码**：登录页「忘记密码？」→ 填注册邮箱 → 收重置验证码 → 设新密码。
- **开发模式**：未配置 SMTP 时验证码不真发邮件，而是打印到服务端日志并在接口响应 `dev_code` 字段返回（仅本地联调用）；配置 SMTP 后即走真实邮件。
- 验证码在数据库中只存 SHA-256 哈希，邮箱已验证状态记录在 `users.email_verified`。

### 云端部署与多人在线（v3 新增）
- **账号数据存云端**：内置 Supabase（免费 PostgreSQL）支持，配置 `backend/.env` 的 `DATABASE_URL` 后，所有注册账号、预约、收藏均持久化到云端 Postgres，重启/重新发布不丢数据（详见 `SUPABASE_SETUP.md`）。
- **多人可访问**：局域网共享 / WorkBuddy 发布 / ngrok / Render / **自有云服务器**（详见 `DEPLOY.md`、`SELF_HOSTING.md`——自有服务器方案含 systemd 开机自启 + Nginx 反向代理 + 免费 HTTPS 证书，正式对外部署首选）。
- **邮箱验证上线**：在 `backend/.env` 配置 SMTP_* 后即启用真实邮件（QQ/163 邮箱授权码）。

### 设备全生命周期管理（v4 新增，借鉴 Spring Boot 毕设案例）
- **设备分类**：设备按类别（显微镜/离心机/光谱仪…）分组管理，用户端可按分类筛选。
- **设备报修**：用户发现故障可报修 → 设备自动进入「维护中」暂停预约 → 管理员「开始处理 / 标记已修复」→ 修复后设备自动恢复可预约；管理后台「设备报修」页签带待处理角标。
- **通知公告**：管理员发布/停用公告，用户门户顶部展示公告条。
- **登录失败锁定**（账号安全）：连续 5 次密码错误锁定 15 分钟，管理员重置密码可解锁。

### 核心能力
- **预约时间记录**：每条预约记录开始/结束时间、用途、提交人与审批人。
- **模糊查询**：设备可按 名称/型号/位置/负责人 模糊搜索；预约可按 预约人/设备/用途 模糊搜索。
- **预约冲突校验**：同一设备时间区间重叠的预约（待审/已通过）会被自动拦截，返回冲突详情。
- **审批流程**：提交 → 待审核 → 通过/驳回 → 使用完成，状态全程可追溯。
- **设备登录（签到/签退）**：预约人通过审核后，到设备前点「登录设备」开始使用（状态变**使用中**），用完点「结束使用」签退（变**已完成**）；使用中同样会阻止他人重复预约。管理员可代操作。
- **管理员统计看板**：设备总数、预约账号、预约总量、待审核数、**当前使用中的设备**、设备使用 TOP5、预约/设备状态分布、近期预约（含用户类型标签）。

---

## 技术栈
- 后端：**FastAPI** + **SQLite**（标准库 `sqlite3`，零配置数据库；可选 PostgreSQL/Supabase）
- 前端：原生 HTML/CSS/JS（**无 CDN 依赖，离线可运行**）
- 运行：**uvicorn**（已装入项目内 `venv`）

---

## 默认账号
| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | `admin` | 首次启动自动生成，见 `backend/ADMIN_PASSWORD.txt` |

> 预约人可在登录页自助注册（校内即时生效；校外需管理员审核）。
> 管理员密码如需固定，可在启动前设置环境变量 `ADMIN_PASSWORD=xxx`（仅首次建库生效）。

---

## 快速启动

### Windows
双击项目根目录下的 **`start.bat`** 即可；或手动：
```bat
cd backend
venv\Scripts\python.exe main.py
```
启动后浏览器打开：<http://127.0.0.1:8000>

### Linux / macOS
```bash
cd backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python main.py
```

首次启动会自动创建数据库并写入示例数据（管理员、6 台设备）；若检测到旧版数据库，会自动**迁移补齐新字段**（无需手动处理）。

---

## 目录结构
```
equipment-reservation-system/
├── backend/
│   ├── main.py              # FastAPI 应用：所有 /api 接口 + 托管前端
│   ├── db.py                # 建表、迁移、种子数据、连接
│   ├── requirements.txt
│   ├── smoketest.py         # 端到端冒烟测试（基础功能）
│   ├── smoketest_v2.py      # 端到端冒烟测试（三角色账号/收藏/审核）
│   ├── cleanup_test_data.py # 清理冒烟测试产生的测试数据
│   └── venv/                # 虚拟环境（含 fastapi/uvicorn）
├── frontend/
│   ├── index.html           # 登录 / 注册（校内·校外）
│   ├── admin.html           # 管理员后台（含账号管理）
│   ├── user.html            # 预约人门户（含我的收藏）
│   ├── css/style.css
│   └── js/{common,admin,user}.js
├── docs/ui-preview/         # 界面截图预览
├── start.bat / start.sh     # 启动脚本
└── README.md
```

---

## 主要 API
| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/api/send-code` | 发送邮箱验证码（purpose=register/reset；未配 SMTP 返回 dev_code） | 公开 |
| POST | `/api/register` | 注册预约人（必填 email + email_code，校内 active / 校外 pending） | 公开 |
| POST | `/api/login` | 预约人登录（校验账号状态） | 公开 |
| POST | `/api/admin/login` | 管理员登录（独立账号库） | 公开 |
| POST | `/api/forgot-password` | 忘记密码：向注册邮箱发重置验证码 | 公开 |
| POST | `/api/reset-password` | 重置密码（邮箱验证码 + 新密码） | 公开 |
| GET  | `/api/equipment-categories` | 设备分类列表 | 登录 |
| GET  | `/api/announcements` | 公告列表（用户只看展示中，管理员看全部） | 登录 |
| POST | `/api/announcements` | 发布公告 | 管理员 |
| PUT  | `/api/announcements/{id}/toggle` | 停用/启用公告 | 管理员 |
| DELETE | `/api/announcements/{id}` | 删除公告 | 管理员 |
| POST | `/api/repairs` | 提交设备报修（自动置设备维护中） | 登录 |
| GET  | `/api/repairs` | 报修列表（用户看自己的，管理员看全部可筛状态） | 登录 |
| PUT  | `/api/repairs/{id}/handle` | 处理报修（处理中/已修复，修复后设备恢复） | 管理员 |
| GET  | `/api/me` | 当前用户 | 登录 |
| GET  | `/api/users` | 用户列表（类型/状态/关键词筛选） | 管理员 |
| POST | `/api/users/{id}/approve` | 审核激活校外用户 | 管理员 |
| POST | `/api/users/{id}/reject` | 驳回注册申请 | 管理员 |
| POST | `/api/users/{id}/toggle` | 启用/禁用账号 | 管理员 |
| POST | `/api/users/{id}/reset-password` | 重置用户密码 | 管理员 |
| GET  | `/api/favorites` | 我的收藏设备 id | 登录 |
| POST | `/api/favorites/{eid}` | 收藏设备 | 登录 |
| DELETE | `/api/favorites/{eid}` | 取消收藏 | 登录 |
| GET  | `/api/equipment?kw=&status=` | 设备列表（模糊查询） | 登录 |
| POST | `/api/equipment` | 新增设备 | 管理员 |
| PUT  | `/api/equipment/{id}` | 修改设备 | 管理员 |
| DELETE | `/api/equipment/{id}` | 删除设备 | 管理员 |
| POST | `/api/reservations` | 提交预约（含冲突校验） | 登录 |
| GET  | `/api/reservations/mine` | 我的预约 | 登录 |
| GET  | `/api/reservations?kw=&status=&equipment_id=` | 全部预约（含用户类型） | 管理员 |
| POST | `/api/reservations/{id}/approve` | 通过 | 管理员 |
| POST | `/api/reservations/{id}/reject` | 驳回 | 管理员 |
| POST | `/api/reservations/{id}/cancel` | 取消 | 本人/管理员 |
| POST | `/api/reservations/{id}/complete` | 标记完成 | 管理员 |
| POST | `/api/reservations/{id}/checkin` | 登录设备（开始使用） | 本人/管理员 |
| POST | `/api/reservations/{id}/checkout` | 结束使用（签退） | 本人/管理员 |
| GET  | `/api/stats` | 统计看板数据（含待审核用户/使用中设备） | 管理员 |

---

## 数据库表
- `users`：用户名、密码（加盐 SHA256）、姓名、手机、邮箱、**邮箱已验证标记（email_verified）**、**登录失败次数/锁定时间（failed_attempts/locked_until）**、**用户类型（internal/external）**、**账号状态（active/pending/disabled/rejected）**、单位名称/类型、院系、学号、导师
- `favorites`：用户设备收藏（user_id + equipment_id）
- `verify_codes`：邮箱验证码（email + purpose + 哈希 + 过期时间，10 分钟一次性）
- `repairs`：设备报修（报修人 + 设备 + 故障描述 + 状态 + 处理人/说明）
- `announcements`：通知公告（标题 + 内容 + 展示状态）
- `sessions`：登录令牌与会话过期时间
- `equipment`：名称、**分类**、型号、位置、状态（available/maintenance/disabled）、负责人、描述
- `reservation`：预约人、设备、起止时间、用途、状态（pending/approved/in_use/rejected/cancelled/used）、审批人/理由/时间、登录/签退时间

---

## 设计参考
本系统 v2/v3/v4 的账号与交互设计借鉴了：
- **佰能预约助手（shareE 大型仪器共享平台）**：设备搜索与收藏、预约记录/使用记录/申请记录分离、管理员「用户管理/设备申请审核/当前使用设备」、注册审核提醒。
- **高校大型仪器共享平台**（清华/北大/武大/浙大）：校内用户注册即用、校外用户注册后管理员审核激活方可预约。
- **NIST 开源项目 NEMO**（github.com/usnistgov/NEMO）：多级用户角色、访问请求审批机制、设备资质考核、状态看板、日历排期。
- **Spring Boot 毕设案例**（实验室管理系统、仪器共享系统、企业设备管理系统，见 B 站/CSDN/Gitee 常见毕设）：设备类别管理、设备报修/报障全流程（报修→处理→修复→恢复）、通知公告、登录失败锁定防爆破、自购服务器部署（systemd + Nginx + HTTPS）。

---

## 说明与可扩展点
- 密码采用固定盐 SHA256 演示方案，生产环境请替换为 `bcrypt`/`argon2` 并启用随机盐。
- 前端零外部依赖，可直接替换为 Vue/React 等框架而不动后端。
- 如需对接参考项目的 MySQL/PostgreSQL，只需把 `db.py` 的 SQLite 连接替换为对应驱动，SQL 基本兼容（已内置 Supabase Postgres 双 schema 支持）。
- 冒烟测试：先启动服务，再运行 `venv\Scripts\python.exe smoketest_v2.py`（测试后可用 `cleanup_test_data.py` 清理测试数据）。
