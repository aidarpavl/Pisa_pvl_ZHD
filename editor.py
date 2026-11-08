"""Мұғалімнің сабақ редакторы (Stepik-тің edit-lesson бетіне ұқсас)."""
import base64

import pandas as pd
import streamlit as st

import grading
import player
import repo


def _image_inserter(text_key, label="🖼 Сурет қосу (PISA мәтіндеріндегі график/кесте суреті)"):
    """Сурет жүктеп, мәтінге <img> ретінде қосу. text_area-дан БҰРЫН шақырылуы керек."""
    with st.expander(label):
        f = st.file_uploader("Сурет", type=["png", "jpg", "jpeg", "gif", "webp"], key=f"{text_key}_img")
        url = st.text_input("немесе сурет сілтемесі (URL)", key=f"{text_key}_url")
        width = st.slider("Ені (px)", 200, 900, 600, key=f"{text_key}_w")
        if st.button("Мәтінге қосу", key=f"{text_key}_addimg"):
            src = None
            if f is not None:
                if f.size > 1_500_000:
                    st.error("Сурет 1.5 МБ-тан аспауы керек.")
                else:
                    src = f"data:{f.type};base64,{base64.b64encode(f.getvalue()).decode()}"
            elif url.strip():
                src = url.strip()
            if src:
                st.session_state[text_key] = (st.session_state.get(text_key, "") +
                                              f'\n\n<img src="{src}" width="{width}">\n\n')
                st.rerun()


def _rich_text(label, key, value, height=220, help_text=None):
    if key not in st.session_state:
        st.session_state[key] = value or ""
    _image_inserter(key)
    return st.text_area(label, key=key, height=height,
                        help=help_text or "Markdown және HTML қолдауы бар: **қалың**, *курсив*, кесте, <br> т.б.")


