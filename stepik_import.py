"""Stepik API арқылы сабақтарды импорттау.

Stepik-тегі курс жабық, сондықтан импорт мұғалімнің ӨЗ Stepik аккаунтымен жасалады:
  1. https://stepik.org/oauth2/applications/ бетінде қосымша тіркеңіз
     (Client type: confidential, Authorization grant type: client-credentials).
  2. Client ID және Client Secret мәндерін импорт бетіне енгізіңіз.
Курс авторы болсаңыз, дұрыс жауаптар да (step-sources) импортталады.
Тек оқушы ретінде қол жетімді болса, мәтін мен нұсқалар ғана келеді —
дұрыс жауаптарды редакторда өзіңіз белгілейсіз.
"""
import re

import requests

API = "https://stepik.org/api"


def get_token(client_id, client_secret):
    r = requests.post("https://stepik.org/oauth2/token/", data={"grant_type": "client_credentials"},
                      auth=(client_id, client_secret), timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _get(path, token, params=None):
    r = requests.get(f"{API}/{path}", headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_lesson(lesson_id, token):
    """Қайтарады: (сабақ атауы, [(type, content, points), ...], ескертулер)"""
    warnings = []
    lesson = _get(f"lessons/{lesson_id}", token)["lessons"][0]
    step_ids = lesson.get("steps", [])
    steps_meta = {}
    if step_ids:
        data = _get("steps", token, params=[("ids[]", i) for i in step_ids])
        steps_meta = {s["id"]: s for s in data.get("steps", [])}
    sources = {}
    try:
        data = _get("step-sources", token, params=[("ids[]", i) for i in step_ids])
        sources = {s["id"]: s for s in data.get("step-sources", [])}
    except requests.HTTPError:
        warnings.append("Дұрыс жауаптарға рұқсат жоқ (курс авторы емессіз) — оларды редакторда белгілеңіз.")

    out = []
    for sid in step_ids:
        meta = steps_meta.get(sid, {})
        block = (sources.get(sid) or {}).get("block") or meta.get("block") or {}
        cost = float(meta.get("cost") or (sources.get(sid) or {}).get("cost") or 1)
        conv = convert_block(block, cost)
        if conv:
            out.append(conv)
        else:
            warnings.append(f"Қадам {sid}: «{block.get('name')}» түрі қолдау көрсетілмейді, мәтін ретінде қосылды.")
            out.append(("text", {"text": block.get("text", "")}, 0))
    return lesson.get("title", f"Stepik {lesson_id}"), out, warnings


def _clean(html):
    return (html or "").strip()


def _strip_tags(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def convert_block(block, cost):
    name = block.get("name")
    text = _clean(block.get("text"))
    src = block.get("source") or {}
    opts = block.get("options") or {}
    base = {"text": text, "max_attempts": 0, "partial": True, "explanation": ""}

    if name == "text":
        return "text", {"text": text}, 0

    if name == "choice":
        options = src.get("options") or [{"text": o, "is_correct": False} for o in opts.get("options", [])]
        base.update(options=[{"text": _strip_tags(o.get("text")), "correct": bool(o.get("is_correct"))}
                             for o in options],
                    multiple=bool(src.get("is_multiple_choice", opts.get("is_multiple_choice", False))),
                    shuffle=True)
        return "choice", base, cost

    if name == "number":
        o = (src.get("options") or [{}])[0]
        try:
            ans = float(str(o.get("answer", "0")).replace(",", "."))
        except ValueError:
            ans = 0.0
        base.update(answer=ans, tolerance=float(o.get("max_error") or 0))
        return "number", base, cost

    if name == "string":
        base.update(answers=[src.get("pattern", "")] if src.get("pattern") else [""],
                    case_sensitive=bool(src.get("case_sensitive")), regex=bool(src.get("use_re")))
        return "string", base, cost

    if name == "matching":
        pairs = src.get("pairs") or [{"first": p.get("first"), "second": p.get("second")} for p in opts.get("pairs", [])]
        base.update(pairs=[{"left": _strip_tags(p.get("first")), "right": _strip_tags(p.get("second"))} for p in pairs])
        return "matching", base, cost

    if name == "sorting":
        items = src.get("options") or [{"text": t} for t in opts.get("options", [])]
        base.update(items=[_strip_tags(i.get("text")) for i in items])
        return "sorting", base, cost

    if name == "table":
        columns = [c.get("name", "") for c in src.get("columns", [])] or \
                  [c.get("name", "") for c in opts.get("columns", [])] or ["Иә", "Жоқ"]
        rows = []
        for r in src.get("rows", []) or opts.get("rows", []):
            correct = 0
            for j, col in enumerate(r.get("columns", [])):
                if col.get("choice"):
                    correct = j
                    break
            rows.append({"text": _strip_tags(r.get("name", "")), "correct": correct})
        base.update(columns=columns, rows=rows)
        return "table", base, cost

    if name == "fill-blanks":
        parts = []
        for comp in src.get("components", []):
            if comp.get("type") == "text":
                parts.append(comp.get("text", ""))
            else:
                answers = [o.get("text", "") for o in comp.get("options", []) if o.get("is_correct", True)]
                parts.append("[[" + "|".join(answers or ["?"]) + "]]")
        joined = " ".join(parts)
        base.update(text=(text + "\n\n" + joined) if text and joined else (joined or text),
                    case_sensitive=bool(src.get("is_case_sensitive")))
        return "fill_blanks", base, cost

    if name in ("free-answer", "free_answer"):
        base.update(rubric="")
        return "free_text", base, cost

    return None
