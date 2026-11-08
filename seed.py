"""Курс мазмұнын деректер қорымен синхрондау (әр іске қосылғанда, қауіпсіз).

- Курс/модуль/сабақ жоқ болса — жасайды.
- Сабақ бар, бірақ ішінде тапсырма ЖОҚ болса — тапсырмаларды толтырады
  (ескі нұсқамен құрылған деректер қорлары да осылай толады, сынып байланыстары сақталады).
- Тапсырмасы бар сабақтарға тиіспейді: мұғалімнің өзгерістері өшпейді.
"""
import db
import repo
from content_data import COURSE


def _lesson_ids(l):
    return [i for i in (l.get("stepik"), l.get("stepik_ru")) if i]


def _fill(lesson_id, l):
    if not repo.steps(lesson_id) and l["steps"]:
        for s in l["steps"]:
            repo.create_step(lesson_id, s["type"], s["content"], s["points"])
        return True
    return False


def _find_course():
    lesson_ids = [i for m in COURSE["modules"] for l in m["lessons"] for i in _lesson_ids(l)]
    for c in repo.courses():
        if c["title"] in [COURSE["kz"]] + COURSE.get("old_titles", []):
            return c["id"]
    for sid in lesson_ids:
        r = db.query_one("""SELECT m.course_id FROM lessons l JOIN modules m ON m.id=l.module_id
                            WHERE l.stepik_lesson_id=?""", (sid,))
        if r:
            return r["course_id"]
    return None


def sync_content():
    filled = 0
    cid = _find_course()
    if cid is None:
        cid = repo.create_course(COURSE["kz"], COURSE["desc_kz"], None, COURSE["ru"], COURSE["desc_ru"])
    else:
        c = repo.course(cid)
        repo.update_course(cid, COURSE["kz"], c.get("description") or COURSE["desc_kz"], COURSE["ru"],
                           c.get("description_ru") or COURSE["desc_ru"])

    for m in COURSE["modules"]:
        names = {m["kz"], m["ru"], *m.get("old", [])}
        mod = next((x for x in repo.modules(cid) if x["title"] in names or (x.get("title_ru") or "") in names), None)
        if mod:
            mid = mod["id"]
            repo.update_module(mid, m["kz"], m["ru"])
        else:
            mid = repo.create_module(cid, m["kz"], m["ru"])

        order = []
        for l in m["lessons"]:
            ids = _lesson_ids(l)
            # 1) Осы курстағы сабақ (stepik ID немесе атауы бойынша)
            existing = None
            for x in repo.course_lessons(cid):
                if x.get("stepik_lesson_id") in ids or x["title"] in (l["kz"], l["ru"]):
                    existing = x
                    break
            if existing:
                lid = existing["id"]
                if not repo.steps(lid):  # бос сабақ — атауы мен орнын түзетеміз
                    db.execute("UPDATE lessons SET title=?, title_ru=?, module_id=?, stepik_lesson_id=? WHERE id=?",
                               (l["kz"], l["ru"], mid, l.get("stepik"), lid))
            else:
                lid = repo.create_lesson(mid, l["kz"], l.get("stepik"), l["ru"])
            filled += _fill(lid, l)
            order.append(lid)

            # 2) Басқа курстардағы (ескі нұсқадан қалған) бос сабақтарды да толтыру
            for sid in ids:
                for x in db.query("SELECT id FROM lessons WHERE stepik_lesson_id=? AND id<>?", (sid, lid)):
                    if not repo.steps(x["id"]):
                        db.execute("UPDATE lessons SET title=?, title_ru=? WHERE id=?", (l["kz"], l["ru"], x["id"]))
                        filled += _fill(x["id"], l)
        # мазмұндағы ретпен орналастыру (мұғалім қосқан басқа сабақтар соңында қалады)
        others = [x["id"] for x in repo.lessons(mid) if x["id"] not in order]
        for pos, lid in enumerate(order + others, start=1):
            db.execute("UPDATE lessons SET position=? WHERE id=?", (pos, lid))
    return filled


# бұрынғы атау (app.py шақырады)
seed_if_empty = sync_content