def edit_step(s):
    """Бір қадамды өңдеу формасы."""
    sid, t = s["id"], s["type"]
    c = dict(s["content"])
    p = f"ed{sid}"
    st.markdown(f"#### {grading.STEP_TYPES.get(t, t)}")

    if t == "fill_blanks":
        text = _rich_text("Мәтін (бос орындарды [[жауап]] немесе [[жауап1|жауап2]] деп белгілеңіз)",
                          f"{p}_text", c.get("text", ""), 260)
        found = grading.blanks(text)
        st.caption(f"Табылған бос орындар: {len(found)} — " + "; ".join(" / ".join(a) for a in found))
    else:
        text = _rich_text("Тапсырма шарты / мәтін" if t != "text" else "Теориялық мәтін",
                          f"{p}_text", c.get("text", ""), 320 if t == "text" else 220)
    c["text"] = text

    if t == "choice":
        df = pd.DataFrame(c.get("options", []) or [{"text": "", "correct": False}])
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_opts",
                            column_config={"text": st.column_config.TextColumn("Жауап нұсқасы", width="large"),
                                           "correct": st.column_config.CheckboxColumn("Дұрыс")})
        c["options"] = [{"text": str(r["text"] or ""), "correct": bool(r["correct"])}
                        for _, r in df.iterrows() if str(r["text"] or "").strip()]
        a, b = st.columns(2)
        c["multiple"] = a.checkbox("Бірнеше дұрыс жауап", value=c.get("multiple", False), key=f"{p}_mul")
        c["shuffle"] = b.checkbox("Нұсқаларды араластыру", value=c.get("shuffle", True), key=f"{p}_shuf")

    elif t == "table":
        cols_txt = st.text_input("Бағандар (үтір арқылы)", ", ".join(c.get("columns", ["Иә", "Жоқ"])), key=f"{p}_cols")
        cols = [x.strip() for x in cols_txt.split(",") if x.strip()] or ["Иә", "Жоқ"]
        rows = c.get("rows", []) or [{"text": "", "correct": 0}]
        df = pd.DataFrame([{"text": r.get("text", ""),
                            "correct": cols[r.get("correct", 0)] if r.get("correct", 0) < len(cols) else cols[0]}
                           for r in rows])
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_rows",
                            column_config={"text": st.column_config.TextColumn("Тұжырым", width="large"),
                                           "correct": st.column_config.SelectboxColumn("Дұрыс жауап", options=cols)})
        c["columns"] = cols
        c["rows"] = [{"text": str(r["text"] or ""), "correct": cols.index(r["correct"]) if r["correct"] in cols else 0}
                     for _, r in df.iterrows() if str(r["text"] or "").strip()]

    elif t == "number":
        a, b = st.columns(2)
        c["answer"] = a.number_input("Дұрыс жауап", value=float(c.get("answer", 0)), format="%.4f", key=f"{p}_ans")
        c["tolerance"] = b.number_input("Рұқсат етілген қателік (±)", value=float(c.get("tolerance", 0)),
                                        min_value=0.0, format="%.4f", key=f"{p}_tol")

    elif t == "string":
        ans = st.text_area("Дұрыс жауаптар (әр жолға біреуден)", "\n".join(c.get("answers", [])), key=f"{p}_answers")
        c["answers"] = [x.strip() for x in ans.splitlines() if x.strip()]
        a, b = st.columns(2)
        c["case_sensitive"] = a.checkbox("Бас/кіші әріпті ескеру", c.get("case_sensitive", False), key=f"{p}_cs")
        c["regex"] = b.checkbox("Тұрақты өрнек (regex)", c.get("regex", False), key=f"{p}_re")

    elif t == "fill_blanks":
        c["case_sensitive"] = st.checkbox("Бас/кіші әріпті ескеру", c.get("case_sensitive", False), key=f"{p}_cs")

    elif t == "matching":
        df = pd.DataFrame(c.get("pairs", []) or [{"left": "", "right": ""}])
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_pairs",
                            column_config={"left": st.column_config.TextColumn("Сол жақ"),
                                           "right": st.column_config.TextColumn("Сәйкес оң жақ")})
        c["pairs"] = [{"left": str(r["left"] or ""), "right": str(r["right"] or "")}
                      for _, r in df.iterrows() if str(r["left"] or "").strip()]

    elif t == "sorting":
        df = pd.DataFrame({"item": c.get("items", []) or [""]})
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_items",
                            column_config={"item": st.column_config.TextColumn("Элемент (ДҰРЫС ретпен жазыңыз)")})
        c["items"] = [str(x) for x in df["item"].tolist() if str(x or "").strip()]

    elif t == "free_text":
        c["rubric"] = st.text_area("Бағалау критерийі (тек мұғалімге көрінеді)", c.get("rubric", ""), key=f"{p}_rub")

    points = s.get("points", 1)
    if t != "text":
        st.markdown("**Бағалау**")
        a, b, d = st.columns(3)
        points = a.number_input("Балл", min_value=0.0, value=float(points or 1), step=0.5, key=f"{p}_pts")
        c["max_attempts"] = int(b.number_input("Әрекет саны (0 = шексіз)", min_value=0,
                                               value=int(c.get("max_attempts", 0)), key=f"{p}_att"))
        c["partial"] = d.checkbox("Жартылай балл беру", c.get("partial", True), key=f"{p}_part",
                                  help="Мысалы, 4 тұжырымның 3-і дұрыс болса — 75% балл")
        c["explanation"] = st.text_area("Түсіндірме (шешкеннен кейін көрсетіледі)", c.get("explanation", ""),
                                        key=f"{p}_expl", height=80)
    return c, points


