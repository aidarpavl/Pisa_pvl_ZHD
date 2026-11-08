"""Сынып бойынша баллдар есебі (Excel), Stepik-тің gradebook файлы үлгісімен.

1-парақ «Табель» — Stepik форматы: user_id, last_name, first_name, «<сабақ> Q<қадам нөмірі>» бағандары,
total, date_joined_utc, last_viewed_utc.
2-парақ «Жиынтық» — сынып, мектеп, оқушылар саны, сабақтар бойынша орташа балл.
3-парақ «Оқушылар» — оқушылар тізімі (Stepik-тің students беті сияқты).
"""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import repo
import schools
from i18n import localize  # noqa: F401  (тіл өрістері үшін)

HEAD_FILL = PatternFill("solid", fgColor="DDEBE3")
BOLD = Font(bold=True)


def _split_name(full):
    parts = (full or "").split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def _num(v):
    v = float(v or 0)
    return int(v) if v.is_integer() else round(v, 2)


def _dt(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return s


def collect(cls, lang="kz"):
    """Есепке керекті деректер: бағандар, оқушылар жолдары, жиынтық."""
    def ttl(row):
        return (row.get("title_ru") if lang == "ru" and row.get("title_ru") else row["title"])

    lessons = repo.course_lessons(cls["course_id"])
    columns = []  # (step_id, header, points, lesson_title)
    for l in lessons:
        for pos, s in enumerate(repo.steps(l["id"]), start=1):
            if s["type"] != "text":
                columns.append((s["id"], f"{ttl(l)} Q{pos}", float(s["points"] or 0), ttl(l)))
    scores = {(r["student_id"], r["step_id"]): float(r["best"] or 0) for r in repo.class_scores(cls["id"])}
    students = repo.class_students(cls["id"])
    rows = []
    for stu in students:
        u = repo.db.query_one("SELECT * FROM users WHERE id=?", (stu["id"],))
        last = repo.db.query_one("SELECT MAX(created_at) AS t FROM submissions WHERE student_id=? AND class_id=?",
                                 (stu["id"], cls["id"]))["t"]
        last_viewed = max([x for x in (last, u.get("last_seen")) if x], default=None)
        vals = [scores.get((stu["id"], sid), 0.0) for sid, *_ in columns]
        rows.append({"user": u, "joined": stu["joined_at"], "last": last_viewed, "vals": vals, "total": sum(vals)})
    max_total = sum(c[2] for c in columns)
    return columns, rows, max_total


def build_xlsx(cls, teacher_name="", lang="kz"):
    L = (lambda kz, ru: ru) if lang == "ru" else (lambda kz, ru: kz)
    columns, rows, max_total = collect(cls, lang)
    wb = Workbook()

    # ---------- 1. Табель (Stepik форматы) ----------
    ws = wb.active
    ws.title = L("Табель", "Табель")
    header = ["user_id", "last_name", "first_name"] + [c[1] for c in columns] + \
             ["total", "date_joined_utc", "last_viewed_utc"]
    ws.append(header)
    for r in rows:
        last, first = _split_name(r["user"]["name"])
        ws.append([r["user"]["id"], last, first] + [_num(v) for v in r["vals"]] +
                  [_num(r["total"]), _dt(r["joined"]), _dt(r["last"])])
    for c in ws[1]:
        c.font = BOLD
        c.fill = HEAD_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i in range(1, len(header) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 13
    for col in (len(header) - 1, len(header)):
        ws.column_dimensions[get_column_letter(col)].width = 19
        for cell in ws.iter_rows(min_row=2, min_col=col, max_col=col):
            cell[0].number_format = "yyyy-mm-dd hh:mm:ss"
    ws.row_dimensions[1].height = 60
    ws.freeze_panes = "D2"

    # ---------- 2. Жиынтық ----------
    ss = wb.create_sheet(L("Жиынтық", "Сводка"))
    lic = schools.teacher_license(cls["teacher_id"])
    started = sum(1 for r in rows if r["total"] > 0)
    avg = sum(r["total"] for r in rows) / len(rows) if rows else 0
    info = [
        (L("Есеп", "Отчёт"), L("Сынып бойынша баллдар есебі", "Отчёт по баллам класса")),
        (L("Құрылған уақыты", "Дата формирования"), datetime.now().strftime("%Y-%m-%d %H:%M")),
        (L("Мектеп", "Школа"), lic["school_name"] if lic else "—"),
        (L("Сынып", "Класс"), cls["name"]),
        (L("Курс", "Курс"), cls.get("course_title_ru") if lang == "ru" and cls.get("course_title_ru") else cls.get("course_title")),
        (L("Мұғалім", "Учитель"), teacher_name),
        (L("Оқушылар саны", "Количество учащихся"), len(rows)),
        (L("Тапсырма орындағандар", "Приступили к заданиям"), started),
        (L("Курстың максимал балы", "Максимальный балл курса"), _num(max_total)),
        (L("Орташа балл", "Средний балл"), round(avg, 2)),
        (L("Орташа нәтиже, %", "Средний результат, %"), round(100 * avg / max_total, 1) if max_total else 0),
    ]
    for k, v in info:
        ss.append([k, v])
        ss.cell(ss.max_row, 1).font = BOLD
    ss.append([])
    ss.append([L("Сабақ", "Урок"), L("Макс. балл", "Макс. балл"), L("Орташа балл", "Средний балл"),
               L("Орташа %", "Средний %"), L("Толық орындағандар", "Выполнили полностью")])
    hdr = ss.max_row
    for c in ss[hdr]:
        c.font = BOLD
        c.fill = HEAD_FILL
    lessons_order = []
    for i, c in enumerate(columns):
        if c[3] not in lessons_order:
            lessons_order.append(c[3])
    for lt in lessons_order:
        idx = [i for i, c in enumerate(columns) if c[3] == lt]
        mx = sum(columns[i][2] for i in idx)
        sums = [sum(r["vals"][i] for i in idx) for r in rows]
        a = sum(sums) / len(sums) if sums else 0
        full = sum(1 for s_ in sums if mx and s_ >= mx - 1e-9)
        ss.append([lt, _num(mx), round(a, 2), round(100 * a / mx, 1) if mx else 0, full])
    ss.column_dimensions["A"].width = 42
    for col in "BCDE":
        ss.column_dimensions[col].width = 20

    # ---------- 3. Оқушылар ----------
    st_ = wb.create_sheet(L("Оқушылар", "Ученики"))
    st_.append(["№", L("Аты-жөні", "ФИО"), "Email", L("Сынып", "Класс"), L("Телефон", "Телефон"),
                L("Тіркелген", "Дата вступления"), L("Соңғы белсенділік", "Последняя активность"),
                L("Балл", "Балл"), "%"])
    for c in st_[1]:
        c.font = BOLD
        c.fill = HEAD_FILL
    for n, r in enumerate(sorted(rows, key=lambda x: -x["total"]), start=1):
        u = r["user"]
        grade = f"{u.get('grade') or ''}{u.get('grade_letter') or ''}"
        st_.append([n, u["name"], u["email"], grade, u.get("phone") or "", _dt(r["joined"]), _dt(r["last"]),
                    _num(r["total"]), round(100 * r["total"] / max_total, 1) if max_total else 0])
    for col, w in zip("ABCDEFGHI", (5, 32, 28, 8, 16, 19, 19, 8, 8)):
        st_.column_dimensions[col].width = w
    for col in "FG":
        for cell in st_[col][1:]:
            cell.number_format = "yyyy-mm-dd hh:mm"
    st_.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filename(cls):
    return f"class-{cls['id']}-grade-book-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.xlsx"
