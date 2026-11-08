"""PISA Жас дарын — оқу платформасы (Streamlit). Екі тілде: қазақша / орысша.

Іске қосу:  streamlit run app.py
"""
import io

import pandas as pd
import streamlit as st

import auth
import db
import editor
import i18n
import mailer
import player
import report
import repo
import schools
import seed
import stepik_import
from i18n import T, title

st.set_page_config(page_title="PISA Жас дарын", page_icon="📘", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
.big-code {font-size: 2rem; font-weight: 700; letter-spacing: .3rem; color: #1f7a4d;}
.stMarkdown table {border-collapse: collapse;}
.stMarkdown td, .stMarkdown th {border: 1px solid #ccc; padding: 4px 8px; vertical-align: top;}
.stMarkdown img {max-width: 100%; height: auto;}
.school-banner {background: linear-gradient(90deg,#1f7a4d,#2f9e68); color:#fff; padding:10px 16px;
  border-radius:10px; margin-bottom:12px; font-size:1.05rem;}
.school-banner.locked {background: linear-gradient(90deg,#8a8a8a,#a5a5a5);}
.school-banner b {font-size:1.2rem;}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def _init():
    db.init_db()
    seed.seed_if_empty()
    try:
        schools.ensure_admins(st.secrets.get("ADMIN_PASSWORD"))
    except Exception:
        pass
    return True


_init()


def secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


APP_URL = (secret("APP_URL", "http://localhost:8501") or "").rstrip("/")


def class_link(code):
    return f"{APP_URL}/?join={code}"


def course_name(row):
    """course_title / course_title_ru бағандарынан ағымдағы тілдегі атау."""
    return title(row, "course_title")


def current_user():
    uid = st.session_state.get("uid")
    return auth.get_user(uid) if uid else None


def do_login(user):
    st.session_state["uid"] = user["id"]
    if user.get("pref_lang") in i18n.LANGS:
        st.session_state["lang"] = user["pref_lang"]


def is_teacher(user):
    return user["role"] in ("teacher", "admin")


def client_ip():
    """Пайдаланушының IP-адресі (прокси артында X-Forwarded-For)."""
    try:
        headers = st.context.headers
        for h in ("X-Forwarded-For", "X-Real-Ip", "X-Real-IP"):
            v = headers.get(h)
            if v:
                return v.split(",")[0].strip()
    except Exception:
        pass
    try:
        return st.context.ip_address
    except Exception:
        return None


def school_banner(user):
    lic = schools.user_license(user)
    if lic:
        st.markdown(f"<div class='school-banner'>🏫 <b>{lic['school_name']}</b> · "
                    f"{T('оқу жылы', 'учебный год')} {lic['academic_year'] or ''} · "
                    f"{T('код жарамды', 'код действует до')} {lic['valid_until']}</div>", unsafe_allow_html=True)
    elif schools.is_admin(user):
        st.markdown(f"<div class='school-banner'>🔐 {T('Әкімші', 'Администратор')}</div>", unsafe_allow_html=True)
    else:
        msg = T("Мектеп қосылмаған · код", "Школа не подключена · код") + f" <b>{schools.NO_CODE}</b> · "
        msg += (T("«🏫 Мектеп» бөлімінде кодты енгізіңіз", "введите код в разделе «🏫 Школа»") if is_teacher(user)
                else T("курстар мұғалім мектепті қосқаннан кейін ашылады", "курсы откроются после подключения школы учителем"))
        st.markdown(f"<div class='school-banner locked'>🔒 {msg}</div>", unsafe_allow_html=True)


def locked_notice(user):
    st.warning(T(f"🔒 Мектеп коды {schools.NO_CODE}. Курстар ашылмайды, сынып құрылмайды. Әкімшіден сатып алған "
                 "кодты «🏫 Мектеп» бөлімінде енгізіңіз.",
                 f"🔒 Код школы {schools.NO_CODE}. Курсы не открываются, классы не создаются. Введите купленный у "
                 "администратора код в разделе «🏫 Школа»."))


def logout():
    lang = i18n.lang()
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state["lang"] = lang
    st.query_params.clear()


def register_student(name, email, class_row):
    """Оқушыны тіркеп, құпиясөзді поштаға жібереді. (user, password|None, қате) қайтарады."""
    password = auth.generate_password()
    uid = auth.create_user(email, name, password, "student")
    repo.enroll(class_row["id"], uid)
    ok, err = mailer.send_email(email, "PISA Жас дарын — логин / пароль",
                                mailer.credentials_email(name, email, password, class_row["name"], APP_URL,
                                                         class_link(class_row["join_code"])))
    return auth.get_user(uid), (None if ok else password), err


def header_with_lang(text):
    a, b = st.columns([4, 1.4])
    a.title(text)
    i18n.switcher(b, key="lang_top")


# ======================================================================
#                               КІРУ БЕТТЕРІ
# ======================================================================

def login_form(key="login"):
    with st.form(key):
        email = st.text_input(T("Email (логин)", "Email (логин)"))
        password = st.text_input(T("Құпиясөз", "Пароль"), type="password")
        if st.form_submit_button(T("Кіру", "Войти"), type="primary", use_container_width=True):
            user = auth.login(email, password)
            if user:
                do_login(user)
                return user
            st.error(T("Email немесе құпиясөз қате.", "Неверный email или пароль."))
    return None


def forgot_password_form():
    with st.expander(T("Құпиясөзді ұмыттыңыз ба?", "Забыли пароль?")):
        email = st.text_input("Email", key="forgot_email")
        if st.button(T("Жаңа құпиясөзді поштаға жіберу", "Отправить новый пароль на почту")):
            user = auth.get_user_by_email(email) if auth.valid_email(email) else None
            if not mailer.is_configured():
                st.warning(T("Пошта бапталмаған. Мұғаліміңізге хабарласыңыз — ол құпиясөзді жаңарта алады.",
                             "Почта не настроена. Обратитесь к учителю — он может обновить пароль."))
            elif user:
                pw = auth.generate_password()
                ok, err = mailer.send_email(user["email"], "PISA Жас дарын — жаңа құпиясөз / новый пароль",
                                            mailer.reset_email(user["name"], user["email"], pw, APP_URL))
                if ok:
                    auth.set_password(user["id"], pw)
                    st.success(T("Жаңа құпиясөз поштаңызға жіберілді.", "Новый пароль отправлен на вашу почту."))
                else:
                    st.error(T("Хат жіберілмеді: ", "Письмо не отправлено: ") + err)
            else:
                st.success(T("Егер бұл email тіркелген болса, жаңа құпиясөз жіберілді.",
                             "Если этот email зарегистрирован, новый пароль отправлен."))


def show_credentials_fallback(email, password, err):
    st.warning(T(f"Хат жіберілмеді ({err}). Логин мен құпиясөзді жазып алыңыз:",
                 f"Письмо не отправлено ({err}). Запишите логин и пароль:"))
    st.code(f"Логин: {email}\n{T('Құпиясөз', 'Пароль')}: {password}", language=None)


def join_page(code):
    cls = repo.class_by_code(code)
    header_with_lang("📘 PISA Жас дарын")
    if not cls:
        st.error(T("Сынып табылмады. Сілтемені тексеріңіз.", "Класс не найден. Проверьте ссылку."))
        if st.button(T("Басты бетке", "На главную")):
            st.query_params.clear()
            st.rerun()
        return
    st.subheader(T("Сыныпқа қосылу", "Вступление в класс") + f": «{cls['name']}»")
    st.write(T("Курс", "Курс") + f": **{course_name(cls)}** · " + T("Мұғалім", "Учитель") + f": **{cls['teacher_name']}**")
    if not cls["is_open"]:
        st.error(T("Бұл сыныпқа тіркелу жабық. Мұғаліміңізге хабарласыңыз.",
                   "Регистрация в этот класс закрыта. Обратитесь к учителю."))
        return

    user = current_user()
    if user:
        if user["role"] != "student":
            st.info(T("Сіз мұғалім ретінде кірдіңіз. Сынып сілтемесі оқушыларға арналған.",
                      "Вы вошли как учитель. Ссылка класса предназначена для учеников."))
            if st.button(T("Басты бетке", "На главную")):
                st.query_params.clear()
                st.rerun()
            return
        repo.enroll(cls["id"], user["id"])
        st.success(T("Сіз сыныпқа қосылдыңыз!", "Вы вступили в класс!"))
        if st.button(T("Сабақтарға өту", "Перейти к урокам"), type="primary"):
            st.session_state["open_class"] = cls["id"]
            st.query_params.clear()
            st.rerun()
        return

    t1, t2 = st.tabs([T("🆕 Тіркелу", "🆕 Регистрация"), T("🔑 Аккаунтым бар", "🔑 У меня есть аккаунт")])
    with t1:
        st.caption(T("Аты-жөніңіз бен email-ді жазыңыз. Логин мен құпиясөз поштаңызға келеді.",
                     "Укажите ФИО и email. Логин и пароль придут на вашу почту."))
        with st.form("join_reg"):
            name = st.text_input(T("Аты-жөні", "Фамилия и имя"))
            email = st.text_input("Email")
            sent = st.form_submit_button(T("Тіркелу", "Зарегистрироваться"), type="primary", use_container_width=True)
        if sent:
            if len(name.strip()) < 3:
                st.error(T("Аты-жөніңізді толық жазыңыз.", "Укажите фамилию и имя полностью."))
            elif not auth.valid_email(email):
                st.error(T("Email дұрыс емес.", "Неверный email."))
            elif auth.get_user_by_email(email) or schools.is_reserved(email):
                st.error(T("Бұл email тіркелген. «Аккаунтым бар» бетінен кіріңіз немесе құпиясөзді қалпына келтіріңіз.",
                           "Этот email уже зарегистрирован. Войдите во вкладке «У меня есть аккаунт» или восстановите пароль."))
            else:
                _, pw, err = register_student(name, email, cls)
                if pw is None:
                    st.success(T(f"Тіркелдіңіз! Логин мен құпиясөз **{email}** поштасына жіберілді. «Аккаунтым бар» "
                                 "бетінен кіріңіз (Спам папкасын да қараңыз).",
                                 f"Готово! Логин и пароль отправлены на **{email}**. Войдите во вкладке «У меня есть "
                                 "аккаунт» (проверьте и папку «Спам»)."))
                else:
                    show_credentials_fallback(email, pw, err)
    with t2:
        user = login_form("join_login")
        if user:
            if user["role"] == "student":
                repo.enroll(cls["id"], user["id"])
                st.session_state["open_class"] = cls["id"]
            st.query_params.clear()
            st.rerun()
        forgot_password_form()


def landing_page():
    header_with_lang("📘 PISA Жас дарын")
    st.caption(T("Функционалдық сауаттылық бойынша оқу платформасы",
                 "Образовательная платформа по функциональной грамотности"))
    a, b = st.columns([1, 1], gap="large")
    with a:
        st.subheader(T("Кіру", "Вход"))
        if login_form():
            st.rerun()
        forgot_password_form()
    with b:
        st.subheader(T("Сыныпқа қосылу", "Вступить в класс"))
        code = st.text_input(T("Сынып коды (мұғалімнен алыңыз)", "Код класса (получите у учителя)"), max_chars=8)
        if st.button(T("Қосылу", "Вступить"), use_container_width=True) and code.strip():
            st.query_params["join"] = code.strip().upper()
            st.rerun()
        st.divider()
        with st.expander(T("👩‍🏫 Мұғалім ретінде тіркелу", "👩‍🏫 Регистрация учителя")):
            need_code = bool(secret("TEACHER_CODE"))
            with st.form("teacher_reg"):
                name = st.text_input(T("Аты-жөні", "ФИО"))
                email = st.text_input("Email")
                pw1 = st.text_input(T("Құпиясөз (кемінде 6 таңба)", "Пароль (минимум 6 символов)"), type="password")
                tcode = st.text_input(T("Мұғалім коды (әкімшіден)", "Код учителя (у администратора)"),
                                      type="password") if need_code else ""
                ok = st.form_submit_button(T("Тіркелу", "Зарегистрироваться"))
            if ok:
                if need_code and tcode != secret("TEACHER_CODE"):
                    st.error(T("Мұғалім коды қате.", "Неверный код учителя."))
                elif len(name.strip()) < 3 or not auth.valid_email(email) or len(pw1) < 6:
                    st.error(T("Барлық өрістерді дұрыс толтырыңыз.", "Заполните все поля правильно."))
                elif auth.get_user_by_email(email) or schools.is_reserved(email):
                    st.error(T("Бұл email тіркелген.", "Этот email уже зарегистрирован."))
                else:
                    uid = auth.create_user(email, name, pw1, "teacher")
                    do_login(auth.get_user(uid))
                    st.rerun()


# ======================================================================
#                               МҰҒАЛІМ
# ======================================================================

def teacher_courses(user):
    st.header(T("📚 Курстар және сабақтар", "📚 Курсы и уроки"))
    all_courses = repo.courses()
    with st.expander(T("➕ Жаңа курс құру", "➕ Создать курс"), expanded=not all_courses):
        with st.form("new_course"):
            t_kz = st.text_input(T("Курс атауы (қазақша)", "Название курса (каз.)"))
            t_ru = st.text_input(T("Курс атауы (орысша)", "Название курса (рус.)"))
            d = st.text_area(T("Сипаттама", "Описание"), height=80)
            if st.form_submit_button(T("Құру", "Создать")) and t_kz.strip():
                st.session_state["course_id"] = repo.create_course(t_kz, d, user["id"], t_ru or None)
                st.rerun()
    if not all_courses:
        return
    ids = [c["id"] for c in all_courses]
    if st.session_state.get("course_id") not in ids:
        st.session_state["course_id"] = ids[0]
    cid = st.selectbox(T("Курс", "Курс"), ids, key="course_id", format_func=lambda i: title(repo.course(i)))
    course = repo.course(cid)

    unlocked = schools.is_unlocked(user)
    if not unlocked:
        locked_notice(user)
    left, right = st.columns([1, 2.6], gap="large")
    with left:
        with st.expander(T("Курс параметрлері", "Параметры курса")):
            nt = st.text_input(T("Атауы (қаз.)", "Название (каз.)"), course["title"], key=f"ct{cid}")
            ntr = st.text_input(T("Атауы (орыс.)", "Название (рус.)"), course.get("title_ru") or "", key=f"ctr{cid}")
            nd = st.text_area(T("Сипаттама (қаз.)", "Описание (каз.)"), course["description"] or "", key=f"cd{cid}")
            ndr = st.text_area(T("Сипаттама (орыс.)", "Описание (рус.)"), course.get("description_ru") or "",
                               key=f"cdr{cid}")
            if st.button(T("Сақтау", "Сохранить"), key=f"cs{cid}"):
                repo.update_course(cid, nt, nd, ntr or None, ndr or None)
                st.rerun()
        st.markdown(T("**Курс мазмұны**", "**Содержание курса**"))
        for mi, m in enumerate(repo.modules(cid), start=1):
            with st.expander(f"{mi}. {title(m)}", expanded=True):
                for li, l in enumerate(repo.lessons(m["id"]), start=1):
                    n = len(repo.steps(l["id"]))
                    c1, c2, c3 = st.columns([6, 1, 1])
                    active = st.session_state.get("edit_lesson") == l["id"]
                    if c1.button(f"{'▶ ' if active else ''}{'🔒 ' if not unlocked else ''}{mi}.{li} {title(l)}  ·  {n}",
                                 key=f"open{l['id']}", use_container_width=True, disabled=not unlocked):
                        st.session_state["edit_lesson"] = l["id"]
                        st.rerun()
                    if c2.button("↑", key=f"lu{l['id']}"):
                        repo.move("lessons", l["id"], "module_id", -1)
                        st.rerun()
                    if c3.button("↓", key=f"ld{l['id']}"):
                        repo.move("lessons", l["id"], "module_id", 1)
                        st.rerun()
                with st.popover(T("➕ Сабақ қосу", "➕ Добавить урок")):
                    lt = st.text_input(T("Атауы (қаз.)", "Название (каз.)"), key=f"nl{m['id']}")
                    ltr = st.text_input(T("Атауы (орыс.)", "Название (рус.)"), key=f"nlr{m['id']}")
                    if st.button(T("Қосу", "Добавить"), key=f"nlb{m['id']}") and lt.strip():
                        st.session_state["edit_lesson"] = repo.create_lesson(m["id"], lt, None, ltr or None)
                        st.rerun()
                with st.popover(T("⚙ Модуль", "⚙ Модуль")):
                    mt = st.text_input(T("Атауы (қаз.)", "Название (каз.)"), m["title"], key=f"mt{m['id']}")
                    mtr = st.text_input(T("Атауы (орыс.)", "Название (рус.)"), m.get("title_ru") or "", key=f"mtr{m['id']}")
                    a, b, c = st.columns(3)
                    if a.button(T("Сақтау", "Сохранить"), key=f"ms{m['id']}"):
                        repo.update_module(m["id"], mt, mtr or None)
                        st.rerun()
                    if b.button("↑", key=f"mu{m['id']}"):
                        repo.move("modules", m["id"], "course_id", -1)
                        st.rerun()
                    if c.button("↓", key=f"md{m['id']}"):
                        repo.move("modules", m["id"], "course_id", 1)
                        st.rerun()
                    if st.checkbox(T("Жоюды растаймын", "Подтверждаю удаление"), key=f"mdc{m['id']}") and \
                            st.button(T("🗑 Модульді жою", "🗑 Удалить модуль"), key=f"mdel{m['id']}"):
                        repo.delete_module(m["id"])
                        st.rerun()
        with st.form(f"new_mod{cid}", clear_on_submit=True):
            mt = st.text_input(T("Жаңа модуль атауы (қаз.)", "Название нового модуля (каз.)"))
            mtr = st.text_input(T("Жаңа модуль атауы (орыс.)", "Название нового модуля (рус.)"))
            if st.form_submit_button(T("➕ Модуль қосу", "➕ Добавить модуль")) and mt.strip():
                repo.create_module(cid, mt, mtr or None)
                st.rerun()

    with right:
        lid = st.session_state.get("edit_lesson")
        lesson = repo.lesson(lid) if lid else None
        if lesson and unlocked:
            editor.lesson_editor(lesson)
        else:
            st.info(T("Сол жақтан сабақты таңдаңыз немесе жаңа сабақ қосыңыз. Сабақ ішінде «➕ Жаңа қадам» арқылы мәтін, "
                      "тест, кестелік, сандық, сәйкестендіру т.б. тапсырмалар қосасыз. Әр тапсырманы қазақша және "
                      "орысша толтыруға болады.",
                      "Выберите урок слева или добавьте новый. Внутри урока через «➕ Новый шаг» добавляются текст, "
                      "тест, табличные, числовые задачи, сопоставление и др. Каждое задание можно заполнить на "
                      "казахском и русском языках."))


def teacher_classes(user):
    st.header(T("👥 Сыныптар", "👥 Классы"))
    if not mailer.is_configured():
        st.warning(T("Пошта (SMTP) бапталмаған — оқушылардың құпиясөздері экранда көрсетіледі. README бойынша "
                     "secrets.toml-ға [smtp] қосыңыз.",
                     "Почта (SMTP) не настроена — пароли учеников показываются на экране. Добавьте [smtp] в "
                     "secrets.toml по инструкции README."))
    unlocked = schools.is_unlocked(user)
    if not unlocked:
        locked_notice(user)
    with st.expander(T("➕ Жаңа сынып құру", "➕ Создать класс"), expanded=not repo.teacher_classes(user["id"])):
        with st.form("new_class"):
            name = st.text_input(T("Сынып атауы (мысалы, 9 «А»)", "Название класса (например, 9 «А»)"))
            courses = repo.courses()
            cid = st.selectbox(T("Курс", "Курс"), [c["id"] for c in courses],
                               format_func=lambda i: title(next(c for c in courses if c["id"] == i)))
            if st.form_submit_button(T("Құру", "Создать"), type="primary", disabled=not unlocked) and name.strip() \
                    and schools.is_unlocked(user):
                repo.create_class(name, cid, user["id"])
                st.rerun()

    for cls in repo.teacher_classes(user["id"]):
        with st.expander(f"**{cls['name']}** · {course_name(cls)} · {T('оқушылар', 'учеников')}: {cls['students']}"):
            a, b = st.columns([2, 1])
            with a:
                st.markdown(T("**Сыныптың сілтемесі** (оқушыларға жіберіңіз):", "**Ссылка класса** (отправьте ученикам):"))
                st.code(class_link(cls["join_code"]), language=None)
            with b:
                st.markdown(T("Сынып коды:", "Код класса:"))
                st.markdown(f"<div class='big-code'>{cls['join_code']}</div>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            is_open = c1.toggle(T("Тіркелу ашық", "Регистрация открыта"), value=bool(cls["is_open"]), key=f"open{cls['id']}")
            if is_open != bool(cls["is_open"]):
                repo.set_class_open(cls["id"], is_open)
                st.rerun()
            if c2.button(T("🔄 Кодты жаңарту", "🔄 Обновить код"), key=f"regen{cls['id']}"):
                repo.regenerate_code(cls["id"])
                st.rerun()
            if c3.checkbox(T("Жоюды растаймын", "Подтверждаю удаление"), key=f"cdc{cls['id']}") and \
                    c3.button(T("🗑 Сыныпты жою", "🗑 Удалить класс"), key=f"cdel{cls['id']}"):
                repo.delete_class(cls["id"])
                st.rerun()

            st.markdown(T("##### Оқушылар", "##### Ученики"))
            students = repo.class_students(cls["id"])
            if students:
                st.dataframe(pd.DataFrame(students)[["name", "email", "joined_at"]]
                             .rename(columns={"name": T("Аты-жөні", "ФИО"), "email": "Email",
                                              "joined_at": T("Тіркелген", "Дата регистрации")}),
                             hide_index=True, use_container_width=True)
                s_ids = [s["id"] for s in students]
                sel = st.selectbox(T("Оқушы", "Ученик"), s_ids, key=f"sel{cls['id']}",
                                   format_func=lambda i: next(s["name"] for s in students if s["id"] == i))
                x, y = st.columns(2)
                if x.button(T("🔑 Құпиясөзді жаңартып, поштаға жіберу", "🔑 Сбросить пароль и отправить на почту"),
                            key=f"rp{cls['id']}"):
                    stu = auth.get_user(sel)
                    pw = auth.generate_password()
                    auth.set_password(sel, pw)
                    ok, err = mailer.send_email(stu["email"], "PISA Жас дарын — жаңа құпиясөз / новый пароль",
                                                mailer.reset_email(stu["name"], stu["email"], pw, APP_URL))
                    if ok:
                        st.success(T("Жаңа құпиясөз жіберілді.", "Новый пароль отправлен."))
                    else:
                        show_credentials_fallback(stu["email"], pw, err)
                if y.button(T("➖ Сыныптан шығару", "➖ Исключить из класса"), key=f"un{cls['id']}"):
                    repo.unenroll(cls["id"], sel)
                    st.rerun()
            else:
                st.caption(T("Әзірге оқушы жоқ. Сілтемені жіберіңіз немесе төменде тізіммен қосыңыз.",
                             "Пока нет учеников. Отправьте ссылку или добавьте списком ниже."))

            with st.popover(T("📋 Оқушыларды тізіммен қосу", "📋 Добавить учеников списком")):
                st.caption(T("Әр жолға: Аты-жөні; email", "В каждой строке: ФИО; email"))
                txt = st.text_area(T("Тізім", "Список"), key=f"bulk{cls['id']}", height=160,
                                   placeholder="Ахметов Ержан; erzhan@mail.kz\nСерікова Аружан; aruzhan@gmail.com")
                if st.button(T("Қосу және хат жіберу", "Добавить и отправить письма"), key=f"bulkb{cls['id']}"):
                    report = []
                    for line in txt.splitlines():
                        if ";" not in line:
                            continue
                        name, email = [x.strip() for x in line.split(";", 1)]
                        if not auth.valid_email(email):
                            report.append((name, email, T("❌ email қате", "❌ неверный email"), ""))
                            continue
                        ex = auth.get_user_by_email(email)
                        if ex:
                            repo.enroll(cls["id"], ex["id"])
                            report.append((name, email, T("ℹ️ бұрын тіркелген — сыныпқа қосылды",
                                                          "ℹ️ уже зарегистрирован — добавлен в класс"), ""))
                            continue
                        _, pw, err = register_student(name, email, cls)
                        report.append((name, email, T("✅ хат жіберілді", "✅ письмо отправлено") if pw is None
                                       else T("⚠️ хат кетпеді: ", "⚠️ письмо не отправлено: ") + err, pw or ""))
                    if report:
                        st.dataframe(pd.DataFrame(report, columns=[T("Аты-жөні", "ФИО"), "Email", T("Нәтиже", "Результат"),
                                                                   T("Құпиясөз", "Пароль")]), hide_index=True)


def _class_picker(user, key):
    classes = repo.teacher_classes(user["id"])
    if not classes:
        st.info(T("Алдымен «Сыныптар» бөлімінде сынып құрыңыз.", "Сначала создайте класс в разделе «Классы»."))
        return None
    cid = st.selectbox(T("Сынып", "Класс"), [c["id"] for c in classes], key=key,
                       format_func=lambda i: next(f"{c['name']} — {course_name(c)}" for c in classes if c["id"] == i))
    return repo.get_class(cid)


def build_gradebook(cls, detail=False):
    students = repo.class_students(cls["id"])
    lessons = repo.course_lessons(cls["course_id"])
    scores = {(r["student_id"], r["step_id"]): float(r["best"] or 0) for r in repo.class_scores(cls["id"])}
    lesson_steps = {l["id"]: [s for s in repo.steps(l["id"]) if s["type"] != "text"] for l in lessons}
    total_max = sum(float(s["points"] or 0) for st_ in lesson_steps.values() for s in st_)
    rows = []
    for stu in students:
        row = {T("Оқушы", "Ученик"): stu["name"], "Email": stu["email"]}
        total = 0.0
        for l in lessons:
            ssum = 0.0
            for j, s in enumerate(lesson_steps[l["id"]], start=1):
                v = scores.get((stu["id"], s["id"]), 0.0)
                ssum += v
                if detail:
                    row[f"{title(l)} · {j}"] = v
            if not detail:
                row[title(l)] = ssum
            total += ssum
        row[T("Барлығы", "Итого")] = round(total, 2)
        row["%"] = round(100 * total / total_max, 1) if total_max else 0
        rows.append(row)
    return pd.DataFrame(rows), total_max, lessons, lesson_steps


def teacher_gradebook(user):
    st.header(T("📒 Журнал және есеп", "📒 Журнал и отчёт"))
    cls = _class_picker(user, "gb_class")
    if not cls:
        return
    columns, rows, max_total = report.collect(cls, i18n.lang())
    started = sum(1 for r in rows if r["total"] > 0)
    avg = sum(r["total"] for r in rows) / len(rows) if rows else 0
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(T("Оқушылар саны", "Учащихся"), len(rows))
    m2.metric(T("Орындағандар", "Приступили"), started)
    m3.metric(T("Орташа балл", "Средний балл"), f"{avg:.1f} / {max_total:g}")
    m4.metric(T("Орташа нәтиже", "Средний результат"), f"{(100 * avg / max_total if max_total else 0):.0f}%")

    st.download_button(T("⬇ Excel есебін жүктеу (табель + жиынтық + оқушылар)",
                         "⬇ Скачать отчёт Excel (табель + сводка + ученики)"),
                       report.build_xlsx(cls, user["name"], i18n.lang()), file_name=report.filename(cls),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    st.caption(T("Есеп әр жүктеген сайын соңғы баллдармен жаңадан құрылады (Stepik gradebook форматы).",
                 "Отчёт формируется заново при каждой выгрузке с актуальными баллами (формат Stepik gradebook)."))
    if not rows:
        st.info(T("Сыныпта оқушы жоқ.", "В классе нет учеников."))
        return

    tab1, tab2, tab3 = st.tabs([T("📒 Табель", "📒 Табель"), T(f"👥 Оқушылар ({len(rows)})", f"👥 Ученики ({len(rows)})"),
                                T("📊 Сабақтар бойынша", "📊 По урокам")])
    with tab1:
        detail = st.toggle(T("Әр тапсырма бойынша (Q)", "По каждому заданию (Q)"), key="gb_detail", value=True)
        if detail:
            df = pd.DataFrame([{T("Оқушы", "Ученик"): r["user"]["name"],
                                **{c[1]: v for c, v in zip(columns, r["vals"])},
                                "total": round(r["total"], 2)} for r in rows])
        else:
            df, _, _, _ = build_gradebook(cls, False)
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={"%": st.column_config.ProgressColumn("%", min_value=0, max_value=100, format="%.0f%%")})
    with tab2:
        df2 = pd.DataFrame([{
            T("Аты-жөні", "ФИО"): r["user"]["name"], "Email": r["user"]["email"],
            T("Сынып", "Класс"): f"{r['user'].get('grade') or ''}{r['user'].get('grade_letter') or ''}",
            T("Тіркелген", "Вступил"): (r["joined"] or "")[:16],
            T("Соңғы белсенділік", "Последняя активность"): (r["last"] or "")[:16],
            T("Балл", "Балл"): round(r["total"], 2),
            "%": round(100 * r["total"] / max_total, 1) if max_total else 0} for r in rows])
        st.dataframe(df2.sort_values(T("Балл", "Балл"), ascending=False), hide_index=True, use_container_width=True,
                     column_config={"%": st.column_config.ProgressColumn("%", min_value=0, max_value=100, format="%.0f%%")})
    with tab3:
        lessons_order = list(dict.fromkeys(c[3] for c in columns))
        data = []
        for lt in lessons_order:
            idx = [i for i, c in enumerate(columns) if c[3] == lt]
            mx = sum(columns[i][2] for i in idx)
            sums = [sum(r["vals"][i] for i in idx) for r in rows]
            a_ = sum(sums) / len(sums)
            data.append({T("Сабақ", "Урок"): lt, T("Макс.", "Макс."): mx, T("Орташа", "Среднее"): round(a_, 2),
                         "%": round(100 * a_ / mx, 1) if mx else 0,
                         T("Толық орындағандар", "Выполнили полностью"): sum(1 for x in sums if mx and x >= mx - 1e-9)})
        st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True,
                     column_config={"%": st.column_config.ProgressColumn("%", min_value=0, max_value=100, format="%.0f%%")})


def teacher_review(user):
    st.header(T("📝 Еркін жауаптарды тексеру", "📝 Проверка свободных ответов"))
    cls = _class_picker(user, "rv_class")
    if not cls:
        return
    pend = repo.pending_reviews(cls["id"])
    if not pend:
        st.success(T("Тексеруді күтетін жауап жоқ 🎉", "Нет ответов, ожидающих проверки 🎉"))
        return
    for sub in pend:
        content = i18n.localize(db.loads(sub["step_content"], {}))
        with st.container(border=True):
            st.markdown(f"**{sub['student_name']}** · {title(sub, 'lesson_title')} · {sub['created_at']}")
            with st.expander(T("Тапсырма", "Задание")):
                player.show_text(content.get("text", ""))
                if content.get("rubric"):
                    st.info(T("Критерий: ", "Критерии: ") + content["rubric"])
            st.markdown(T("**Жауабы:**", "**Ответ:**"))
            st.write(db.loads(sub["answer"], ""))
            mx = float(sub["step_points"] or 0)
            a, b, c = st.columns([1, 3, 1])
            score = a.number_input(T("Балл", "Балл") + f" (0–{mx:g})", 0.0, mx, 0.0, 0.5, key=f"rs{sub['id']}")
            comment = b.text_input(T("Пікір", "Комментарий"), key=f"rc{sub['id']}")
            if c.button(T("Бағалау", "Оценить"), key=f"rb{sub['id']}", type="primary"):
                repo.grade_submission(sub["id"], score, mx, comment)
                st.rerun()


def teacher_import(user):
    st.header(T("⬇ Stepik-тен импорттау", "⬇ Импорт из Stepik"))
    st.markdown(stepik_import.__doc__)
    courses = repo.courses()
    cid = st.selectbox(T("Курс", "Курс"), [c["id"] for c in courses],
                       format_func=lambda i: title(next(c for c in courses if c["id"] == i)), key="imp_course")
    lessons = [l for l in repo.course_lessons(cid) if l.get("stepik_lesson_id")]
    a, b = st.columns(2)
    client_id = a.text_input("Client ID", value=secret("STEPIK_CLIENT_ID", "") or "")
    client_secret = b.text_input("Client Secret", type="password", value=secret("STEPIK_CLIENT_SECRET", "") or "")
    c_, d_ = st.columns(2)
    sp_user = c_.text_input(T("Stepik логині (email) — жабық курс үшін", "Логин Stepik (email) — для закрытого курса"),
                            value=secret("STEPIK_USERNAME", "") or "")
    sp_pass = d_.text_input(T("Stepik құпиясөзі", "Пароль Stepik"), type="password",
                            value=secret("STEPIK_PASSWORD", "") or "")
    chosen = st.multiselect(T("Сабақтар (Stepik ID жазылғандар)", "Уроки (с указанным ID Stepik)"), [l["id"] for l in lessons],
                            default=[l["id"] for l in lessons if not repo.steps(l["id"])],
                            format_func=lambda i: next(f"{title(l)} (#{l['stepik_lesson_id']}) · "
                                                       f"{len(repo.steps(l['id']))}" for l in lessons if l["id"] == i))
    replace = st.checkbox(T("Бар қадамдарды ауыстыру (әйтпесе соңына қосылады)",
                            "Заменить существующие шаги (иначе добавятся в конец)"))
    if not schools.is_unlocked(user):
        locked_notice(user)
        return
    if st.button(T("Импорттау", "Импортировать"), type="primary", disabled=not (client_id and client_secret and chosen)):
        try:
            token = stepik_import.get_token(client_id, client_secret, sp_user.strip() or None, sp_pass or None)
        except Exception as e:  # noqa: BLE001
            st.error(T("Stepik токенін алу мүмкін болмады: ", "Не удалось получить токен Stepik: ") + str(e))
            return
        prog = st.progress(0.0)
        for n, lid in enumerate(chosen, start=1):
            l = repo.lesson(lid)
            try:
                _, steps, warnings = stepik_import.fetch_lesson(l["stepik_lesson_id"], token)
                if replace:
                    for s in repo.steps(lid):
                        repo.delete_step(s["id"])
                for t, content, pts in steps:
                    repo.create_step(lid, t, content, pts)
                st.success(f"{title(l)}: {len(steps)} " + T("қадам импортталды", "шагов импортировано"))
                for w in warnings:
                    st.caption(f"⚠️ {w}")
            except Exception as e:  # noqa: BLE001
                st.error(f"{title(l)}: {e}")
            prog.progress(n / len(chosen))


# ======================================================================
#                               ОҚУШЫ
# ======================================================================

def student_home(user):
    classes = repo.student_classes(user["id"])
    if not classes:
        st.header(T("Сәлем, ", "Привет, ") + user["name"].split()[0] + "!")
        st.info(T("Сіз әлі ешбір сыныпқа қосылмағансыз. Мұғаліміңізден сынып сілтемесін не кодын алыңыз.",
                  "Вы ещё не состоите ни в одном классе. Получите у учителя ссылку или код класса."))
        code = st.text_input(T("Сынып коды", "Код класса"))
        if st.button(T("Қосылу", "Вступить")) and code.strip():
            st.query_params["join"] = code.strip().upper()
            st.rerun()
        return
    ids = [c["id"] for c in classes]
    if st.session_state.get("open_class") not in ids:
        st.session_state["open_class"] = ids[0]
    cid = st.selectbox(T("Сынып", "Класс"), ids, key="open_class",
                       format_func=lambda i: next(f"{c['name']} — {course_name(c)}" for c in classes if c["id"] == i))
    cls = repo.get_class(cid)
    lid = st.session_state.get("open_lesson")
    lesson = repo.lesson(lid) if lid else None
    if lesson and schools.class_unlocked(cls):
        if st.button(T("← Курс мазмұнына оралу", "← К содержанию курса")):
            st.session_state.pop("open_lesson")
            st.rerun()
        st.subheader(title(lesson))
        player.render_lesson(lesson, user["id"], cls["id"])
        return
    syllabus(user, cls)


def syllabus(user, cls):
    course = repo.course(cls["course_id"])
    unlocked = schools.class_unlocked(cls)
    if not unlocked:
        st.warning(T(f"🔒 Мектеп коды {schools.NO_CODE}: сабақтар әзірге жабық. Мұғаліміңіз мектеп кодын енгізгеннен "
                     "кейін ашылады.",
                     f"🔒 Код школы {schools.NO_CODE}: уроки пока закрыты. Они откроются после того, как учитель "
                     "введёт код школы."))
    st.header(title(course))
    desc = title(course, "description")
    if desc:
        st.caption(desc)
    scores = repo.best_scores(user["id"], cls["id"])
    total_e = total_m = 0.0
    blocks = []
    for mi, m in enumerate(repo.modules(course["id"]), start=1):
        rows, me, mm = [], 0.0, 0.0
        visible = [l for l in repo.lessons(m["id"]) if repo.steps(l["id"])]  # бос сабақтар оқушыға көрсетілмейді
        for li, l in enumerate(visible, start=1):
            steps = [s for s in repo.steps(l["id"]) if s["type"] != "text"]
            mx = sum(float(s["points"] or 0) for s in steps)
            earned = sum(scores.get(s["id"], (0, None))[0] for s in steps)
            rows.append((li, l, earned, mx))
            me += earned
            mm += mx
        blocks.append((mi, m, rows, me, mm))
        total_e += me
        total_m += mm
    st.progress(total_e / total_m if total_m else 0.0,
                text=T("Жалпы прогресс", "Общий прогресс") + f": {total_e:g} / {total_m:g} " + T("балл", "балл."))
    st.markdown(T("### Курс бағдарламасы", "### Программа курса"))
    for mi, m, rows, me, mm in blocks:
        with st.container(border=True):
            st.markdown(f"**{mi}. {title(m)}** — {me:g}/{mm:g}")
            for li, l, earned, mx in rows:
                a, b = st.columns([5, 1])
                done = mx and earned >= mx
                icon = "🔒" if not unlocked else ("✅" if done else "📄")
                if a.button(f"{icon} {mi}.{li} {title(l)}", key=f"ol{l['id']}", use_container_width=True,
                            disabled=not unlocked):
                    st.session_state["open_lesson"] = l["id"]
                    st.rerun()
                b.markdown(f"**{earned:g} / {mx:g}**")


def student_grades(user):
    st.header(T("📊 Менің бағаларым", "📊 Мои оценки"))
    for cls in repo.student_classes(user["id"]):
        st.subheader(f"{cls['name']} — {course_name(cls)}")
        scores = repo.best_scores(user["id"], cls["id"])
        rows = []
        for l in repo.course_lessons(cls["course_id"]):
            steps = [s for s in repo.steps(l["id"]) if s["type"] != "text"]
            mx = sum(float(s["points"] or 0) for s in steps)
            e = sum(scores.get(s["id"], (0, None))[0] for s in steps)
            pend = sum(1 for s in steps if scores.get(s["id"], (0, None))[1] == "pending")
            rows.append({T("Модуль", "Модуль"): title(l, "module_title"), T("Сабақ", "Урок"): title(l),
                         T("Балл", "Балл"): e, T("Макс", "Макс."): mx, T("Тексерілуде", "На проверке"): pend or ""})
        df = pd.DataFrame(rows)
        if not df.empty:
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.metric(T("Барлығы", "Итого"), f"{df[T('Балл', 'Балл')].sum():g} / {df[T('Макс', 'Макс.')].sum():g}")


GRADES = [str(g) for g in range(1, 12)]
LETTERS = ["", "А", "Ә", "Б", "В", "Г", "Ғ", "Д", "Е", "Ж", "З", "И", "К"]


def profile(user, onboarding=False):
    st.header(T("👤 Профильді баптау", "👤 Настройки профиля"))
    if onboarding:
        st.info(T("Тіркелу сәтті өтті! Профиліңізді толтырыңыз — бұл мұғаліміңізге журналда сізді тануға көмектеседі.",
                  "Регистрация прошла успешно! Заполните профиль — это поможет учителю узнать вас в журнале."))
    role = T("Әкімші", "Администратор") if schools.is_admin(user) else (
        T("Мұғалім", "Учитель") if is_teacher(user) else T("Оқушы", "Ученик"))
    lic = schools.user_license(user)
    a, b, c = st.columns(3)
    a.metric(T("Рөлі", "Роль"), role)
    b.metric(T("Мектеп", "Школа"), lic["school_name"] if lic else "—")
    c.metric(T("Мектеп коды", "Код школы"), schools.code_of(user) if is_teacher(user) else ("✓" if lic else schools.NO_CODE))
    if user["role"] == "student":
        classes = repo.student_classes(user["id"])
        if classes:
            st.caption(T("Сыныптарым", "Мои классы") + ": " + ", ".join(f"{x['name']} ({x['teacher_name']})" for x in classes))

    with st.form("profile_form"):
        st.markdown(T("##### Жеке мәліметтер", "##### Личные данные"))
        name = st.text_input(T("Аты-жөні", "Фамилия и имя"), user["name"])
        st.text_input(T("Email (логин, өзгертілмейді)", "Email (логин, не меняется)"), user["email"], disabled=True)
        x, y = st.columns(2)
        if user["role"] == "student":
            grade = x.selectbox(T("Сынып", "Класс"), [""] + GRADES,
                                index=([""] + GRADES).index(user.get("grade") or "") if (user.get("grade") or "") in GRADES else 0)
            letter = y.selectbox(T("Литер", "Литера"), LETTERS,
                                 index=LETTERS.index(user.get("grade_letter") or "") if (user.get("grade_letter") or "") in LETTERS else 0)
            import datetime as _dt
            try:
                bd_val = _dt.date.fromisoformat(user["birth_date"]) if user.get("birth_date") else None
            except ValueError:
                bd_val = None
            birth = x.date_input(T("Туған күні", "Дата рождения"), value=bd_val, min_value=_dt.date(1990, 1, 1),
                                 max_value=_dt.date.today(), format="DD.MM.YYYY")
        else:
            grade, letter, birth = user.get("grade"), user.get("grade_letter"), None
        phone = (y if user["role"] == "student" else x).text_input(T("Телефон", "Телефон"), user.get("phone") or "",
                                                                  placeholder="+7 7xx xxx xx xx")
        city = st.text_input(T("Қала / ауыл", "Город / село"), user.get("city") or "")
        langs = list(i18n.LANGS)
        pref = st.radio(T("Интерфейс тілі", "Язык интерфейса"), langs, horizontal=True, format_func=lambda k: i18n.LANGS[k],
                        index=langs.index(user.get("pref_lang") or i18n.lang()))
        if st.form_submit_button(T("💾 Сақтау", "💾 Сохранить"), type="primary"):
            if len(name.strip()) < 3:
                st.error(T("Аты-жөніңізді толық жазыңыз.", "Укажите фамилию и имя полностью."))
            else:
                db.execute("""UPDATE users SET name=?, grade=?, grade_letter=?, birth_date=?, phone=?, city=?,
                              pref_lang=?, profile_done=1 WHERE id=?""",
                           (name.strip(), grade or None, letter or None, birth.isoformat() if birth else None,
                            phone.strip() or None, city.strip() or None, pref, user["id"]))
                st.session_state["lang"] = pref
                st.session_state["profile_saved"] = True
                st.rerun()
    if st.session_state.pop("profile_saved", False):
        st.success(T("Профиль сақталды ✓", "Профиль сохранён ✓"))
    if onboarding and st.button(T("Кейін толтырамын →", "Заполню позже →")):
        db.execute("UPDATE users SET profile_done=1 WHERE id=?", (user["id"],))
        st.rerun()

    with st.expander(T("🔑 Құпиясөзді өзгерту", "🔑 Изменить пароль")):
        with st.form("chpw"):
            old = st.text_input(T("Қазіргі құпиясөз", "Текущий пароль"), type="password")
            new = st.text_input(T("Жаңа құпиясөз (кемінде 6 таңба)", "Новый пароль (минимум 6 символов)"), type="password")
            new2 = st.text_input(T("Жаңа құпиясөзді қайталаңыз", "Повторите новый пароль"), type="password")
            if st.form_submit_button(T("Құпиясөзді өзгерту", "Изменить пароль")):
                if not auth.verify_password(old, user["password_hash"]):
                    st.error(T("Қазіргі құпиясөз қате.", "Неверный текущий пароль."))
                elif len(new) < 6:
                    st.error(T("Жаңа құпиясөз тым қысқа.", "Новый пароль слишком короткий."))
                elif new != new2:
                    st.error(T("Құпиясөздер сәйкес емес.", "Пароли не совпадают."))
                else:
                    auth.set_password(user["id"], new)
                    st.success(T("Өзгертілді.", "Изменено."))


def school_page(user):
    st.header(T("🏫 Мектеп", "🏫 Школа"))
    lic = schools.teacher_license(user["id"])
    if lic:
        st.success(T("Мектеп қосылған", "Школа подключена") + f": **{lic['school_name']}**")
        a, b, c = st.columns(3)
        a.metric(T("Мектеп коды", "Код школы"), lic["code"])
        b.metric(T("Оқу жылы", "Учебный год"), lic["academic_year"] or "—")
        c.metric(T("Жарамды", "Действует до"), lic["valid_until"])
        st.caption(T("Жаңа оқу жылында әкімшіден жаңа код алып, төменде енгізіңіз.",
                     "В новом учебном году получите у администратора новый код и введите его ниже."))
    else:
        old = db.query_one("SELECT c.* FROM users u JOIN school_codes c ON c.id=u.school_code_id WHERE u.id=?", (user["id"],))
        st.markdown(f"### {T('Ағымдағы код', 'Текущий код')}: `{schools.NO_CODE}`")
        if old:
            st.warning(T(f"«{old['school_name']}» мектебінің коды ({old['code']}) жарамсыз: мерзімі өткен немесе бұғатталған. "
                         "Жаңа код енгізіңіз.",
                         f"Код школы «{old['school_name']}» ({old['code']}) недействителен: истёк срок или заблокирован. "
                         "Введите новый код."))
        else:
            st.info(T("Код 000000 болғанда курстар ашылмайды, сынып құрылмайды, сабақ батырмалары белсенді емес. "
                      "Мектеп кодын әкімшіден сатып алып, осында енгізіңіз — мектеп атауы кодпен бірге жүктеледі.",
                      "При коде 000000 курсы не открываются, классы не создаются, кнопки уроков неактивны. Купите код "
                      "школы у администратора и введите его здесь — название школы загрузится вместе с кодом."))
    with st.form("activate_code", clear_on_submit=True):
        code = st.text_input(T("Мектеп коды (6 сан)", "Код школы (6 цифр)"), max_chars=6, placeholder="______")
        if st.form_submit_button(T("Кодты енгізу", "Ввести код"), type="primary"):
            ok, (kz, ru) = schools.activate(user, code)
            (st.success if ok else st.error)(T(kz, ru))
            if ok:
                st.balloons()
                st.rerun()


def admin_codes_page(user):
    if not schools.is_admin(user):
        st.error(T("Бұл бетке рұқсат жоқ.", "Нет доступа к этой странице."))
        return
    st.header(T("🔐 Мектеп кодтары (әкімші)", "🔐 Коды школ (администратор)"))
    with st.expander(T("🔄 Курс мазмұнын жаңарту", "🔄 Обновить содержимое курса")):
        st.caption(T("Бос сабақтарды дайын тапсырмалармен толтырады. Тапсырмасы бар сабақтарға тиіспейді.",
                     "Заполняет пустые уроки готовыми заданиями. Уроки, где уже есть задания, не изменяются."))
        if st.button(T("Жаңарту", "Обновить"), key="resync"):
            n = seed.sync_content()
            st.success(T(f"Толтырылған сабақтар: {n}", f"Заполнено уроков: {n}"))
    years = schools.academic_years()
    with st.form("gen_codes"):
        st.markdown(T("##### Жаңа код жасау", "##### Создать новый код"))
        school = st.text_input(T("Мектеп атауы", "Название школы"), placeholder="Екібастұз қ., №1 жалпы білім беретін мектеп")
        a, b = st.columns(2)
        yi = a.selectbox(T("Оқу жылы", "Учебный год"), list(range(len(years))),
                         format_func=lambda i: f"{years[i][0]} ({T('31 тамызға дейін', 'до 31 августа')} {years[i][1][:4]})")
        count = b.number_input(T("Код саны (әр мұғалімге біреу)", "Количество кодов (по одному на учителя)"), 1, 50, 1)
        if st.form_submit_button(T("⚙ Кодты автоматты жасау", "⚙ Сгенерировать код"), type="primary"):
            if len(school.strip()) < 3:
                st.error(T("Мектеп атауын жазыңыз.", "Укажите название школы."))
            else:
                codes = schools.generate_codes(school, years[yi][0], years[yi][1], count, user["id"])
                st.session_state["new_codes"] = (school, codes)
                st.rerun()
    if "new_codes" in st.session_state:
        school, codes = st.session_state["new_codes"]
        st.success(T(f"«{school}» үшін жасалған кодтар (әрқайсысы бір рет қолданылады):",
                     f"Коды для «{school}» (каждый используется один раз):"))
        st.code("\n".join(codes), language=None)
        if st.button(T("Жабу", "Закрыть")):
            st.session_state.pop("new_codes")
            st.rerun()

    st.markdown(T("##### Барлық кодтар", "##### Все коды"))
    status_names = {"new": T("🟢 Жаңа", "🟢 Новый"), "active": T("🔵 Қолданылған", "🔵 Активирован"),
                    "expired": T("⚪ Мерзімі өткен", "⚪ Истёк"), "revoked": T("🔴 Бұғатталған", "🔴 Заблокирован")}
    rows = schools.list_codes()
    a, b = st.columns([3, 1])
    q = a.text_input(T("Іздеу (мектеп немесе код)", "Поиск (школа или код)"), key="code_search")
    b.button(T("🔄 Жаңарту", "🔄 Обновить"), use_container_width=True)
    if q.strip():
        rows = [r for r in rows if q.lower() in r["school_name"].lower() or q in r["code"]]
    if not rows:
        st.info(T("Әзірге код жоқ.", "Пока нет кодов."))
        return
    df = pd.DataFrame([{
        T("Код", "Код"): r["code"],
        T("Мектеп", "Школа"): r["school_name"],
        T("Оқу жылы", "Учебный год"): r["academic_year"],
        T("Жарамды", "Действует до"): r["valid_until"],
        T("Статус", "Статус"): status_names.get(r["effective_status"], r["effective_status"]),
        T("Мұғалім", "Учитель"): f"{r['teacher_name']} ({r['teacher_email']})" if r["teacher_name"] else "",
        T("Енгізілген", "Активирован"): r["used_at"] or "",
        T("IP-адрестер", "IP-адреса"): "; ".join(f"{x['ip']} ({x['last_seen'][5:16]}, ×{x['visits']})" for x in r["ips"]),
    } for r in rows])
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={T("IP-адрестер", "IP-адреса"): st.column_config.TextColumn(width="large")})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button(T("⬇ CSV жүктеу", "⬇ Скачать CSV"), buf.getvalue().encode("utf-8-sig"), "school_codes.csv", "text/csv")

    with st.expander(T("Кодты бұғаттау / жою", "Заблокировать / удалить код")):
        cid = st.selectbox(T("Код", "Код"), [r["id"] for r in rows],
                           format_func=lambda i: next(f"{r['code']} — {r['school_name']}" for r in rows if r["id"] == i))
        x, y = st.columns(2)
        if x.button(T("🔴 Бұғаттау", "🔴 Заблокировать")):
            schools.revoke(cid)
            st.rerun()
        if y.checkbox(T("Жоюды растаймын", "Подтверждаю удаление"), key="del_code_ok") and \
                y.button(T("🗑 Жою", "🗑 Удалить")):
            schools.delete_code(cid)
            st.rerun()


# ======================================================================
#                               МАРШРУТ
# ======================================================================

def main():
    join_code = st.query_params.get("join")
    if join_code:
        join_page(join_code)
        return
    user = current_user()
    if not user:
        landing_page()
        return

    if not st.session_state.get("ip_logged"):
        schools.log_ip(user, client_ip())
        db.execute("UPDATE users SET last_seen=? WHERE id=?", (db.now(), user["id"]))
        st.session_state["ip_logged"] = True

    with st.sidebar:
        st.markdown("## 📘 PISA Жас дарын")
        i18n.switcher(st.sidebar, key="lang_side")
        st.caption(f"{user['name']} · " + (T("мұғалім", "учитель") if is_teacher(user) else T("оқушы", "ученик")))
        if is_teacher(user):
            pages = [("courses", T("📚 Курстар", "📚 Курсы"), teacher_courses),
                     ("classes", T("👥 Сыныптар", "👥 Классы"), teacher_classes),
                     ("gradebook", T("📒 Журнал", "📒 Журнал"), teacher_gradebook),
                     ("review", T("📝 Тексеру", "📝 Проверка"), teacher_review),
                     ("import", T("⬇ Stepik импорт", "⬇ Импорт Stepik"), teacher_import),
                     ("school", T("🏫 Мектеп", "🏫 Школа"), school_page),
                     ("profile", T("👤 Профиль", "👤 Профиль"), profile)]
            if schools.is_admin(user):
                pages.append(("codes", T("🔐 Мектеп кодтары", "🔐 Коды школ"), admin_codes_page))
        else:
            pages = [("lessons", T("📖 Сабақтар", "📖 Уроки"), student_home),
                     ("grades", T("📊 Бағаларым", "📊 Мои оценки"), student_grades),
                     ("profile", T("👤 Профиль", "👤 Профиль"), profile)]
        codes = [p[0] for p in pages]
        names = {p[0]: p[1] for p in pages}
        if st.session_state.get("nav") not in codes:
            st.session_state["nav"] = codes[0]
        page = st.radio("menu", codes, format_func=lambda c: names[c], label_visibility="collapsed", key="nav")
        st.divider()
        if st.button(T("Шығу", "Выйти"), use_container_width=True):
            logout()
            st.rerun()

    school_banner(user)
    if user["role"] == "student" and not user.get("profile_done"):
        profile(user, onboarding=True)
        return
    next(p[2] for p in pages if p[0] == page)(user)


main()
