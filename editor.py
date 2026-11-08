"""Мұғалімнің сабақ редакторы (Stepik-тің edit-lesson бетіне ұқсас), екі тілде."""
import base64

import pandas as pd
import streamlit as st

import grading
import player
import repo
from i18n import LANGS, T, localize, set_lang_content

TYPE_NAMES = {
    "text": ("📄 Мәтін (теория)", "📄 Текст (теория)"),
    "choice": ("☑️ Тест (бір/бірнеше жауап)", "☑️ Тест (один/несколько ответов)"),
    "table": ("▦ Кестелік тапсырма (Иә/Жоқ)", "▦ Табличная задача (Да/Нет)"),
    "number": ("🔢 Сандық тапсырма", "🔢 Числовая задача"),
    "string": ("🔤 Мәтіндік жауап", "🔤 Текстовый ответ"),
    "fill_blanks": ("✏️ Бос орындарды толтыру", "✏️ Заполнить пропуски"),
    "matching": ("🔗 Сәйкестендіру", "🔗 Сопоставление"),
    "sorting": ("↕️ Ретке келтіру", "↕️ Сортировка"),
    "free_text": ("📝 Еркін жауап (мұғалім тексереді)", "📝 Свободный ответ (проверяет учитель)"),
}


def type_name(t):
    return T(*TYPE_NAMES.get(t, (t, t)))


def _image_inserter(text_key):
    """Сурет жүктеп, мәтінге <img> ретінде қосу. text_area-дан БҰРЫН шақырылуы керек."""
    with st.expander(T("🖼 Сурет қосу", "🖼 Добавить изображение")):
        f = st.file_uploader(T("Сурет", "Изображение"), type=["png", "jpg", "jpeg", "gif", "webp"], key=f"{text_key}_img")
        url = st.text_input(T("немесе сурет сілтемесі (URL)", "или ссылка на изображение (URL)"), key=f"{text_key}_url")
        width = st.slider(T("Ені (px)", "Ширина (px)"), 200, 900, 600, key=f"{text_key}_w")
        if st.button(T("Мәтінге қосу", "Вставить в текст"), key=f"{text_key}_addimg"):
            src = None
            if f is not None:
                if f.size > 1_500_000:
                    st.error(T("Сурет 1.5 МБ-тан аспауы керек.", "Изображение должно быть не больше 1,5 МБ."))
                else:
                    src = f"data:{f.type};base64,{base64.b64encode(f.getvalue()).decode()}"
            elif url.strip():
                src = url.strip()
            if src:
                st.session_state[text_key] = (st.session_state.get(text_key, "") +
                                              f'\n\n<img src="{src}" width="{width}" style="max-width:100%">\n\n')
                st.rerun()


def _rich_text(label, key, value, height=220):
    if key not in st.session_state:
        st.session_state[key] = value or ""
    _image_inserter(key)
    return st.text_area(label, key=key, height=height,
                        help=T("Markdown және HTML қолдауы бар: **қалың**, *курсив*, кесте, <img> т.б.",
                               "Поддерживаются Markdown и HTML: **жирный**, *курсив*, таблицы, <img> и т.д."))


