"""Екі тіл: қазақша (kz) / орысша (ru)."""
import streamlit as st

LANGS = {"kz": "🇰🇿 Қазақша", "ru": "🇷🇺 Русский"}

# Тапсырма мазмұнындағы тілге тәуелді өрістер
LANG_FIELDS = ("text", "options", "rows", "columns", "items", "pairs", "answers", "explanation", "rubric")


def lang():
    return st.session_state.get("lang", "kz")


def T(kz, ru):
    """Ағымдағы тілдегі мәтін."""
    return ru if lang() == "ru" else kz


def title(row, field="title"):
    """DB жолының атауы ағымдағы тілде (орысшасы бос болса — қазақшасы)."""
    if row is None:
        return ""
    if lang() == "ru" and row.get(f"{field}_ru"):
        return row[f"{field}_ru"]
    return row.get(field) or ""


def localize(content, lng=None):
    """Тапсырма мазмұнын таңдалған тілге келтіру."""
    lng = lng or lang()
    content = dict(content or {})
    ru = content.pop("ru", None) or {}
    if lng == "ru" and ru:
        content.update({k: v for k, v in ru.items() if v not in (None, "", [])})
    return content


def set_lang_content(content, lng, new_view):
    """Редактордан келген өзгерістерді керекті тілге жазу."""
    content = dict(content or {})
    ru = dict(content.get("ru") or {})
    for k, v in new_view.items():
        if k == "ru":
            continue
        if k in LANG_FIELDS:
            if lng == "ru":
                ru[k] = v
            else:
                content[k] = v
        else:
            content[k] = v
    if ru:
        content["ru"] = ru
    return content


def _on_lang_change(key):
    st.session_state["lang"] = st.session_state[key]


def switcher(where=st.sidebar, key="lang_switch"):
    # Виджет жасалмай тұрып басқа ауыстырғышпен синхрондаймыз; таңдау on_change арқылы сақталады
    st.session_state[key] = lang()
    where.radio("Тіл / Язык", list(LANGS), horizontal=True, format_func=lambda k: LANGS[k], key=key,
                label_visibility="collapsed", on_change=_on_lang_change, args=(key,))
