"""邮件发送模块（账号安全：注册邮箱验证码 / 忘记密码重置码）。

配置（环境变量，或 backend/.env）：
  SMTP_HOST      smtp 服务器，如 smtp.qq.com / smtp.163.com
  SMTP_PORT      smtp 端口，如 465(SSL) / 587(STARTTLS)
  SMTP_USER      发件邮箱账号
  SMTP_PASS      发件邮箱授权码（QQ/163 需在邮箱设置里开通 SMTP 并生成授权码）
  MAIL_FROM      发件人显示，默认等于 SMTP_USER

未配置 SMTP 时自动进入「开发模式」：验证码不真正发信，而是打印到服务端日志，
并在接口响应里返回 dev_code 字段，便于本地联调；配置 SMTP 后即走真实邮件。
"""
import os
import smtplib
import secrets
from email.mime.text import MIMEText
from email.header import Header


def _load_dotenv() -> None:
    p = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(p):
        return
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


_load_dotenv()

SMTP_HOST = (os.environ.get("SMTP_HOST") or "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT") or "465")
SMTP_USER = (os.environ.get("SMTP_USER") or "").strip()
SMTP_PASS = (os.environ.get("SMTP_PASS") or "").strip()
MAIL_FROM = (os.environ.get("MAIL_FROM") or SMTP_USER).strip()

# 开发模式：未配置 SMTP 时，验证码直接暴露在接口响应与日志中，仅用于本地联调
DEV_MODE = not (SMTP_HOST and SMTP_USER and SMTP_PASS)


def smtp_configured() -> bool:
    return not DEV_MODE


def gen_code() -> str:
    """6 位数字验证码。"""
    return f"{secrets.randbelow(1000000):06d}"


def send_code(email: str, code: str, purpose: str) -> bool:
    """发送验证码邮件；开发模式返回 False 表示未真正发信（由调用方读日志/响应）。"""
    title = {
        "register": "注册验证码",
        "reset": "重置密码验证码",
    }.get(purpose, "验证码")
    body = (
        f"您好：\n\n"
        f"您正在进行【{title}】操作，验证码为：{code}\n"
        f"验证码 10 分钟内有效，请勿泄露给他人。\n"
        f"如非本人操作，请忽略本邮件。\n\n"
        f"—— 实验设备预约系统"
    )
    if DEV_MODE:
        print(f"[mailer-dev] 向 {email} 发送 {purpose} 验证码: {code}（未配置 SMTP，仅开发模式）")
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(f"【实验设备预约系统】{title}", "utf-8")
        msg["From"] = MAIL_FROM
        msg["To"] = email
        if SMTP_PORT == 465:
            srv = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        else:
            srv = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            srv.starttls()
        srv.login(SMTP_USER, SMTP_PASS)
        srv.sendmail(MAIL_FROM, [email], msg.as_string())
        srv.quit()
        print(f"[mailer] 已向 {email} 发送 {purpose} 验证码")
        return True
    except Exception as e:
        print(f"[mailer] 发送失败: {e}")
        return False
