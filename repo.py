"""Курс / сабақ / қадам / сынып / журнал бойынша деректерге қатынау."""
import db
import auth

# ---------- Курстар ----------

def courses():
    return db.query("SELECT * FROM courses ORDER BY id")


def course(cid):
    return db.query_one("SELECT * FROM courses WHERE id=?", (cid,))


def create_course(title, description, owner_id):
    return db.insert("INSERT INTO courses (title, description, owner_id, created_at) VALUES (?,?,?,?)",
                     (title, description, owner_id, db.now()))


def update_course(cid, title, description):
    db.execute("UPDATE courses SET title=?, description=? WHERE id=?", (title, description, cid))


def delete_course(cid):
    db.execute("DELETE FROM courses WHERE id=?", (cid,))


# ---------- Модульдер ----------

def modules(cid):
    return db.query("SELECT * FROM modules WHERE course_id=? ORDER BY position, id", (cid,))


def create_module(cid, title):
    pos = (db.query_one("SELECT COALESCE(MAX(position),0) AS m FROM modules WHERE course_id=?", (cid,)) or {"m": 0})["m"] + 1
    return db.insert("INSERT INTO modules (course_id, title, position) VALUES (?,?,?)", (cid, title, pos))


def update_module(mid, title):
    db.execute("UPDATE modules SET title=? WHERE id=?", (title, mid))


def delete_module(mid):
    db.execute("DELETE FROM modules WHERE id=?", (mid,))


# ---------- Сабақтар ----------

def lessons(mid):
    return db.query("SELECT * FROM lessons WHERE module_id=? ORDER BY position, id", (mid,))


def lesson(lid):
    return db.query_one("SELECT * FROM lessons WHERE id=?", (lid,))


def course_lessons(cid):
    return db.query(
        """SELECT l.*, m.title AS module_title, m.position AS mpos
           FROM lessons l JOIN modules m ON m.id=l.module_id
           WHERE m.course_id=? ORDER BY m.position, m.id, l.position, l.id""", (cid,))


def create_lesson(mid, title, stepik_id=None):
    pos = (db.query_one("SELECT COALESCE(MAX(position),0) AS m FROM lessons WHERE module_id=?", (mid,)) or {"m": 0})["m"] + 1
    return db.insert("INSERT INTO lessons (module_id, title, position, stepik_lesson_id) VALUES (?,?,?,?)",
                     (mid, title, pos, stepik_id))


def update_lesson(lid, title, stepik_id=None):
    db.execute("UPDATE lessons SET title=?, stepik_lesson_id=? WHERE id=?", (title, stepik_id, lid))


def delete_lesson(lid):
    db.execute("DELETE FROM lessons WHERE id=?", (lid,))


def move(table, row_id, parent_col, direction):
    """Жолды жоғары/төмен жылжыту (direction = -1 / +1)."""
    row = db.query_one(f"SELECT * FROM {table} WHERE id=?", (row_id,))
    siblings = db.query(f"SELECT id FROM {table} WHERE {parent_col}=? ORDER BY position, id", (row[parent_col],))
    ids = [s["id"] for s in siblings]
    i = ids.index(row_id)
    j = i + direction
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        for pos, rid in enumerate(ids, start=1):
            db.execute(f"UPDATE {table} SET position=? WHERE id=?", (pos, rid))


# ---------- Қадамдар ----------

def steps(lid):
    rows = db.query("SELECT * FROM steps WHERE lesson_id=? ORDER BY position, id", (lid,))
    for r in rows:
        r["content"] = db.loads(r["content"], {})
    return rows


def step(sid):
    r = db.query_one("SELECT * FROM steps WHERE id=?", (sid,))
    if r:
        r["content"] = db.loads(r["content"], {})
    return r


def create_step(lid, step_type, content, points, position=None):
    if position is None:
        position = (db.query_one("SELECT COALESCE(MAX(position),0) AS m FROM steps WHERE lesson_id=?", (lid,)) or {"m": 0})["m"] + 1
    return db.insert("INSERT INTO steps (lesson_id, position, type, content, points) VALUES (?,?,?,?,?)",
                     (lid, position, step_type, db.dumps(content), 0 if step_type == "text" else points))


def update_step(sid, content, points):
    db.execute("UPDATE steps SET content=?, points=? WHERE id=?", (db.dumps(content), points, sid))


def delete_step(sid):
    db.execute("DELETE FROM steps WHERE id=?", (sid,))


def lesson_max(lid):
    r = db.query_one("SELECT COALESCE(SUM(points),0) AS s FROM steps WHERE lesson_id=? AND type!='text'", (lid,))
    return float(r["s"] or 0)


# ---------- Сыныптар ----------

def teacher_classes(tid):
    return db.query(
        """SELECT c.*, co.title AS course_title,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.class_id=c.id) AS students
           FROM classes c JOIN courses co ON co.id=c.course_id
           WHERE c.teacher_id=? ORDER BY c.id DESC""", (tid,))


