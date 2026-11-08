"""Мектеп кодтары (лицензия), әкімшілер және IP тіркеу.

- Код жоқ немесе мерзімі өткен мұғалімнің коды — «000000»: курстар ашылмайды, сынып құрылмайды.
- Кодты тек әкімші жасайды (aidar / aidarpavl@gmail.com). Әр код бір рет қана қолданылады.
- Код оқу жылының соңына дейін (31 тамыз) жарамды, жыл сайын жаңа код беріледі.
"""
import secrets
from datetime import date, datetime, timedelta

import auth
import db

NO_CODE = "000000"
ADMIN_LOGINS = {"aidar", "aidarpavl@gmail.com"}
MAX_ATTEMPTS = 5          # қате код енгізу шегі
ATTEMPT_WINDOW_MIN = 15   # минут


# ---------------- әкімшілер ----------------

def _extra_admins():
    try:
        import streamlit as st
        extra = st.secrets.get("ADMIN_EMAILS", "") or ""
    except Exception:
        extra = ""
    return {e.strip().lower() for e in str(extra).split(",") if e.strip()}


def admin_logins():
    return ADMIN_LOGINS | _extra_admins()


def is_admin(user):
    return bool(user) and (user.get("role") == "admin" or user["email"].lower() in admin_logins())


def is_reserved(email):
    """Әкімші логиндерімен ешкім өзі тіркеле алмайды."""
    return email.strip().lower() in admin_logins()


def ensure_admins(password):
    """secrets.toml-дағы ADMIN_PASSWORD бойынша әкімші аккаунттарын жасау (бар болса — тиіспейді)."""
    if not password:
        return
    for login in ADMIN_LOGINS:
        u = auth.get_user_by_email(login)
        if not u:
            uid = auth.create_user(login, "Aidar" if login == "aidar" else "Aidar (admin)", password, "admin")
            db.execute("UPDATE users SET profile_done=1 WHERE id=?", (uid,))
        elif u["role"] != "admin":
            db.execute("UPDATE users SET role='admin' WHERE id=?", (u["id"],))


# ---------------- оқу жылы ----------------

def academic_years(today=None):
    """[(«2026–2027», «2027-08-31»), ...] — ағымдағы және келесі оқу жылы."""
    today = today or date.today()
    start = today.year if today.month >= 9 else today.year - 1
    return [(f"{y}–{y + 1}", f"{y + 1}-08-31") for y in (start, start + 1)]


def today_str():
    return date.today().isoformat()


# ---------------- кодтар ----------------

def _new_code():
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if code != NO_CODE and not db.query_one("SELECT id FROM school_codes WHERE code=?", (code,)):
            return code


def generate_codes(school_name, academic_year, valid_until, count, admin_id):
    codes = []
    for _ in range(max(1, int(count))):
        code = _new_code()
        db.insert("""INSERT INTO school_codes (code, school_name, academic_year, valid_until, status, created_by, created_at)
                     VALUES (?,?,?,?, 'new', ?, ?)""",
                  (code, school_name.strip(), academic_year, valid_until, admin_id, db.now()))
        codes.append(code)
    return codes


def list_codes():
    rows = db.query("""SELECT c.*, u.name AS teacher_name, u.email AS teacher_email
                       FROM school_codes c LEFT JOIN users u ON u.id=c.used_by ORDER BY c.id DESC""")
    for r in rows:
        r["effective_status"] = effective_status(r)
        r["ips"] = db.query("SELECT ip, last_seen, visits FROM ip_log WHERE code_id=? ORDER BY last_seen DESC",
                            (r["id"],))
    return rows


def effective_status(row):
    if row["status"] == "revoked":
        return "revoked"
    if row["valid_until"] < today_str():
        return "expired"
    return row["status"]  # new | active


def revoke(code_id):
    db.execute("UPDATE school_codes SET status='revoked' WHERE id=?", (code_id,))


def delete_code(code_id):
    db.execute("UPDATE users SET school_code_id=NULL WHERE school_code_id=?", (code_id,))
    db.execute("DELETE FROM school_codes WHERE id=?", (code_id,))


