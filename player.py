"""Оқушы тапсырманы орындайтын бет (қадамдарды көрсету және жауапты тексеру)."""
import random

import streamlit as st

import db
import grading
import repo
from i18n import T, lang, localize

STATUS_ICON = {"correct": "✅", "partial": "🟡", "wrong": "❌", "pending": "⏳", None: "⚪"}


def show_text(text):
    if text:
        st.markdown(text, unsafe_allow_html=True)


def _shuffled(items, seed):
    idx = list(range(len(items)))
    random.Random(seed).shuffle(idx)
    return idx


def render_inputs(t, c, key, seed):
    """Тапсырма түріне қарай енгізу виджеттерін көрсетіп, жауапты қайтарады."""
    if t == "choice":
        opts = c.get("options", [])
        order = _shuffled(opts, seed) if c.get("shuffle", True) else list(range(len(opts)))
        label = lambda i: opts[i]["text"] or f"{T('Нұсқа', 'Вариант')} {i + 1}"
        if c.get("multiple"):
            st.caption(T("Бірнеше дұрыс жауапты таңдаңыз", "Выберите несколько правильных ответов"))
            return [i for i in order if st.checkbox(label(i), key=f"{key}_o{i}")]
        st.caption(T("Бір дұрыс жауапты таңдаңыз", "Выберите один правильный ответ"))
        choice = st.radio("answer", order, index=None, key=f"{key}_r", format_func=label,
                          label_visibility="collapsed")
        return [] if choice is None else [choice]

    if t == "table":
        cols = c.get("columns", ["Иә", "Жоқ"])
        ans = {}
        for i, row in enumerate(c.get("rows", [])):
            a, b = st.columns([3, 2])
            a.markdown(row.get("text", ""))
            v = b.radio(f"r{i}", list(range(len(cols))), index=None, horizontal=True, key=f"{key}_t{i}",
                        format_func=lambda j: cols[j], label_visibility="collapsed")
            if v is not None:
                ans[str(i)] = v
            st.divider()
        return ans

    if t == "number":
        return st.text_input(T("Жауабыңыз (сан)", "Ваш ответ (число)"), key=f"{key}_n")

    if t == "string":
        return st.text_input(T("Жауабыңыз", "Ваш ответ"), key=f"{key}_s")

    if t == "fill_blanks":
        parts = grading.BLANK_RE.split(c.get("text", ""))
        shown = "".join(p if i % 2 == 0 else f" **({i // 2 + 1}) ______** " for i, p in enumerate(parts))
        show_text(shown)
        n = len(grading.blanks(c.get("text", "")))
        cols = st.columns(min(n, 4) or 1)
        return [cols[i % len(cols)].text_input(f"({i + 1})", key=f"{key}_b{i}") for i in range(n)]

    if t == "matching":
        pairs = c.get("pairs", [])
        rights = [p["right"] for p in pairs]
        order = _shuffled(rights, seed)
        options = ["—"] + [rights[i] for i in order]
        ans = {}
        for i, p in enumerate(pairs):
            a, b = st.columns([1, 1])
            a.markdown(f"**{p['left']}**")
            v = b.selectbox("match", options, key=f"{key}_m{i}", label_visibility="collapsed")
            if v != "—":
                ans[str(i)] = v
        return ans

    if t == "sorting":
        items = c.get("items", [])
        order = _shuffled(items, seed)
        st.caption(T("Элементтерді дұрыс ретпен орналастырыңыз (1 — бірінші)",
                     "Расположите элементы в правильном порядке (1 — первый)"))
        st.markdown(" · ".join(f"`{items[i]}`" for i in order))
        result = []
        for pos in range(len(items)):
            v = st.selectbox(T(f"{pos + 1}-орын", f"Место {pos + 1}"), ["—"] + [items[i] for i in order],
                             key=f"{key}_so{pos}")
            result.append(None if v == "—" else v)
        return result

    if t == "free_text":
        return st.text_area(T("Жауабыңыз", "Ваш ответ"), height=180, key=f"{key}_f")

    return None


