# Supabase 建库教程（5 步，约 5 分钟）

接了 Supabase 之后，线上分享链接的数据会存在云端 Postgres，**回收 / 重新发布都不再丢失**，
用户注册一次就能一直用，管理员审批的也是真实预约人的预约。

---

## 第 1 步：注册 / 登录

打开 <https://supabase.com> → 右上角 **Start your project**，用 GitHub 或邮箱注册（免费）。

## 第 2 步：新建项目

1. 进入控制台后点 **New project**。
2. 填写：

   | 字段 | 建议 |
   |------|------|
   | Organization | 默认自带的即可 |
   | Name | 例如 `equipment-reservation` |
   | **Database Password** | **自己设一个强密码，务必记下来**（它就是连接串里的密码，建好后无法直接查看，只能重置） |
   | Region | 选 **Southeast Asia (Singapore)** 或 **Tokyo**（离国内延迟低） |

3. 点 **Create new project**，等待约 1–2 分钟完成初始化（页面会转圈）。

## 第 3 步：复制连接串（关键）

1. 左侧栏点齿轮 **Project Settings** → **Database**。
2. 往下找到 **Connection string** 区块，切换到 **URI** 标签页。
3. 你会看到两种，**请复制 Direct connection（端口 5432）** 的那一条：

   ```
   postgresql://postgres:<你的密码>@db.<项目ID>.supabase.co:5432/postgres
   ```

   > 为什么不用 6543（Transaction pooler）：本程序首次启动要执行 `CREATE SCHEMA` 建表和 DDL，
   > 事务池模式对部分会话状态支持不完整，用直连 5432 最稳。

4. 把 `<你的密码>` 替换成第 2 步设置的真实数据库密码。

### ⚠️ 密码含特殊字符要 URL 编码

如果密码里有 `@ # $ % & + / :` 等符号，必须转义后再拼进连接串，否则连不上：

| 原字符 | 替换为 |
|--------|--------|
| `@` | `%40` |
| `#` | `%23` |
| `$` | `%24` |
| `%` | `%25` |
| `&` | `%26` |
| `+` | `%2B` |
| `/` | `%2F` |
| `:` | `%3A` |

> 建议：干脆设一个**只含字母和数字**的密码，最省事，不用转义。

## 第 4 步：写入项目配置

把 `backend/.env.example` 复制成 `backend/.env`，内容填成这样：

```env
DATABASE_URL=postgresql://postgres:你的密码@db.项目ID.supabase.co:5432/postgres
ADMIN_PASSWORD=你想设的管理员强密码
```

- `DATABASE_URL`：第 3 步拿到的连接串
- `ADMIN_PASSWORD`：管理员初始密码（**首次启动前**设置才生效；不填则随机生成并写入 `ADMIN_PASSWORD.txt`）

> `.env` 和 `ADMIN_PASSWORD.txt` 已在 `.gitignore` 中，**不会**被提交到 git。

## 第 5 步：本地验证一下

```bash
python backend/main.py
python backend/verify_local.py
```

- 启动日志若出现建库过程即为正常；程序会自动在云端创建 `admin` 和 `app` 两个 schema 及全部表。
- `verify_local.py` 全部 PASS，说明双库 + 审批链路在 Postgres 上同样正常。
- 想确认数据真的进了云端：打开 Supabase 控制台左侧 **Table Editor**，
  能看到 `admin` schema 下的 `admin_users / equipment / settings`、
  `app` schema 下的 `users / sessions / reservations`。

---

## 第 6 步（可选）：邮箱验证上线（SMTP 配置）

账号安全功能（注册验证码 / 忘记密码）在未配置 SMTP 时处于**开发模式**（验证码不真发信，打印在日志并随接口返回）。要上线真实邮件：

1. 任选一个邮箱开启 SMTP 服务：
   - **QQ 邮箱**：网页版设置 → 账户 → 开启「POP3/SMTP 服务」→ 按提示发短信生成**授权码**（16 位，记下来）。
   - **163 邮箱**：设置 → POP3/SMTP/IMAP → 开启 SMTP → 新增**授权码**。
2. 在 `backend/.env` 追加（`SMTP_PASS` 填授权码，**不是**邮箱登录密码）：
   ```env
   SMTP_HOST=smtp.qq.com
   SMTP_PORT=465
   SMTP_USER=你的QQ号@qq.com
   SMTP_PASS=你的16位授权码
   ```
3. 重启服务。之后注册/忘记密码的验证码走真实邮件，接口不再返回 `dev_code`。
4. 云端部署（Render/WorkBuddy 发布）时，把上述 4 项加到对应平台的环境变量即可，无需改代码。

> 验证码 10 分钟有效、一次性，数据库只存 SHA-256 哈希；邮箱唯一，已被注册的邮箱不可重复注册。

---

## 然后：把连接串发给我

把下面这行发给我（**密码可以打码，你本地已经在 `.env` 里填好了，我发布时会用你本地那份**）：

```
postgresql://postgres:****@db.xxxx.supabase.co:5432/postgres
```

并告诉我「发布到线上」，我就会：

1. 确认 `.env` 就位；
2. 重新发布到你的分享链接（用同一个 appId，链接不变）；
3. 线上跑一遍注册 → 提交预约 → 管理员审批 → 设备登录/签退；
4. 再触发一次重新发布，确认**数据依然在**（这就是持久化的最终验证）。

---

## 常见问题

**Q：免费档够用吗？**
够。免费项目有 500MB 数据库空间，本系统几千条预约绰绰有余。
注意：免费项目**连续 7 天无访问会被暂停**，到控制台点一下 Restore 即可恢复。

**Q：发布平台能连上 Supabase 吗？**
能。发布沙箱可以访问公网，且平台明确允许「指向公网托管数据库（如 Supabase）的连接串」；
被拒绝的是指向 `localhost` / compose 服务名的连接串。本项目用的是 `pg8000` 纯 Python 驱动，
不依赖系统库，也不会触发平台的额外数据库服务限制。

**Q：提示连不上 / 超时？**
- 检查密码是否 URL 编码正确；
- 确认用的是 5432 直连而不是 6543；
- 在 Supabase 控制台确认项目状态是 Active（不是 Paused）。

**Q：我想换回本地 SQLite？**
把 `backend/.env` 里的 `DATABASE_URL` 删掉或整行注释掉即可，程序会自动回退到本地
`admin.db` / `app.db`。