def edit_step(s, lng):
    """Бір қадамды өңдеу формасы (lng тіліндегі мазмұн)."""
    sid, t = s["id"], s["type"]
    c = localize(s["content"], lng)
    p = f"ed{sid}_{lng}"
    st.markdown(f"#### {type_name(t)} · {LANGS[lng]}")

    if t == "fill_blanks":
        text = _rich_text(T("Мәтін (бос орындарды [[жауап]] немесе [[жауап1|жауап2]] деп белгілеңіз)",
                            "Текст (пропуски отмечайте [[ответ]] или [[ответ1|ответ2]])"), f"{p}_text", c.get("text", ""), 260)
        found = grading.blanks(text)
        st.caption(T("Табылған бос орындар", "Найдено пропусков") + f": {len(found)} — " +
                   "; ".join(" / ".join(a) for a in found))
    else:
        text = _rich_text(T("Теориялық мәтін", "Теоретический текст") if t == "text"
                          else T("Тапсырма шарты / мәтін", "Условие задания / текст"),
                          f"{p}_text", c.get("text", ""), 320 if t == "text" else 220)
    c["text"] = text

    if t == "choice":
        df = pd.DataFrame(c.get("options", []) or [{"text": "", "correct": False}])
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_opts",
                            column_config={"text": st.column_config.TextColumn(T("Жауап нұсқасы", "Вариант ответа"),
                                                                               width="large"),
                                           "correct": st.column_config.CheckboxColumn(T("Дұрыс", "Верный"))})
        c["options"] = [{"text": str(r["text"] or ""), "correct": bool(r["correct"])}
                        for _, r in df.iterrows() if str(r["text"] or "").strip()]
        a, b = st.columns(2)
        c["multiple"] = a.checkbox(T("Бірнеше дұрыс жауап", "Несколько правильных ответов"),
                                   value=c.get("multiple", False), key=f"{p}_mul")
        c["shuffle"] = b.checkbox(T("Нұсқаларды араластыру", "Перемешивать варианты"),
                                  value=c.get("shuffle", True), key=f"{p}_shuf")

    elif t == "table":
        cols_txt = st.text_input(T("Бағандар (үтір арқылы)", "Столбцы (через запятую)"),
                                 ", ".join(c.get("columns", ["Иә", "Жоқ"])), key=f"{p}_cols")
        cols = [x.strip() for x in cols_txt.split(",") if x.strip()] or ["Иә", "Жоқ"]
        rows = c.get("rows", []) or [{"text": "", "correct": 0}]
        df = pd.DataFrame([{"text": r.get("text", ""),
                            "correct": cols[r.get("correct", 0)] if r.get("correct", 0) < len(cols) else cols[0]}
                           for r in rows])
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_rows",
                            column_config={"text": st.column_config.TextColumn(T("Тұжырым", "Утверждение"), width="large"),
                                           "correct": st.column_config.SelectboxColumn(T("Дұрыс жауап", "Верный ответ"),
                                                                                       options=cols)})
        c["columns"] = cols
        c["rows"] = [{"text": str(r["text"] or ""), "correct": cols.index(r["correct"]) if r["correct"] in cols else 0}
                     for _, r in df.iterrows() if str(r["text"] or "").strip()]

    elif t == "number":
        a, b = st.columns(2)
        c["answer"] = a.number_input(T("Дұрыс жауап", "Правильный ответ"), value=float(c.get("answer", 0)),
                                     format="%.4f", key=f"{p}_ans")
        c["tolerance"] = b.number_input(T("Рұқсат етілген қателік (±)", "Допустимая погрешность (±)"),
                                        value=float(c.get("tolerance", 0)), min_value=0.0, format="%.4f", key=f"{p}_tol")

    elif t == "string":
        ans = st.text_area(T("Дұрыс жауаптар (әр жолға біреуден)", "Правильные ответы (по одному в строке)"),
                           "\n".join(c.get("answers", [])), key=f"{p}_answers")
        c["answers"] = [x.strip() for x in ans.splitlines() if x.strip()]
        a, b = st.columns(2)
        c["case_sensitive"] = a.checkbox(T("Бас/кіші әріпті ескеру", "Учитывать регистр"),
                                         c.get("case_sensitive", False), key=f"{p}_cs")
        c["regex"] = b.checkbox(T("Тұрақты өрнек (regex)", "Регулярное выражение"), c.get("regex", False), key=f"{p}_re")

    elif t == "fill_blanks":
        c["case_sensitive"] = st.checkbox(T("Бас/кіші әріпті ескеру", "Учитывать регистр"),
                                          c.get("case_sensitive", False), key=f"{p}_cs")

    elif t == "matching":
        df = pd.DataFrame(c.get("pairs", []) or [{"left": "", "right": ""}])
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_pairs",
                            column_config={"left": st.column_config.TextColumn(T("Сол жақ", "Левая часть")),
                                           "right": st.column_config.TextColumn(T("Сәйкес оң жақ", "Правая часть"))})
        c["pairs"] = [{"left": str(r["left"] or ""), "right": str(r["right"] or "")}
                      for _, r in df.iterrows() if str(r["left"] or "").strip()]

    elif t == "sorting":
        df = pd.DataFrame({"item": c.get("items", []) or [""]})
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"{p}_items",
                            column_config={"item": st.column_config.TextColumn(
                                T("Элемент (ДҰРЫС ретпен жазыңыз)", "Элемент (в ПРАВИЛЬНОМ порядке)"))})
        c["items"] = [str(x) for x in df["item"].tolist() if str(x or "").strip()]

    elif t == "free_text":
        c["rubric"] = st.text_area(T("Бағалау критерийі (тек мұғалімге көрінеді)", "Критерии оценивания (видит только учитель)"),
                                   c.get("rubric", ""), key=f"{p}_rub")

    points = s.get("points", 1)
    if t != "text":
        st.markdown(T("**Бағалау** (екі тілге ортақ)", "**Оценивание** (общее для обоих языков)"))
        a, b, d = st.columns(3)
        points = a.number_input(T("Балл", "Балл"), min_value=0.0, value=float(points or 1), step=0.5, key=f"{p}_pts")
        c["max_attempts"] = int(b.number_input(T("Әрекет саны (0 = шексіз)", "Число попыток (0 = без ограничений)"),
                                               min_value=0, value=int(c.get("max_attempts", 0)), key=f"{p}_att"))
        c["partial"] = d.checkbox(T("Жартылай балл беру", "Частичный балл"), c.get("partial", True), key=f"{p}_part")
        c["explanation"] = st.text_area(T("Түсіндірме (шешкеннен кейін көрсетіледі)", "Пояснение (показывается после решения)"),
                                        c.get("explanation", ""), key=f"{p}_expl", height=80)
    return set_lang_content(s["content"], lng, c), points, c