def render_step(step, user_id=None, class_id=None, preview=False):
    """Бір қадамды көрсету. preview=True — мұғалімнің алдын ала қарауы (журналға жазылмайды)."""
    t = step["type"]
    c = localize(step["content"])
    if t != "fill_blanks":
        show_text(c.get("text", ""))
    if t == "text":
        return

    pts = float(step.get("points") or 0)
    key = f"st{step['id']}_{lang()}_{'p' if preview else 'u'}"
    seed = (user_id or 0) * 100003 + step["id"]

    history = [] if preview else repo.submissions_for(step["id"], user_id, class_id)
    best = max([h["score"] for h in history], default=0)
    solved = any(h["status"] == "correct" for h in history)
    pending = any(h["status"] == "pending" for h in history)
    max_att = int(c.get("max_attempts", 0) or 0)
    used = len(history)
    left = (max_att - used) if max_att else None

    info = T("Балл", "Балл") + f": **{best:g} / {pts:g}**"
    if max_att:
        info += " · " + T("Әрекеттер", "Попытки") + f": {used}/{max_att}"
    st.caption(info)

    def explanation():
        if c.get("explanation"):
            with st.expander(T("Түсіндірме", "Пояснение")):
                show_text(c["explanation"])

    if solved:
        st.success(T("Шешілді ✅", "Решено ✅") + f"  {best:g} / {pts:g} " + T("балл", "балл."))
        explanation()
        if not st.toggle(T("Қайта шешу", "Решить снова"), key=f"{key}_again"):
            return
    if pending and not solved:
        st.info(T("⏳ Жауабыңыз мұғалімнің тексеруін күтуде.", "⏳ Ваш ответ ожидает проверки учителем."))
        with st.expander(T("Жіберген жауабыңыз", "Ваш ответ")):
            st.write(db.loads(history[0]["answer"], ""))
        return
    if left is not None and left <= 0 and not solved:
        st.error(T("Әрекеттер таусылды. Нәтиже: ", "Попытки закончились. Результат: ") + f"{best:g} / {pts:g}")
        explanation()
        return

    answer = render_inputs(t, c, key, seed)

    if st.button(T("Жіберу", "Отправить"), type="primary", key=f"{key}_send"):
        score, status, _ = grading.check(t, c, answer, pts)
        if not preview and user_id and class_id:
            repo.add_submission(step["id"], user_id, class_id, answer, score, pts, status)
        st.session_state[f"{key}_msg"] = (status, score)
        st.rerun()

    if f"{key}_msg" in st.session_state:
        status, score = st.session_state[f"{key}_msg"]
        msgs = {"correct": T("Дұрыс! 🎉", "Верно! 🎉"),
                "partial": T("Жартылай дұрыс", "Частично верно"),
                "pending": T("Жауабыңыз жіберілді. Мұғалім тексергеннен кейін балл қойылады.",
                             "Ответ отправлен. Балл будет выставлен после проверки учителем."),
                "wrong": T("Қате. Тағы байқап көріңіз.", "Неверно. Попробуйте ещё раз.")}
        text = f"{msgs.get(status, msgs['wrong'])}  ({score:g} / {pts:g} {T('балл', 'балл.')})"
        {"correct": st.success, "partial": st.warning, "pending": st.info}.get(status, st.error)(text)
        if preview:
            st.caption(T("Алдын ала қарау режимі — нәтиже журналға жазылмайды.",
                         "Режим предпросмотра — результат не записывается в журнал."))


def render_lesson(lesson, user_id=None, class_id=None, preview=False):
    steps = repo.steps(lesson["id"])
    if not steps:
        st.info(T("Бұл сабақта әзірге тапсырма жоқ.", "В этом уроке пока нет заданий."))
        return
    scores = {} if preview else repo.best_scores(user_id, class_id)
    labels = []
    for i, s in enumerate(steps):
        icon = "📄" if s["type"] == "text" else STATUS_ICON[scores.get(s["id"], (0, None))[1]]
        labels.append(f"{icon} {i + 1}")
    k = f"lesson_step_{lesson['id']}_{'p' if preview else 'u'}"
    idx = st.radio("step", list(range(len(steps))), format_func=lambda i: labels[i], horizontal=True, key=k,
                   label_visibility="collapsed")
    st.divider()
    render_step(steps[idx], user_id, class_id, preview)
    st.divider()
    a, _, b = st.columns([1, 3, 1])
    if idx > 0:
        a.button(T("← Алдыңғы", "← Назад"), key=f"{k}_prev", on_click=_go, args=(k, idx - 1))
    if idx < len(steps) - 1:
        b.button(T("Келесі →", "Далее →"), key=f"{k}_next", on_click=_go, args=(k, idx + 1))


def _go(key, value):
    st.session_state[key] = value