def lesson_editor(lesson):
    st.subheader(f"✏️ {lesson['title']}")
    with st.expander("Сабақ параметрлері"):
        title = st.text_input("Сабақ атауы", lesson["title"], key=f"lt{lesson['id']}")
        sid = st.text_input("Stepik сабақ ID (импорт үшін)", str(lesson.get("stepik_lesson_id") or ""),
                            key=f"ls{lesson['id']}")
        a, b = st.columns(2)
        if a.button("Сақтау", key=f"lsave{lesson['id']}"):
            repo.update_lesson(lesson["id"], title, int(sid) if sid.strip().isdigit() else None)
            st.success("Сақталды")
            st.rerun()
        if b.button("🗑 Сабақты жою", key=f"ldel{lesson['id']}"):
            st.session_state[f"confirm_ldel{lesson['id']}"] = True
        if st.session_state.get(f"confirm_ldel{lesson['id']}"):
            st.warning("Сабақ және оның барлық тапсырмалары мен жауаптары жойылады.")
            if st.button("Иә, жою", key=f"ldel2{lesson['id']}", type="primary"):
                repo.delete_lesson(lesson["id"])
                st.session_state.pop("edit_lesson", None)
                st.rerun()

    steps = repo.steps(lesson["id"])
    nav_key = f"edstep_{lesson['id']}"
    apply_goto(lesson["id"])
    labels = [f"{i + 1}. {grading.STEP_TYPES[s['type']].split()[0]}" for i, s in enumerate(steps)]
    options = list(range(len(steps))) + ["new"]
    if st.session_state.get(nav_key) not in options:
        st.session_state[nav_key] = 0 if steps else "new"
    cur = st.radio("Қадамдар", options, horizontal=True, key=nav_key,
                   format_func=lambda i: "➕ Жаңа қадам" if i == "new" else labels[i])
    st.caption(f"Сабақтың жалпы балы: **{repo.lesson_max(lesson['id']):g}**")
    st.divider()

    if cur == "new":
        st.markdown("### Жаңа қадам қосу")
        cols = st.columns(3)
        for i, (code, name) in enumerate(grading.STEP_TYPES.items()):
            if cols[i % 3].button(name, key=f"add_{lesson['id']}_{code}", use_container_width=True):
                repo.create_step(lesson["id"], code, grading.default_content(code), 1)
                st.session_state[f"{nav_key}_goto"] = len(steps)
                st.rerun()
        return

    s = steps[cur]
    tab_edit, tab_prev = st.tabs(["Өңдеу", "👁 Алдын ала қарау"])
    with tab_edit:
        content, points = edit_step(s)
        st.divider()
        a, b, d, e = st.columns(4)
        if a.button("💾 Сақтау", type="primary", key=f"save{s['id']}", use_container_width=True):
            problems = validate(s["type"], content)
            if problems:
                st.error(" ".join(problems))
            else:
                repo.update_step(s["id"], content, points)
                st.success("Сақталды ✓")
        if b.button("⬆ Жоғары", key=f"up{s['id']}", use_container_width=True, disabled=cur == 0):
            repo.move("steps", s["id"], "lesson_id", -1)
            st.session_state[f"{nav_key}_goto"] = cur - 1
            st.rerun()
        if d.button("⬇ Төмен", key=f"down{s['id']}", use_container_width=True, disabled=cur == len(steps) - 1):
            repo.move("steps", s["id"], "lesson_id", 1)
            st.session_state[f"{nav_key}_goto"] = cur + 1
            st.rerun()
        if e.button("🗑 Жою", key=f"del{s['id']}", use_container_width=True):
            repo.delete_step(s["id"])
            st.session_state[f"{nav_key}_goto"] = max(cur - 1, 0)
            st.rerun()
    with tab_prev:
        st.caption("Оқушы көретін түрі. Жауап журналға жазылмайды. Өзгерістерді көру үшін алдымен сақтаңыз.")
        player.render_step(repo.step(s["id"]), preview=True)


def apply_goto(lesson_id):
    """Қадам қосу/жылжытудан кейін керекті қадамға өту (radio жасалмай тұрып шақырылады)."""
    nav_key = f"edstep_{lesson_id}"
    goto = st.session_state.pop(f"{nav_key}_goto", None)
    if goto is not None:
        st.session_state[nav_key] = goto


def validate(t, c):
    errs = []
    if t == "choice":
        if len(c.get("options", [])) < 2:
            errs.append("Кемінде 2 жауап нұсқасы керек.")
        if not any(o["correct"] for o in c.get("options", [])):
            errs.append("Кемінде бір дұрыс жауапты белгілеңіз.")
    if t == "table" and not c.get("rows"):
        errs.append("Кемінде бір тұжырым қосыңыз.")
    if t == "string" and not c.get("answers"):
        errs.append("Дұрыс жауапты жазыңыз.")
    if t == "fill_blanks" and not grading.blanks(c.get("text", "")):
        errs.append("Мәтінде [[...]] түріндегі бос орын жоқ.")
    if t == "matching" and len(c.get("pairs", [])) < 2:
        errs.append("Кемінде 2 жұп керек.")
    if t == "sorting" and len(c.get("items", [])) < 2:
        errs.append("Кемінде 2 элемент керек.")
    return errs
