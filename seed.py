"""Бастапқы деректер: content_data.COURSE мазмұнын деректер қорына жазу (бір рет)."""
import db
import repo
from content_data import COURSE


def seed_if_empty():
    # Курс бұрын жазылған болса (Витаминдер сабағы бар) — қайталамаймыз
    if db.query_one("SELECT id FROM lessons WHERE stepik_lesson_id=?", (541068,)):
        return
    cid = repo.create_course(COURSE["kz"], COURSE["desc_kz"], None, COURSE["ru"], COURSE["desc_ru"])
    for m in COURSE["modules"]:
        mid = repo.create_module(cid, m["kz"], m["ru"])
        for l in m["lessons"]:
            lid = repo.create_lesson(mid, l["kz"], l.get("stepik"), l["ru"])
            for s in l["steps"]:
                repo.create_step(lid, s["type"], s["content"], s["points"])
