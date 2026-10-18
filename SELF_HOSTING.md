# 自有云服务器部署指南（不依赖 WorkBuddy，公网多人可访问）

如果你有自己的云服务器（阿里云/腾讯云/华为云轻量服务器、搬瓦工等），
可以把本系统部署成**正式的公网服务**：独立域名 + HTTPS + 云端数据库 + 开机自启。
比 WorkBuddy 发布/ngrok 更稳定，是"每个人都能访问"的最终形态。

---

## 架构总览

```
用户浏览器 ──HTTPS──> Nginx(443) ──> uvicorn(127.0.0.1:8000) ──> PostgreSQL
                          │                                        │
                          └── 静态前端文件(由 FastAPI 托管)          └── Supabase 云端 或 本机 Postgres
```

- **Nginx**：反向代理 + HTTPS 证书（Let's Encrypt 免费）+ 静态资源加速
- **uvicorn**：FastAPI 应用，仅监听本机，不直接暴露公网
- **systemd**：开机自启 + 崩溃自动拉起
- **数据库**：推荐 Supabase 云端（数据不随服务器迁移而丢）；也可用服务器本机 PostgreSQL

---

## 第 1 步：准备服务器

- 系统：Ubuntu 22.04 / Debian 12（其他 Linux 同理）
- 域名：一个已解析到服务器 IP 的域名（HTTPS 需要；只想 IP 访问可跳过证书步骤）
- 开放端口：22（SSH）、80、443

登录服务器并安装基础依赖：

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip nginx git
```

## 第 2 步：上传项目

本地执行（把项目整个传到服务器 `/opt/equipment-reservation-system`）：

```bash
# 用 scp 或任意方式上传；也可以先 git clone 再覆盖 frontend/backend
scp -r equipment-reservation-system root@你的服务器IP:/opt/
```

> ⚠️ 不要上传 `backend/.env`（里面是密码/连接串，服务器上单独创建）。

## 第 3 步：创建环境配置

在服务器上创建 `backend/.env`：

```bash
cd /opt/equipment-reservation-system/backend
cp .env.example .env
nano .env   # 填入下面几项
```

```env
# 云端数据库（推荐 Supabase，免费 500MB，步骤见 SUPABASE_SETUP.md）
DATABASE_URL=postgresql://postgres:你的密码@db.你的项目.supabase.co:5432/postgres
# 管理员初始密码（仅首次启动生效）
ADMIN_PASSWORD=你的强密码
# 邮箱验证（QQ/163 授权码，见 SUPABASE_SETUP.md 第 6 步）
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=发件邮箱@qq.com
SMTP_PASS=邮箱授权码
```

## 第 4 步：安装依赖并验证启动

```bash
cd /opt/equipment-reservation-system/backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python main.py &   # 先手动跑一次
curl http://127.0.0.1:8000/  # 应返回登录页 HTML
```

首次启动会自动在云端/本机建表。确认 OK 后 `Ctrl+C` 停掉，进入下一步。

## 第 5 步：systemd 开机自启

```bash
sudo nano /etc/systemd/system/equipment-reservation.service
```

```ini
[Unit]
Description=Equipment Reservation System (FastAPI)
After=network.target

[Service]
WorkingDirectory=/opt/equipment-reservation-system/backend
ExecStart=/opt/equipment-reservation-system/backend/venv/bin/python main.py
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now equipment-reservation
sudo systemctl status equipment-reservation   # active (running) 即成功
```

## 第 6 步：Nginx 反向代理 + HTTPS

### 6.1 无域名（仅 IP 访问）

```bash
sudo nano /etc/nginx/sites-available/reservation
```

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 20m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/reservation /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

访问 `http://你的服务器IP` 即可。**此时数据已存云端，换服务器/重装都不丢。**

### 6.2 有域名（推荐，带免费 HTTPS）

先把域名 A 记录解析到服务器 IP，然后：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名.com -d www.你的域名.com
```

Certbot 自动签发 Let's Encrypt 证书并改写 Nginx 配置，之后：
- `https://你的域名.com` 直接可用，http 自动跳转 https
- 证书 90 天自动续期（certbot 定时任务已自动装好）

---

## 第 7 步：上线验证清单

| 检查项 | 方法 | 预期 |
|--------|------|------|
| 服务自启 | `sudo reboot` 后访问 | 服务自动恢复 |
| 崩溃拉起 | `sudo systemctl kill equipment-reservation` | systemd 3 秒后自动重启 |
| 注册邮箱验证 | 注册新账号 | 收到真实验证码邮件（SMTP 已配置时） |
| 数据上云 | Supabase Table Editor | 新注册用户出现在 `app.users` |
| HTTPS | 浏览器访问 https 域名 | 锁头图标，无告警 |
| 日志排查 | `sudo journalctl -u equipment-reservation -f` | 实时日志 |

---

## 常见问题

**Q：不想用 Supabase，用服务器本机 PostgreSQL？**
```bash
sudo apt install -y postgresql
sudo -u postgres createdb equipment
sudo -u postgres psql -c "CREATE USER ers WITH PASSWORD '强密码';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE equipment TO ers;"
```
`.env` 写 `DATABASE_URL=postgresql://ers:强密码@127.0.0.1:5432/equipment` 即可
（程序会自动创建 admin/app 两个 schema 并建表）。

**Q：服务器 IP 被防火墙挡了？**
阿里云/腾讯云安全组放行 80、443 端口；Ubuntu 自带的 ufw：
```bash
sudo ufw allow 80,443/tcp && sudo ufw enable
```

**Q：如何更新代码？**
```bash
cd /opt/equipment-reservation-system
# 覆盖新代码（保留 backend/.env）
sudo systemctl restart equipment-reservation
```

**Q：数据备份？**
Supabase 免费档自带自动备份；本机 PostgreSQL 可加 cron 定时 `pg_dump`。

---

## 和 WorkBuddy 发布的区别

| 维度 | 自有服务器 | WorkBuddy 发布 |
|------|-----------|----------------|
| 成本 | 约 ¥30-60/月（轻量服务器） | 免费 |
| 稳定性 | 高（systemd + Nginx） | 中（沙箱回收风险） |
| 数据 | 云端数据库（不丢） | 需自行接 Supabase 才不丢 |
| HTTPS | 免费证书自动配置 | 按平台规则 |
| 域名 | 自己的域名/IP | 分享链接 |
| 适合 | 正式长期使用 | 快速演示 |

**结论**：正式对外用推荐自有服务器 + Supabase；先快速体验用局域网/WorkBuddy 发布。
