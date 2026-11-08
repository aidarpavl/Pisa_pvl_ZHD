"""Оқушы тапсырманы орындайтын бет (қадамдарды көрсету және жауапты тексеру)."""
import random

import streamlit as st

import db
import grading
import repo

STATUS_ICON = {"correct": "✅", "partial": "🟡", "wrong": "❌", "pending": "⏳", None: "⚪"}


def show_text(text):
    if text:
        st.markdown(text, unsafe_allow_html=True)


def _shuffled(items, seed):
    idx = list(range(len(items)))
    random.Random(seed).shuffle(idx)
    return idx


def render_inputs(step, key, seed):
    """Тапсырма түріне қарай енгізу виджеттерін көрсетіп, жауапты қайтарады."""
    t, c = step["type"], step["content"]

    if t == "choice":
        opts = c.get("options", [])
        order = _shuffled(opts, seed) if c.get("shuffle", True) else list(range(len(opts)))
        if c.get("multiple"):
            st.caption("Бірнеше дұрыс жауапты таңдаңыз")
            return [i for i in order if st.checkbox(opts[i]["text"] or f"Нұсқа {i + 1}", key=f"{key}_o{i}")]
        st.caption("Бір дұрыс жауапты таңдаңыз")
        choice = st.radio("Жауап", order, index=None, key=f"{key}_r",
                          format_func=lambda i: opts[i]["text"] or f"Нұсқа {i + 1}", label_visibility="collapsed")
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
        return st.text_input("Жауабыңыз (сан)", key=f"{key}_n")

    if t == "string":
        return st.text_input("Жауабыңыз", key=f"{key}_s")

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
            v = b.selectbox("сәйкес", options, key=f"{key}_m{i}", label_visibility="collapsed")
            if v != "—":
                ans[str(i)] = v
        return ans

    if t == "sorting":
        items = c.get("items", [])
        order = _shuffled(items, seed)
        st.caption("Элементтерді дұрыс ретпен орналастырыңыз (1 — бірінші)")
        st.markdown("Берілген элементтер: " + " · ".join(f"`{items[i]}`" for i in order))
        result = []
        for pos in range(len(items)):
            v = st.selectbox(f"{pos + 1}-орын", ["—"] + [items[i] for i in order], key=f"{key}_so{pos}")
            result.append(None if v == "—" else v)
        return result

    if t == "free_text":
        return st.text_area("Жауабыңыз", height=180, key=f"{key}_f")

    return None


def render_step(step, user_id=None, class_id=None, preview=False):
    """Бір қадамды көрсету. preview=True — мұғалімнің алдын ала қарауы (журналға жазылмайды)."""
    t, c = step["type"], step["content"]
    show_text(c.get("text", "") if t != "fill_blanks" else "")
    if t == "text":
        return

    pts = float(step.get("points") or 0)
    key = f"st{step['id']}_{'p' if preview else 'u'}"
    seed = (user_id or 0) * 100003 + step["id"]

    history = [] if preview else repo.submissions_for(step["id"], user_id, class_id)
    best = max([h["score"] for h in history], default=0)
    solved = any(h["status"] == "correct" for h in history)
    pending = any(h["status"] == "pending" for h in history)
    max_att = int(c.get("max_attempts", 0) or 0)
    used = len(history)
    left = (max_att - used) if max_att else None

    info = f"Балл: **{best:g} / {pts:g}**"
    if max_att:
        info += f" · Әрекеттер: {used}/{max_att}"
    st.caption(info)

    if solved:
        st.success(f"Шешілді ✅  {best:g} / {pts:g} балл")
        if c.get("explanation"):
            with st.expander("Түсіндірме"):
                show_text(c["explanation"])
        if not st.toggle("Қайта шешу", key=f"{key}_again"):
            return
    if pending and not solved:
        last = history[0]
        st.info("⏳ Жауабыңыз мұғалімнің тексеруін күтуде.")
        with st.expander("Жіберген жауабыңыз"):
            st.write(db.loads(last["answer"], ""))
        return
    if left is not None and left <= 0 and not solved:
        st.error(f"Әрекеттер таусылды. Нәтиже: {best:g} / {pts:g}")
        if c.get("explanation"):
            with st.expander("Түсіндірме"):
                show_text(c["explanation"])
        return

    answer = render_inputs(step, key, seed)

    if st.button("Жіберу", type="primary", key=f"{key}_send"):
        score, status, msg = grading.check(t, c, answer, pts)
        if not preview and user_id and class_id:
            repo.add_submission(step["id"], user_id, class_id, answer, score, pts, status)
        st.session_state[f"{key}_msg"] = (status, msg, score)
        st.rerun()

    if f"{key}_msg" in st.session_state:
        status, msg, score = st.session_state[f"{key}_msg"]
        text = f"{msg}  ({score:g} / {pts:g} балл)"
        {"correct": st.success, "partial": st.warning, "pending": st.info}.get(status, st.error)(text)
        if preview and status != "pending":
            st.caption("Алдын ала қарау режимі — нәтиже журналға жазылмайды.")


def render_lesson(lesson, user_id=None, class_id=None, preview=False):
    steps = repo.steps(lesson["id"])
    if not steps:
        st.info("Бұл сабақта әзірге тапсырма жоқ.")
        return
    scores = {} if preview else repo.best_scores(user_id, class_id)
    labels = []
    for i, s in enumerate(steps):
        icon = "📄" if s["type"] == "text" else STATUS_ICON[scores.get(s["id"], (0, None))[1]]
        labels.append(f"{icon} {i + 1}")
    k = f"lesson_step_{lesson['id']}_{'p' if preview else 'u'}"
    idx = st.radio("Қадам", list(range(len(steps))), format_func=lambda i: labels[i], horizontal=True, key=k,
                   label_visibility="collapsed")
    st.divider()
    render_step(steps[idx], user_id, class_id, preview)
    st.divider()
    a, _, b = st.columns([1, 3, 1])
    if idx > 0:
        a.button("← Алдыңғы", key=f"{k}_prev", on_click=_go, args=(k, idx - 1))
    if idx < len(steps) - 1:
        b.button("Келесі →", key=f"{k}_next", on_click=_go, args=(k, idx + 1))


def _go(key, value):
    st.session_state[key] = value