def lesson_editor(lesson):
    lid = lesson["id"]
    st.subheader(f"✏️ {lesson['title']}")
    if lesson.get("title_ru"):
        st.caption(lesson["title_ru"])
    with st.expander(T("Сабақ параметрлері", "Параметры урока")):
        title = st.text_input(T("Атауы (қазақша)", "Название (каз.)"), lesson["title"], key=f"lt{lid}")
        title_ru = st.text_input(T("Атауы (орысша)", "Название (рус.)"), lesson.get("title_ru") or "", key=f"ltr{lid}")
        sid = st.text_input(T("Stepik сабақ ID (импорт үшін)", "ID урока Stepik (для импорта)"),
                            str(lesson.get("stepik_lesson_id") or ""), key=f"ls{lid}")
        a, b = st.columns(2)
        if a.button(T("Сақтау", "Сохранить"), key=f"lsave{lid}"):
            repo.update_lesson(lid, title, int(sid) if sid.strip().isdigit() else None, title_ru or None)
            st.rerun()
        if b.button(T("🗑 Сабақты жою", "🗑 Удалить урок"), key=f"ldel{lid}"):
            st.session_state[f"confirm_ldel{lid}"] = True
        if st.session_state.get(f"confirm_ldel{lid}"):
            st.warning(T("Сабақ және оның барлық тапсырмалары мен жауаптары жойылады.",
                         "Урок и все его задания и ответы будут удалены."))
            if st.button(T("Иә, жою", "Да, удалить"), key=f"ldel2{lid}", type="primary"):
                repo.delete_lesson(lid)
                st.session_state.pop("edit_lesson", None)
                st.rerun()

    steps = repo.steps(lid)
    nav_key = f"edstep_{lid}"
    apply_goto(lid)
    labels = [f"{i + 1}. {type_name(s['type']).split()[0]}" for i, s in enumerate(steps)]
    options = list(range(len(steps))) + ["new"]
    if st.session_state.get(nav_key) not in options:
        st.session_state[nav_key] = 0 if steps else "new"
    cur = st.radio(T("Қадамдар", "Шаги"), options, horizontal=True, key=nav_key,
                   format_func=lambda i: T("➕ Жаңа қадам", "➕ Новый шаг") if i == "new" else labels[i])
    st.caption(T("Сабақтың жалпы балы", "Общий балл урока") + f": **{repo.lesson_max(lid):g}**")
    st.divider()

    if cur == "new":
        st.markdown(T("### Жаңа қадам қосу", "### Добавить новый шаг"))
        cols = st.columns(3)
        for i, code in enumerate(grading.STEP_TYPES):
            if cols[i % 3].button(type_name(code), key=f"add_{lid}_{code}", use_container_width=True):
                repo.create_step(lid, code, grading.default_content(code), 1)
                st.session_state[f"{nav_key}_goto"] = len(steps)
                st.rerun()
        return

    s = steps[cur]
    lng = st.radio(T("Мазмұн тілі", "Язык содержания"), list(LANGS), format_func=lambda k: LANGS[k],
                   horizontal=True, key=f"edlang_{s['id']}")
    tab_edit, tab_prev = st.tabs([T("Өңдеу", "Редактирование"), T("👁 Алдын ала қарау", "👁 Предпросмотр")])
    with tab_edit:
        content, points, view = edit_step(s, lng)
        st.divider()
        a, b, d, e = st.columns(4)
        if a.button(T("💾 Сақтау", "💾 Сохранить"), type="primary", key=f"save{s['id']}_{lng}", use_container_width=True):
            problems = validate(s["type"], view)
            if problems:
                st.error(" ".join(problems))
            else:
                repo.update_step(s["id"], content, points)
                st.success(T("Сақталды ✓", "Сохранено ✓"))
        if b.button(T("⬆ Жоғары", "⬆ Вверх"), key=f"up{s['id']}", use_container_width=True, disabled=cur == 0):
            repo.move("steps", s["id"], "lesson_id", -1)
            st.session_state[f"{nav_key}_goto"] = cur - 1
            st.rerun()
        if d.button(T("⬇ Төмен", "⬇ Вниз"), key=f"down{s['id']}", use_container_width=True,
                    disabled=cur == len(steps) - 1):
            repo.move("steps", s["id"], "lesson_id", 1)
            st.session_state[f"{nav_key}_goto"] = cur + 1
            st.rerun()
        if e.button(T("🗑 Жою", "🗑 Удалить"), key=f"del{s['id']}", use_container_width=True):
            repo.delete_step(s["id"])
            st.session_state[f"{nav_key}_goto"] = max(cur - 1, 0)
            st.rerun()
    with tab_prev:
        st.caption(T("Оқушы көретін түрі (жоғарғы тіл ауыстырғышы бойынша). Өзгерістерді көру үшін алдымен сақтаңыз.",
                     "Так видит ученик (по переключателю языка). Чтобы увидеть изменения, сначала сохраните."))
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
            errs.append(T("Кемінде 2 жауап нұсқасы керек.", "Нужно минимум 2 варианта ответа."))
        if not any(o["correct"] for o in c.get("options", [])):
            errs.append(T("Кемінде бір дұрыс жауапты белгілеңіз.", "Отметьте хотя бы один правильный ответ."))
    if t == "table" and not c.get("rows"):
        errs.append(T("Кемінде бір тұжырым қосыңыз.", "Добавьте хотя бы одно утверждение."))
    if t == "string" and not c.get("answers"):
        errs.append(T("Дұрыс жауапты жазыңыз.", "Укажите правильный ответ."))
    if t == "fill_blanks" and not grading.blanks(c.get("text", "")):
        errs.append(T("Мәтінде [[...]] түріндегі бос орын жоқ.", "В тексте нет пропусков вида [[...]]."))
    if t == "matching" and len(c.get("pairs", [])) < 2:
        errs.append(T("Кемінде 2 жұп керек.", "Нужно минимум 2 пары."))
    if t == "sorting" and len(c.get("items", [])) < 2:
        errs.append(T("Кемінде 2 элемент керек.", "Нужно минимум 2 элемента."))
    return errs
