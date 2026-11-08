"""Email жіберу (SMTP). Параметрлер .streamlit/secrets.toml ішіндегі [smtp] бөлімінен алынады.

[smtp]
host = "smtp.gmail.com"
port = 587
user = "mektep@gmail.com"
password = "gmail app password (16 таңба)"
sender_name = "PISA Жас дарын"
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _cfg():
    try:
        import streamlit as st
        cfg = dict(st.secrets.get("smtp", {}))
        return cfg if cfg.get("host") and cfg.get("user") else None
    except Exception:
        return None


def is_configured() -> bool:
    return _cfg() is not None


def send_email(to: str, subject: str, html: str):
    """(True, '') немесе (False, қате_мәтіні) қайтарады."""
    cfg = _cfg()
    if not cfg:
        return False, "SMTP бапталмаған"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f'{cfg.get("sender_name", "PISA Жас дарын")} <{cfg["user"]}>'
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        port = int(cfg.get("port", 587))
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(cfg["host"], port, context=ctx, timeout=20) as s:
                s.login(cfg["user"], cfg["password"])
                s.sendmail(cfg["user"], [to], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], port, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(cfg["user"], cfg["password"])
                s.sendmail(cfg["user"], [to], msg.as_string())
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def credentials_email(name, email, password, class_name, app_url, class_link):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px">
      <h2 style="color:#1f7a4d">PISA Жас дарын</h2>
      <p>Сәлеметсіз бе, <b>{name}</b>! Сіз <b>«{class_name}»</b> сыныбына тіркелдіңіз.<br>
         <span style="color:#555">Здравствуйте, <b>{name}</b>! Вы зарегистрированы в классе <b>«{class_name}»</b>.</span></p>
      <table style="border-collapse:collapse">
        <tr><td style="padding:4px 12px 4px 0">Логин:</td><td><b>{email}</b></td></tr>
        <tr><td style="padding:4px 12px 4px 0">Құпиясөз / Пароль:</td><td><b style="font-size:18px">{password}</b></td></tr>
      </table>
      <p><a href="{app_url}" style="background:#1f7a4d;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none">
         Платформаға кіру / Войти на платформу</a></p>
      <p style="color:#666;font-size:13px">Сынып сілтемесі / Ссылка класса: <a href="{class_link}">{class_link}</a><br>
      Құпиясөзді «Профиль» бөлімінде өзгерте аласыз. / Пароль можно изменить в разделе «Профиль».</p>
    </div>"""


def reset_email(name, email, password, app_url):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px">
      <h2 style="color:#1f7a4d">PISA Жас дарын — жаңа құпиясөз / новый пароль</h2>
      <p>{name}</p>
      <p>Логин: <b>{email}</b><br>Құпиясөз / Пароль: <b style="font-size:18px">{password}</b></p>
      <p><a href="{app_url}">Платформаға кіру / Войти на платформу</a></p>
    </div>"""
