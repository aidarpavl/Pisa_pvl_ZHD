"""Тапсырма түрлері және автоматты тексеру (Stepik-тегі қадам түрлеріне ұқсас)."""
import re

STEP_TYPES = {
    "text": "📄 Мәтін (теория)",
    "choice": "☑️ Тест (бір/бірнеше жауап)",
    "table": "▦ Кестелік тапсырма (Иә/Жоқ)",
    "number": "🔢 Сандық тапсырма",
    "string": "🔤 Мәтіндік жауап",
    "fill_blanks": "✏️ Бос орындарды толтыру",
    "matching": "🔗 Сәйкестендіру",
    "sorting": "↕️ Ретке келтіру",
    "free_text": "📝 Еркін жауап (мұғалім тексереді)",
}

AUTO_TYPES = {"choice", "table", "number", "string", "fill_blanks", "matching", "sorting"}

BLANK_RE = re.compile(r"\[\[(.+?)\]\]")


def default_content(step_type):
    base = {"text": "", "max_attempts": 0, "partial": True, "explanation": ""}
    if step_type == "text":
        return {"text": ""}
    if step_type == "choice":
        base.update(options=[{"text": "", "correct": True}, {"text": "", "correct": False}],
                    multiple=False, shuffle=True)
    elif step_type == "table":
        base.update(columns=["Иә", "Жоқ"], rows=[{"text": "", "correct": 0}])
    elif step_type == "number":
        base.update(answer=0.0, tolerance=0.0)
    elif step_type == "string":
        base.update(answers=[""], case_sensitive=False, regex=False)
    elif step_type == "fill_blanks":
        base.update(text="Мысал: Қазақстанның астанасы — [[Астана]].")
    elif step_type == "matching":
        base.update(pairs=[{"left": "", "right": ""}, {"left": "", "right": ""}])
    elif step_type == "sorting":
        base.update(items=["", ""])
    elif step_type == "free_text":
        base.update(rubric="")
    return base


def blanks(text):
    """[[жауап1|жауап2]] -> [['жауап1','жауап2'], ...]"""
    return [[a.strip() for a in m.split("|")] for m in BLANK_RE.findall(text or "")]


def _norm(s, case_sensitive=False):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if case_sensitive else s.lower().replace("ё", "е")


def _to_float(x):
    try:
        return float(str(x).replace(",", ".").replace(" ", ""))
    except Exception:
        return None


def check(step_type, content, answer, points):
    """Қайтарады: (ұпай, статус, хабарлама). статус: correct | partial | wrong | pending"""
    points = float(points or 0)
    partial = content.get("partial", True)

    def result(fraction, msg_ok="Дұрыс! 🎉", msg_bad="Қате. Тағы байқап көріңіз."):
        fraction = max(0.0, min(1.0, fraction))
        if fraction >= 0.999:
            return points, "correct", msg_ok
        if fraction > 0 and partial:
            return round(points * fraction, 2), "partial", f"Жартылай дұрыс: {round(fraction * 100)}%"
        return 0.0, "wrong", msg_bad

    if step_type == "choice":
        correct = {i for i, o in enumerate(content.get("options", [])) if o.get("correct")}
        chosen = set(answer or [])
        if not content.get("multiple"):
            return result(1.0 if chosen == correct else 0.0)
        n = len(content.get("options", [])) or 1
        right = sum(1 for i in range(n) if (i in chosen) == (i in correct))
        return result(1.0 if chosen == correct else (right / n if partial else 0.0))

    if step_type == "table":
        rows = content.get("rows", [])
        if not rows:
            return result(0)
        ok = sum(1 for i, r in enumerate(rows) if (answer or {}).get(str(i)) == r.get("correct"))
        return result(ok / len(rows))

    if step_type == "number":
        val = _to_float(answer)
        if val is None:
            return 0.0, "wrong", "Сан енгізіңіз."
        target = float(content.get("answer", 0))
        tol = float(content.get("tolerance", 0) or 0)
        return result(1.0 if abs(val - target) <= tol + 1e-9 else 0.0)

    if step_type == "string":
        cs = content.get("case_sensitive", False)
        given = _norm(answer, cs)
        for a in content.get("answers", []):
            if not str(a).strip():
                continue
            if content.get("regex"):
                flags = 0 if cs else re.IGNORECASE
                try:
                    if re.fullmatch(a, str(answer or "").strip(), flags):
                        return result(1.0)
                except re.error:
                    pass
            elif given == _norm(a, cs):
                return result(1.0)
        return result(0.0)

    if step_type == "fill_blanks":
        cs = content.get("case_sensitive", False)
        expected = blanks(content.get("text", ""))
        if not expected:
            return result(0)
        given = list(answer or [])
        ok = 0
        for i, alts in enumerate(expected):
            g = _norm(given[i] if i < len(given) else "", cs)
            if any(g == _norm(a, cs) for a in alts):
                ok += 1
        return result(ok / len(expected))

    if step_type == "matching":
        pairs = content.get("pairs", [])
        if not pairs:
            return result(0)
        ok = sum(1 for i, p in enumerate(pairs) if (answer or {}).get(str(i)) == p.get("right"))
        return result(ok / len(pairs))

    if step_type == "sorting":
        items = content.get("items", [])
        given = list(answer or [])
        if not items:
            return result(0)
        ok = sum(1 for i, it in enumerate(items) if i < len(given) and given[i] == it)
        return result(1.0 if given == items else ok / len(items))

    if step_type == "free_text":
        if not str(answer or "").strip():
            return 0.0, "wrong", "Жауап бос."
        return 0.0, "pending", "Жауабыңыз жіберілді. Мұғалім тексергеннен кейін балл қойылады."

    return 0.0, "wrong", "Белгісіз тапсырма түрі"