def _attempts_left(user_id):
    since = (datetime.now() - timedelta(minutes=ATTEMPT_WINDOW_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    n = db.query_one("SELECT COUNT(*) AS n FROM code_attempts WHERE user_id=? AND at>=?", (user_id, since))["n"]
    return MAX_ATTEMPTS - int(n)


def activate(user, code):
    """Мұғалім кодты енгізеді. Қайтарады: (ok, kz_хабар, ru_хабар)."""
    code = (code or "").strip()
    if _attempts_left(user["id"]) <= 0:
        return False, (f"Тым көп қате әрекет. {ATTEMPT_WINDOW_MIN} минуттан кейін қайталаңыз.",
                       f"Слишком много неверных попыток. Повторите через {ATTEMPT_WINDOW_MIN} минут.")
    row = db.query_one("SELECT * FROM school_codes WHERE code=?", (code,)) if code and code != NO_CODE else None
    problem = None
    if not row:
        problem = ("Код табылмады.", "Код не найден.")
    elif row["status"] == "revoked":
        problem = ("Бұл код бұғатталған.", "Этот код заблокирован.")
    elif row["status"] == "active" or row["used_by"]:
        problem = ("Бұл код бұрын қолданылған. Әр код тек бір рет беріледі.",
                   "Этот код уже использован. Каждый код выдаётся только один раз.")
    elif row["valid_until"] < today_str():
        problem = ("Кодтың мерзімі өткен.", "Срок действия кода истёк.")
    if problem:
        db.insert("INSERT INTO code_attempts (user_id, at) VALUES (?,?)", (user["id"], db.now()))
        return False, problem
    db.execute("UPDATE school_codes SET status='active', used_by=?, used_at=? WHERE id=?", (user["id"], db.now(), row["id"]))
    db.execute("UPDATE users SET school_code_id=? WHERE id=?", (row["id"], user["id"]))
    return True, (f"Мектеп қосылды: {row['school_name']}", f"Школа подключена: {row['school_name']}")


# ---------------- лицензияны тексеру ----------------

def teacher_license(user_id):
    """Мұғалімнің жарамды коды (жол) немесе None."""
    row = db.query_one("""SELECT c.* FROM users u JOIN school_codes c ON c.id=u.school_code_id
                          WHERE u.id=?""", (user_id,))
    if row and effective_status(row) == "active":
        return row
    return None


def user_license(user):
    """Пайдаланушының мектебі (код жолы) немесе None. Оқушы үшін — сынып мұғалімінің коды."""
    if not user:
        return None
    if user["role"] in ("teacher", "admin"):
        return teacher_license(user["id"])
    for r in db.query("""SELECT c.teacher_id FROM enrollments e JOIN classes c ON c.id=e.class_id
                         WHERE e.student_id=?""", (user["id"],)):
        lic = teacher_license(r["teacher_id"])
        if lic:
            return lic
    return None


def is_unlocked(user):
    return is_admin(user) or user_license(user) is not None


def class_unlocked(class_row):
    return teacher_license(class_row["teacher_id"]) is not None or \
        is_admin(auth.get_user(class_row["teacher_id"]))


def code_of(user):
    lic = user_license(user)
    return lic["code"] if lic else NO_CODE


# ---------------- IP тіркеу ----------------

def log_ip(user, ip):
    lic = user_license(user)
    if not lic or not ip:
        return
    ex = db.query_one("SELECT id FROM ip_log WHERE code_id=? AND ip=?", (lic["id"], ip))
    if ex:
        db.execute("UPDATE ip_log SET last_seen=?, visits=visits+1, user_id=? WHERE id=?", (db.now(), user["id"], ex["id"]))
    else:
        db.insert("INSERT INTO ip_log (code_id, user_id, ip, first_seen, last_seen, visits) VALUES (?,?,?,?,?,1)",
                  (lic["id"], user["id"], ip, db.now(), db.now()))