def class_by_code(code):
    return db.query_one(
        """SELECT c.*, co.title AS course_title, u.name AS teacher_name
           FROM classes c JOIN courses co ON co.id=c.course_id JOIN users u ON u.id=c.teacher_id
           WHERE upper(c.join_code)=upper(?)""", (code.strip(),))


def get_class(class_id):
    return db.query_one("SELECT c.*, co.title AS course_title FROM classes c JOIN courses co ON co.id=c.course_id WHERE c.id=?",
                        (class_id,))


def create_class(name, course_id, teacher_id):
    while True:
        code = auth.generate_code()
        if not class_by_code(code):
            break
    return db.insert("INSERT INTO classes (name, course_id, teacher_id, join_code, is_open, created_at) VALUES (?,?,?,?,1,?)",
                     (name, course_id, teacher_id, code, db.now()))


def set_class_open(class_id, is_open):
    db.execute("UPDATE classes SET is_open=? WHERE id=?", (1 if is_open else 0, class_id))


def regenerate_code(class_id):
    db.execute("UPDATE classes SET join_code=? WHERE id=?", (auth.generate_code(), class_id))


def delete_class(class_id):
    db.execute("DELETE FROM classes WHERE id=?", (class_id,))


def enroll(class_id, student_id):
    if not db.query_one("SELECT id FROM enrollments WHERE class_id=? AND student_id=?", (class_id, student_id)):
        db.insert("INSERT INTO enrollments (class_id, student_id, joined_at) VALUES (?,?,?)",
                  (class_id, student_id, db.now()))
        return True
    return False


def unenroll(class_id, student_id):
    db.execute("DELETE FROM enrollments WHERE class_id=? AND student_id=?", (class_id, student_id))


def class_students(class_id):
    return db.query(
        """SELECT u.id, u.name, u.email, e.joined_at FROM enrollments e
           JOIN users u ON u.id=e.student_id WHERE e.class_id=? ORDER BY u.name""", (class_id,))


def student_classes(sid):
    return db.query(
        """SELECT c.*, co.title AS course_title, u.name AS teacher_name FROM enrollments e
           JOIN classes c ON c.id=e.class_id JOIN courses co ON co.id=c.course_id
           JOIN users u ON u.id=c.teacher_id WHERE e.student_id=? ORDER BY c.id DESC""", (sid,))


# ---------- Жауаптар және журнал ----------

def add_submission(step_id, student_id, class_id, answer, score, max_score, status):
    return db.insert(
        """INSERT INTO submissions (step_id, student_id, class_id, answer, score, max_score, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (step_id, student_id, class_id, db.dumps(answer), score, max_score, status, db.now()))


def submissions_for(step_id, student_id, class_id):
    return db.query("SELECT * FROM submissions WHERE step_id=? AND student_id=? AND class_id=? ORDER BY id DESC",
                    (step_id, student_id, class_id))


def best_scores(student_id, class_id):
    """{step_id: (ең жақсы балл, соңғы статус)}"""
    rows = db.query(
        """SELECT step_id, MAX(score) AS best,
                  SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pend,
                  SUM(CASE WHEN status='correct' THEN 1 ELSE 0 END) AS ok
           FROM submissions WHERE student_id=? AND class_id=? GROUP BY step_id""", (student_id, class_id))
    out = {}
    for r in rows:
        status = "correct" if r["ok"] else ("pending" if r["pend"] else ("partial" if (r["best"] or 0) > 0 else "wrong"))
        out[r["step_id"]] = (float(r["best"] or 0), status)
    return out


def class_scores(class_id):
    """Сыныптағы барлық оқушылардың әр қадам бойынша ең жақсы балы."""
    return db.query(
        """SELECT s.student_id, s.step_id, MAX(s.score) AS best
           FROM submissions s JOIN enrollments e ON e.student_id=s.student_id AND e.class_id=s.class_id
           WHERE s.class_id=? GROUP BY s.student_id, s.step_id""", (class_id,))


def pending_reviews(class_id):
    return db.query(
        """SELECT s.*, u.name AS student_name, st.content AS step_content, st.points AS step_points,
                  l.title AS lesson_title
           FROM submissions s JOIN users u ON u.id=s.student_id
           JOIN steps st ON st.id=s.step_id JOIN lessons l ON l.id=st.lesson_id
           WHERE s.class_id=? AND s.status='pending' ORDER BY s.id""", (class_id,))


def grade_submission(sub_id, score, max_score, comment):
    status = "correct" if score >= max_score - 1e-9 else ("partial" if score > 0 else "wrong")
    db.execute("UPDATE submissions SET score=?, status=?, teacher_comment=? WHERE id=?",
               (score, status, comment, sub_id))
