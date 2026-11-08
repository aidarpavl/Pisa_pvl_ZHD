"""PISA Жас дарын — оқу платформасы (Streamlit).

Іске қосу:  streamlit run app.py
"""
import io

import pandas as pd
import streamlit as st

import auth
import db
import editor
import grading
import mailer
import player
import repo
import seed
import stepik_import

st.set_page_config(page_title="PISA Жас дарын", page_icon="📘", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
.lesson-row {padding: 6px 10px; border-radius: 8px; margin-bottom: 4px; background: rgba(31,122,77,0.06);}
.big-code {font-size: 2rem; font-weight: 700; letter-spacing: .3rem; color: #1f7a4d;}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def _init():
    db.init_db()
    seed.seed_if_empty()
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


def current_user():
    uid = st.session_state.get("uid")
    return auth.get_user(uid) if uid else None


def do_login(user):
    st.session_state["uid"] = user["id"]


def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.query_params.clear()


def register_student(name, email, class_row):
    """Оқушыны тіркеп, құпиясөзді поштаға жібереді. (user, password|None, хабарлама) қайтарады."""
    password = auth.generate_password()
    uid = auth.create_user(email, name, password, "student")
    repo.enroll(class_row["id"], uid)
    ok, err = mailer.send_email(email, "PISA Жас дарын — логин және құпиясөз",
                                mailer.credentials_email(name, email, password, class_row["name"], APP_URL,
                                                         class_link(class_row["join_code"])))
    return auth.get_user(uid), (None if ok else password), err


# ======================================================================
#                               КІРУ БЕТТЕРІ
# ======================================================================

def login_form(key="login"):
    with st.form(key):
        email = st.text_input("Email (логин)")
        password = st.text_input("Құпиясөз", type="password")
        if st.form_submit_button("Кіру", type="primary", use_container_width=True):
            user = auth.login(email, password)
            if user:
                do_login(user)
                return user
            st.error("Email немесе құпиясөз қате.")
    return None


def forgot_password_form():
    with st.expander("Құпиясөзді ұмыттыңыз ба?"):
        email = st.text_input("Email", key="forgot_email")
        if st.button("Жаңа құпиясөзді поштаға жіберу"):
            user = auth.get_user_by_email(email) if auth.valid_email(email) else None
            if not mailer.is_configured():
                st.warning("Пошта бапталмаған. Мұғаліміңізге хабарласыңыз — ол құпиясөзді жаңарта алады.")
            elif user:
                pw = auth.generate_password()
                ok, err = mailer.send_email(user["email"], "PISA Жас дарын — жаңа құпиясөз",
                                            mailer.reset_email(user["name"], user["email"], pw, APP_URL))
                if ok:
                    auth.set_password(user["id"], pw)
                    st.success("Жаңа құпиясөз поштаңызға жіберілді.")
                else:
                    st.error(f"Хат жіберілмеді: {err}")
            else:
                st.success("Егер бұл email тіркелген болса, жаңа құпиясөз жіберілді.")


def show_credentials_fallback(email, password, err):
    st.warning(f"Хат жіберілмеді ({err}). Логин мен құпиясөзді жазып алыңыз:")
    st.code(f"Логин: {email}\nҚұпиясөз: {password}", language=None)


def join_page(code):
    cls = repo.class_by_code(code)
    st.title("📘 PISA Жас дарын")
    if not cls:
        st.error("Сынып табылмады. Сілтемені тексеріңіз.")
        if st.button("Басты бетке"):
            st.query_params.clear()
            st.rerun()
        return
    st.subheader(f"Сыныпқа қосылу: «{cls['name']}»")
    st.write(f"Курс: **{cls['course_title']}** · Мұғалім: **{cls['teacher_name']}**")
    if not cls["is_open"]:
        st.error("Бұл сыныпқа тіркелу жабық. Мұғаліміңізге хабарласыңыз.")
        return

    user = current_user()
    if user:
        if user["role"] != "student":
            st.info("Сіз мұғалім ретінде кірдіңіз. Сынып сілтемесі оқушыларға арналған.")
            if st.button("Басты бетке"):
                st.query_params.clear()
                st.rerun()
            return
        repo.enroll(cls["id"], user["id"])
        st.success("Сіз сыныпқа қосылдыңыз!")
        if st.button("Сабақтарға өту", type="primary"):
            st.session_state["open_class"] = cls["id"]
            st.query_params.clear()
            st.rerun()
        return

    t1, t2 = st.tabs(["🆕 Тіркелу", "🔑 Аккаунтым бар"])
    with t1:
        st.caption("Аты-жөніңіз бен email-ді жазыңыз. Логин мен құпиясөз поштаңызға келеді.")
        with st.form("join_reg"):
            name = st.text_input("Аты-жөні")
            email = st.text_input("Email")
            sent = st.form_submit_button("Тіркелу", type="primary", use_container_width=True)
        if sent:
            if len(name.strip()) < 3:
                st.error("Аты-жөніңізді толық жазыңыз.")
            elif not auth.valid_email(email):
                st.error("Email дұрыс емес.")
            elif auth.get_user_by_email(email):
                st.error("Бұл email тіркелген. «Аккаунтым бар» бетінен кіріңіз немесе құпиясөзді қалпына келтіріңіз.")
            else:
                user, pw, err = register_student(name, email, cls)
                if pw is None:
                    st.success(f"Тіркелдіңіз! Логин мен құпиясөз **{email}** поштасына жіберілді. "
                               "Хатты тексеріп, «Аккаунтым бар» бетінен кіріңіз (Спам папкасын да қараңыз).")
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
    st.title("📘 PISA Жас дарын")
    st.caption("Функционалдық сауаттылық бойынша оқу платформасы")
    a, b = st.columns([1, 1], gap="large")
    with a:
        st.subheader("Кіру")
        if login_form():
            st.rerun()
        forgot_password_form()
    with b:
        st.subheader("Сыныпқа қосылу")
        code = st.text_input("Сынып коды (мұғалімнен алыңыз)", max_chars=8)
        if st.button("Қосылу", use_container_width=True) and code.strip():
            st.query_params["join"] = code.strip().upper()
            st.rerun()
        st.divider()
        with st.expander("👩‍🏫 Мұғалім ретінде тіркелу"):
            teacher_code_required = bool(secret("TEACHER_CODE"))
            with st.form("teacher_reg"):
                name = st.text_input("Аты-жөні")
                email = st.text_input("Email")
                pw1 = st.text_input("Құпиясөз (кемінде 6 таңба)", type="password")
                tcode = st.text_input("Мұғалім коды (әкімшіден)", type="password") if teacher_code_required else ""
                ok = st.form_submit_button("Тіркелу")
            if ok:
                if teacher_code_required and tcode != secret("TEACHER_CODE"):
                    st.error("Мұғалім коды қате.")
                elif len(name.strip()) < 3 or not auth.valid_email(email) or len(pw1) < 6:
                    st.error("Барлық өрістерді дұрыс толтырыңыз.")
                elif auth.get_user_by_email(email):
                    st.error("Бұл email тіркелген.")
                else:
                    uid = auth.create_user(email, name, pw1, "teacher")
                    do_login(auth.get_user(uid))
                    st.rerun()


# ======================================================================
#                               МҰҒАЛІМ
# ======================================================================

def teacher_courses(user):
    st.header("📚 Курстар және сабақтар")
    all_courses = repo.courses()
    with st.expander("➕ Жаңа курс құру", expanded=not all_courses):
        with st.form("new_course"):
            t = st.text_input("Курс атауы")
            d = st.text_area("Сипаттама", height=80)
            if st.form_submit_button("Құру") and t.strip():
                st.session_state["course_id"] = repo.create_course(t, d, user["id"])
                st.rerun()
    if not all_courses:
        return
    ids = [c["id"] for c in all_courses]
    if st.session_state.get("course_id") not in ids:
        st.session_state["course_id"] = ids[0]
    cid = st.selectbox("Курс", ids, key="course_id", format_func=lambda i: repo.course(i)["title"])
    course = repo.course(cid)

    left, right = st.columns([1, 2.6], gap="large")
    with left:
        with st.expander("Курс параметрлері"):
            nt = st.text_input("Атауы", course["title"], key=f"ct{cid}")
            nd = st.text_area("Сипаттама", course["description"] or "", key=f"cd{cid}")
            if st.button("Сақтау", key=f"cs{cid}"):
                repo.update_course(cid, nt, nd)
                st.rerun()
        st.markdown("**Курс мазмұны**")
        for mi, m in enumerate(repo.modules(cid), start=1):
            with st.expander(f"{mi}. {m['title']}", expanded=True):
                for li, l in enumerate(repo.lessons(m["id"]), start=1):
                    n = len(repo.steps(l["id"]))
                    c1, c2, c3 = st.columns([6, 1, 1])
                    active = st.session_state.get("edit_lesson") == l["id"]
                    if c1.button(f"{'▶ ' if active else ''}{mi}.{li} {l['title']}  ·  {n}",
                                 key=f"open{l['id']}", use_container_width=True):
                        st.session_state["edit_lesson"] = l["id"]
                        st.rerun()
                    if c2.button("↑", key=f"lu{l['id']}"):
                        repo.move("lessons", l["id"], "module_id", -1)
                        st.rerun()
                    if c3.button("↓", key=f"ld{l['id']}"):
                        repo.move("lessons", l["id"], "module_id", 1)
                        st.rerun()
                with st.popover("➕ Сабақ қосу"):
                    lt = st.text_input("Сабақ атауы", key=f"nl{m['id']}")
                    if st.button("Қосу", key=f"nlb{m['id']}") and lt.strip():
                        st.session_state["edit_lesson"] = repo.create_lesson(m["id"], lt)
                        st.rerun()
                with st.popover("⚙ Модуль"):
                    mt = st.text_input("Атауы", m["title"], key=f"mt{m['id']}")
                    a, b, c = st.columns(3)
                    if a.button("Сақтау", key=f"ms{m['id']}"):
                        repo.update_module(m["id"], mt)
                        st.rerun()
                    if b.button("↑", key=f"mu{m['id']}"):
                        repo.move("modules", m["id"], "course_id", -1)
                        st.rerun()
                    if c.button("↓", key=f"md{m['id']}"):
                        repo.move("modules", m["id"], "course_id", 1)
                        st.rerun()
                    if st.checkbox("Жоюды растаймын", key=f"mdc{m['id']}") and \
                            st.button("🗑 Модульді жою", key=f"mdel{m['id']}"):
                        repo.delete_module(m["id"])
                        st.rerun()
        with st.form(f"new_mod{cid}", clear_on_submit=True):
            mt = st.text_input("Жаңа модуль атауы")
            if st.form_submit_button("➕ Модуль қосу") and mt.strip():
                repo.create_module(cid, mt)
                st.rerun()

    with right:
        lid = st.session_state.get("edit_lesson")
        lesson = repo.lesson(lid) if lid else None
        if lesson:
            editor.lesson_editor(lesson)
        else:
            st.info("Сол жақтан сабақты таңдаңыз немесе жаңа сабақ қосыңыз. "
                    "Сабақ ішінде «➕ Жаңа қадам» арқылы мәтін, тест, кестелік, сандық, сәйкестендіру т.б. "
                    "тапсырмалар қосасыз.")


def teacher_classes(user):
    st.header("👥 Сыныптар")
    if not mailer.is_configured():
        st.warning("Пошта (SMTP) бапталмаған — оқушылардың құпиясөздері экранда көрсетіледі. "
                   "README-дегі нұсқау бойынша secrets.toml-ға [smtp] қосыңыз.")
    with st.expander("➕ Жаңа сынып құру", expanded=not repo.teacher_classes(user["id"])):
        with st.form("new_class"):
            name = st.text_input("Сынып атауы (мысалы, 9 «А»)")
            courses = repo.courses()
            cid = st.selectbox("Курс", [c["id"] for c in courses],
                               format_func=lambda i: next(c["title"] for c in courses if c["id"] == i))
            if st.form_submit_button("Құру", type="primary") and name.strip():
                repo.create_class(name, cid, user["id"])
                st.rerun()

    for cls in repo.teacher_classes(user["id"]):
        with st.expander(f"**{cls['name']}** · {cls['course_title']} · оқушылар: {cls['students']}"):
            a, b = st.columns([2, 1])
            with a:
                st.markdown("**Сыныптың сілтемесі** (оқушыларға жіберіңіз):")
                st.code(class_link(cls["join_code"]), language=None)
            with b:
                st.markdown("Сынып коды:")
                st.markdown(f"<div class='big-code'>{cls['join_code']}</div>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            is_open = c1.toggle("Тіркелу ашық", value=bool(cls["is_open"]), key=f"open{cls['id']}")
            if is_open != bool(cls["is_open"]):
                repo.set_class_open(cls["id"], is_open)
                st.rerun()
            if c2.button("🔄 Кодты жаңарту", key=f"regen{cls['id']}"):
                repo.regenerate_code(cls["id"])
                st.rerun()
            if c3.checkbox("Жоюды растаймын", key=f"cdc{cls['id']}") and \
                    c3.button("🗑 Сыныпты жою", key=f"cdel{cls['id']}"):
                repo.delete_class(cls["id"])
                st.rerun()

            st.markdown("##### Оқушылар")
            students = repo.class_students(cls["id"])
            if students:
                st.dataframe(pd.DataFrame(students)[["name", "email", "joined_at"]]
                             .rename(columns={"name": "Аты-жөні", "email": "Email", "joined_at": "Тіркелген"}),
                             hide_index=True, use_container_width=True)
                s_ids = [s["id"] for s in students]
                sel = st.selectbox("Оқушы", s_ids, key=f"sel{cls['id']}",
                                   format_func=lambda i: next(s["name"] for s in students if s["id"] == i))
                x, y = st.columns(2)
                if x.button("🔑 Құпиясөзді жаңартып, поштаға жіберу", key=f"rp{cls['id']}"):
                    stu = auth.get_user(sel)
                    pw = auth.generate_password()
                    auth.set_password(sel, pw)
                    ok, err = mailer.send_email(stu["email"], "PISA Жас дарын — жаңа құпиясөз",
                                                mailer.reset_email(stu["name"], stu["email"], pw, APP_URL))
                    if ok:
                        st.success("Жаңа құпиясөз жіберілді.")
                    else:
                        show_credentials_fallback(stu["email"], pw, err)
                if y.button("➖ Сыныптан шығару", key=f"un{cls['id']}"):
                    repo.unenroll(cls["id"], sel)
                    st.rerun()
            else:
                st.caption("Әзірге оқушы жоқ. Сілтемені жіберіңіз немесе төменде тізіммен қосыңыз.")

            with st.popover("📋 Оқушыларды тізіммен қосу"):
                st.caption("Әр жолға: Аты-жөні; email")
                txt = st.text_area("Тізім", key=f"bulk{cls['id']}", height=160,
                                   placeholder="Ахметов Ержан; erzhan@mail.kz\nСерікова Аружан; aruzhan@gmail.com")
                if st.button("Қосу және хат жіберу", key=f"bulkb{cls['id']}"):
                    report = []
                    for line in txt.splitlines():
                        if ";" not in line:
                            continue
                        name, email = [x.strip() for x in line.split(";", 1)]
                        if not auth.valid_email(email):
                            report.append((name, email, "❌ email қате", ""))
                            continue
                        ex = auth.get_user_by_email(email)
                        if ex:
                            repo.enroll(cls["id"], ex["id"])
                            report.append((name, email, "ℹ️ бұрын тіркелген — сыныпқа қосылды", ""))
                            continue
                        _, pw, err = register_student(name, email, cls)
                        report.append((name, email, "✅ хат жіберілді" if pw is None else f"⚠️ хат кетпеді: {err}",
                                       pw or ""))
                    if report:
                        st.dataframe(pd.DataFrame(report, columns=["Аты-жөні", "Email", "Нәтиже", "Құпиясөз"]),
                                     hide_index=True)


def _class_picker(user, key):
    classes = repo.teacher_classes(user["id"])
    if not classes:
        st.info("Алдымен «Сыныптар» бөлімінде сынып құрыңыз.")
        return None
    cid = st.selectbox("Сынып", [c["id"] for c in classes], key=key,
                       format_func=lambda i: next(f"{c['name']} — {c['course_title']}" for c in classes if c["id"] == i))
    return repo.get_class(cid)


def build_gradebook(cls, detail=False):
    students = repo.class_students(cls["id"])
    lessons = repo.course_lessons(cls["course_id"])
    scores = {}
    for r in repo.class_scores(cls["id"]):
        scores[(r["student_id"], r["step_id"])] = float(r["best"] or 0)
    columns, rows = [], []
    lesson_steps = {l["id"]: [s for s in repo.steps(l["id"]) if s["type"] != "text"] for l in lessons}
    total_max = sum(float(s["points"] or 0) for st_ in lesson_steps.values() for s in st_)
    for stu in students:
        row = {"Оқушы": stu["name"], "Email": stu["email"]}
        total = 0.0
        for i, l in enumerate(lessons, start=1):
            ssum = 0.0
            for j, s in enumerate(lesson_steps[l["id"]], start=1):
                v = scores.get((stu["id"], s["id"]), 0.0)
                ssum += v
                if detail:
                    row[f"{l['title']} · {j}"] = v
            if not detail:
                row[l["title"]] = ssum
            total += ssum
        row["Барлығы"] = round(total, 2)
        row["%"] = round(100 * total / total_max, 1) if total_max else 0
        rows.append(row)
    return pd.DataFrame(rows), total_max, lessons, lesson_steps


def teacher_gradebook(user):
    st.header("📒 Журнал")
    cls = _class_picker(user, "gb_class")
    if not cls:
        return
    detail = st.toggle("Әр тапсырма бойынша толық", key="gb_detail")
    df, total_max, lessons, lesson_steps = build_gradebook(cls, detail)
    if df.empty:
        st.info("Сыныпта оқушы жоқ.")
        return
    st.caption(f"Курстың жалпы балы: **{total_max:g}**. Әр тапсырма бойынша оқушының ең жоғары нәтижесі есептеледі.")
    maxes = {l["title"]: sum(float(s["points"] or 0) for s in lesson_steps[l["id"]]) for l in lessons}
    if not detail:
        st.caption(" · ".join(f"{t}: макс {m:g}" for t, m in maxes.items() if m))
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"%": st.column_config.ProgressColumn("%", min_value=0, max_value=100, format="%.0f%%")})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button("⬇ CSV жүктеу (Excel-де ашылады)", buf.getvalue().encode("utf-8-sig"),
                       file_name=f"jurnal_{cls['name']}.csv", mime="text/csv")


def teacher_review(user):
    st.header("📝 Еркін жауаптарды тексеру")
    cls = _class_picker(user, "rv_class")
    if not cls:
        return
    pend = repo.pending_reviews(cls["id"])
    if not pend:
        st.success("Тексеруді күтетін жауап жоқ 🎉")
        return
    for sub in pend:
        content = db.loads(sub["step_content"], {})
        with st.container(border=True):
            st.markdown(f"**{sub['student_name']}** · {sub['lesson_title']} · {sub['created_at']}")
            with st.expander("Тапсырма"):
                player.show_text(content.get("text", ""))
                if content.get("rubric"):
                    st.info(f"Критерий: {content['rubric']}")
            st.markdown("**Жауабы:**")
            st.write(db.loads(sub["answer"], ""))
            mx = float(sub["step_points"] or 0)
            a, b, c = st.columns([1, 3, 1])
            score = a.number_input(f"Балл (0–{mx:g})", 0.0, mx, 0.0, 0.5, key=f"rs{sub['id']}")
            comment = b.text_input("Пікір", key=f"rc{sub['id']}")
            if c.button("Бағалау", key=f"rb{sub['id']}", type="primary"):
                repo.grade_submission(sub["id"], score, mx, comment)
                st.rerun()


def teacher_import(user):
    st.header("⬇ Stepik-тен импорттау")
    st.markdown(stepik_import.__doc__)
    courses = repo.courses()
    cid = st.selectbox("Курс", [c["id"] for c in courses],
                       format_func=lambda i: next(c["title"] for c in courses if c["id"] == i), key="imp_course")
    lessons = [l for l in repo.course_lessons(cid) if l.get("stepik_lesson_id")]
    a, b = st.columns(2)
    client_id = a.text_input("Client ID", value=secret("STEPIK_CLIENT_ID", "") or "")
    client_secret = b.text_input("Client Secret", type="password", value=secret("STEPIK_CLIENT_SECRET", "") or "")
    chosen = st.multiselect("Сабақтар (Stepik ID жазылғандар)", [l["id"] for l in lessons],
                            default=[l["id"] for l in lessons if not repo.steps(l["id"])],
                            format_func=lambda i: next(f"{l['title']} (#{l['stepik_lesson_id']}) · қадам: "
                                                       f"{len(repo.steps(l['id']))}" for l in lessons if l["id"] == i))
    replace = st.checkbox("Бар қадамдарды ауыстыру (әйтпесе соңына қосылады)")
    if st.button("Импорттау", type="primary", disabled=not (client_id and client_secret and chosen)):
        try:
            token = stepik_import.get_token(client_id, client_secret)
        except Exception as e:  # noqa: BLE001
            st.error(f"Stepik токенін алу мүмкін болмады: {e}")
            return
        prog = st.progress(0.0)
        for n, lid in enumerate(chosen, start=1):
            l = repo.lesson(lid)
            try:
                title, steps, warnings = stepik_import.fetch_lesson(l["stepik_lesson_id"], token)
                if replace:
                    for s in repo.steps(lid):
                        repo.delete_step(s["id"])
                for t, content, pts in steps:
                    repo.create_step(lid, t, content, pts)
                st.success(f"{l['title']}: {len(steps)} қадам импортталды")
                for w in warnings:
                    st.caption(f"⚠️ {w}")
            except Exception as e:  # noqa: BLE001
                st.error(f"{l['title']}: қате — {e}")
            prog.progress(n / len(chosen))


# ======================================================================
#                               ОҚУШЫ
# ======================================================================

def student_home(user):
    classes = repo.student_classes(user["id"])
    if not classes:
        st.header("Сәлем, " + user["name"].split()[0] + "!")
        st.info("Сіз әлі ешбір сыныпқа қосылмағансыз. Мұғаліміңізден сынып сілтемесін не кодын алыңыз.")
        code = st.text_input("Сынып коды")
        if st.button("Қосылу") and code.strip():
            st.query_params["join"] = code.strip().upper()
            st.rerun()
        return
    ids = [c["id"] for c in classes]
    if st.session_state.get("open_class") not in ids:
        st.session_state["open_class"] = ids[0]
    cid = st.selectbox("Сынып", ids, key="open_class",
                       format_func=lambda i: next(f"{c['name']} — {c['course_title']}" for c in classes if c["id"] == i))
    cls = repo.get_class(cid)
    lid = st.session_state.get("open_lesson")
    lesson = repo.lesson(lid) if lid else None
    if lesson:
        if st.button("← Курс мазмұнына оралу"):
            st.session_state.pop("open_lesson")
            st.rerun()
        st.subheader(lesson["title"])
        player.render_lesson(lesson, user["id"], cls["id"])
        return
    syllabus(user, cls)


def syllabus(user, cls):
    course = repo.course(cls["course_id"])
    st.header(course["title"])
    if course.get("description"):
        st.caption(course["description"])
    scores = repo.best_scores(user["id"], cls["id"])
    total_e = total_m = 0.0
    blocks = []
    for mi, m in enumerate(repo.modules(course["id"]), start=1):
        rows = []
        me = mm = 0.0
        for li, l in enumerate(repo.lessons(m["id"]), start=1):
            steps = [s for s in repo.steps(l["id"]) if s["type"] != "text"]
            mx = sum(float(s["points"] or 0) for s in steps)
            earned = sum(scores.get(s["id"], (0, None))[0] for s in steps)
            rows.append((mi, li, l, earned, mx))
            me += earned
            mm += mx
        blocks.append((mi, m, rows, me, mm))
        total_e += me
        total_m += mm
    st.progress(total_e / total_m if total_m else 0.0, text=f"Жалпы прогресс: {total_e:g} / {total_m:g} балл")
    st.markdown("### Курс бағдарламасы")
    for mi, m, rows, me, mm in blocks:
        with st.container(border=True):
            st.markdown(f"**{mi}. {m['title']}** — {me:g}/{mm:g}")
            for _, li, l, earned, mx in rows:
                a, b = st.columns([5, 1])
                done = mx and earned >= mx
                if a.button(f"{'✅' if done else '📄'} {mi}.{li} {l['title']}", key=f"ol{l['id']}",
                            use_container_width=True):
                    st.session_state["open_lesson"] = l["id"]
                    st.rerun()
                b.markdown(f"**{earned:g} / {mx:g}**")


def student_grades(user):
    st.header("📊 Менің бағаларым")
    for cls in repo.student_classes(user["id"]):
        st.subheader(f"{cls['name']} — {cls['course_title']}")
        scores = repo.best_scores(user["id"], cls["id"])
        rows = []
        for l in repo.course_lessons(cls["course_id"]):
            steps = [s for s in repo.steps(l["id"]) if s["type"] != "text"]
            mx = sum(float(s["points"] or 0) for s in steps)
            e = sum(scores.get(s["id"], (0, None))[0] for s in steps)
            pend = sum(1 for s in steps if scores.get(s["id"], (0, None))[1] == "pending")
            rows.append({"Модуль": l["module_title"], "Сабақ": l["title"], "Балл": e, "Макс": mx,
                         "Тексерілуде": pend or ""})
        df = pd.DataFrame(rows)
        if not df.empty:
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.metric("Барлығы", f"{df['Балл'].sum():g} / {df['Макс'].sum():g}")


def profile(user):
    st.header("👤 Профиль")
    st.write(f"**{user['name']}** · {user['email']} · "
             f"{'Мұғалім' if user['role'] == 'teacher' else 'Оқушы'}")
    with st.form("chpw"):
        old = st.text_input("Қазіргі құпиясөз", type="password")
        new = st.text_input("Жаңа құпиясөз (кемінде 6 таңба)", type="password")
        if st.form_submit_button("Құпиясөзді өзгерту"):
            if not auth.verify_password(old, user["password_hash"]):
                st.error("Қазіргі құпиясөз қате.")
            elif len(new) < 6:
                st.error("Жаңа құпиясөз тым қысқа.")
            else:
                auth.set_password(user["id"], new)
                st.success("Өзгертілді.")


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

    with st.sidebar:
        st.markdown("## 📘 PISA Жас дарын")
        st.caption(f"{user['name']} · {'мұғалім' if user['role'] == 'teacher' else 'оқушы'}")
        if user["role"] == "teacher":
            pages = {"📚 Курстар": teacher_courses, "👥 Сыныптар": teacher_classes, "📒 Журнал": teacher_gradebook,
                     "📝 Тексеру": teacher_review, "⬇ Stepik импорт": teacher_import, "👤 Профиль": profile}
        else:
            pages = {"📖 Сабақтар": student_home, "📊 Бағаларым": student_grades, "👤 Профиль": profile}
        page = st.radio("Мәзір", list(pages.keys()), label_visibility="collapsed", key="nav")
        st.divider()
        if st.button("Шығу", use_container_width=True):
            logout()
            st.rerun()
    pages[page](user)


main()
