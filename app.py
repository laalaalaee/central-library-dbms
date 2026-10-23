import os
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import Flask, g, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "library.db")
LOAN_DAYS = 14
FINE_PER_DAY = 2  # keep in sync with the calc_fine trigger in schema.sql
MAX_LOANS = 3

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "central-library-dev-key")


# database
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def query(sql, args=(), one=False):
    rows = db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def scalar(sql, args=()):
    return db().execute(sql, args).fetchone()[0]


def today():
    return date.today().isoformat()


def init_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    with open(os.path.join(BASE, "schema.sql")) as f:
        conn.executescript(f.read())
    if not conn.execute("SELECT 1 FROM users").fetchone():
        seed(conn)
    conn.commit()
    conn.close()


def seed(conn):
    t = date.today()
    d = lambda n: (t + timedelta(days=n)).isoformat()

    conn.execute("INSERT INTO users(name,email,password,role,joined_on) VALUES(?,?,?,'admin',?)",
                 ("Librarian", "admin@lib.com", generate_password_hash("admin123"), d(-180)))
    members = [
        ("Aarav Sharma", "aarav@student.edu", -120), ("Priya Verma", "priya@student.edu", -110),
        ("Rohan Gupta", "rohan@student.edu", -95), ("Sneha Iyer", "sneha@student.edu", -80),
        ("Karan Mehta", "karan@student.edu", -60),
    ]
    pw = generate_password_hash("member123")
    conn.executemany("INSERT INTO users(name,email,password,joined_on) VALUES(?,?,?,?)",
                     [(n, e, pw, d(j)) for n, e, j in members])

    conn.executemany("INSERT INTO books(title,author,category,isbn,year,copies) VALUES(?,?,?,?,?,?)", [
        ("Database System Concepts", "Silberschatz, Korth, Sudarshan", "Databases", "9780073523323", 2010, 4),
        ("Fundamentals of Database Systems", "Elmasri, Navathe", "Databases", "9780133970777", 2015, 3),
        ("An Introduction to Database Systems", "C. J. Date", "Databases", "9780321197849", 2003, 2),
        ("Operating System Concepts", "Silberschatz, Galvin, Gagne", "Operating Systems", "9781118063330", 2012, 3),
        ("Modern Operating Systems", "Andrew S. Tanenbaum", "Operating Systems", "9780133591620", 2014, 2),
        ("Computer Networks", "Andrew S. Tanenbaum", "Networks", "9780132126953", 2010, 3),
        ("Computer Networking: A Top-Down Approach", "Kurose, Ross", "Networks", "9780133594140", 2016, 2),
        ("Introduction to Algorithms", "Cormen, Leiserson, Rivest, Stein", "Algorithms", "9780262033848", 2009, 4),
        ("The Algorithm Design Manual", "Steven S. Skiena", "Algorithms", "9781848000698", 2008, 2),
        ("Clean Code", "Robert C. Martin", "Software Engineering", "9780132350884", 2008, 3),
        ("The Pragmatic Programmer", "Hunt, Thomas", "Software Engineering", "9780201616224", 1999, 2),
        ("Design Patterns", "Gamma, Helm, Johnson, Vlissides", "Software Engineering", "9780201633610", 1994, 2),
        ("Artificial Intelligence: A Modern Approach", "Russell, Norvig", "Artificial Intelligence", "9780136042594", 2009, 3),
        ("Pattern Recognition and Machine Learning", "Christopher M. Bishop", "Artificial Intelligence", "9780387310732", 2006, 1),
        ("Computer Organization and Design", "Patterson, Hennessy", "Architecture", "9780124077263", 2013, 2),
        ("Compilers: Principles, Techniques, and Tools", "Aho, Lam, Sethi, Ullman", "Compilers", "9780321486813", 2006, 2),
        ("The C Programming Language", "Kernighan, Ritchie", "Programming", "9780131103627", 1988, 3),
        ("Let Us C", "Yashavant Kanetkar", "Programming", "9788183331630", 2016, 4),
    ])

    ids = {r["email"]: r["user_id"] for r in conn.execute("SELECT user_id, email FROM users")}
    # (member, book_id, issued N days ago, returned N days ago or None)
    loans = [
        ("aarav", 18, 50, 31), ("priya", 13, 60, 44), ("karan", 10, 45, 33), ("priya", 1, 40, 28),
        ("rohan", 6, 35, 17), ("sneha", 8, 30, 16), ("sneha", 10, 25, 12),
        ("rohan", 13, 20, None), ("aarav", 10, 17, None), ("sneha", 4, 12, None),
        ("aarav", 1, 5, None), ("priya", 8, 2, None), ("karan", 17, 1, None),
    ]
    for who, book, issued, returned in loans:
        cur = conn.execute("INSERT INTO issues(user_id,book_id,issue_date,due_date) VALUES(?,?,?,?)",
                           (ids[f"{who}@student.edu"], book, d(-issued), d(-issued + LOAN_DAYS)))
        if returned is not None:
            conn.execute("UPDATE issues SET return_date=? WHERE issue_id=?", (d(-returned), cur.lastrowid))


# template helpers
COVERS = ["#7a2e2e", "#1f3b5a", "#2f5d4a", "#86621f", "#4a4458", "#5b3a29", "#355c66", "#6b3550"]


@app.template_filter("cover")
def cover(book_id):
    return COVERS[int(book_id) % len(COVERS)]


@app.template_filter("nice")
def nice(s):
    if not s:
        return "—"
    d = date.fromisoformat(s) if isinstance(s, str) else s
    return f"{d.day} {d:%b %Y}"


@app.template_filter("initials")
def initials(name):
    return "".join(p[0] for p in name.split()[:2]).upper()


@app.template_filter("loan_state")
def loan_state(i):
    if i["return_date"]:
        return ("Late return", "warn") if i["fine"] else ("Returned", "muted")
    days = (date.fromisoformat(i["due_date"]) - date.today()).days
    if days < 0:
        return (f"{-days} day{'s' if days != -1 else ''} overdue", "danger")
    if days == 0:
        return ("Due today", "warn")
    if days <= 3:
        return (f"Due in {days} day{'s' if days != 1 else ''}", "warn")
    return (f"Due in {days} days", "ok")


@app.template_filter("loan_progress")
def loan_progress(i):
    start, due = date.fromisoformat(i["issue_date"]), date.fromisoformat(i["due_date"])
    span = max((due - start).days, 1)
    return min(100, max(4, round((date.today() - start).days / span * 100)))


@app.context_processor
def globals_():
    nav_overdue = 0
    if "uid" in session:
        sql = "SELECT COUNT(*) FROM issues WHERE return_date IS NULL AND due_date < ?"
        args = [today()]
        if session["role"] != "admin":
            sql += " AND user_id = ?"
            args.append(session["uid"])
        nav_overdue = scalar(sql, args)
    return dict(today=today(), FINE_PER_DAY=FINE_PER_DAY, LOAN_DAYS=LOAN_DAYS, MAX_LOANS=MAX_LOANS,
                nav_overdue=nav_overdue)


def categories():
    return [r[0] for r in query("SELECT DISTINCT category FROM books WHERE category <> '' ORDER BY 1")]


# auth
def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "uid" not in session:
                return redirect(url_for("login"))
            if role and session["role"] != role:
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco


@app.route("/")
def home():
    if "uid" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("overview" if session["role"] == "admin" else "catalogue"))


def auth_figures():
    return dict(titles=scalar("SELECT COUNT(*) FROM books"),
                members=scalar("SELECT COUNT(*) FROM users WHERE role='user'"),
                on_loan=scalar("SELECT COUNT(*) FROM issues WHERE return_date IS NULL"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "uid" in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        u = query("SELECT * FROM users WHERE email=?", (request.form["email"].strip().lower(),), one=True)
        if u and check_password_hash(u["password"], request.form["password"]):
            session.clear()
            session.update(uid=u["user_id"], name=u["name"], role=u["role"])
            return redirect(url_for("home"))
        flash("That email and password don't match our records.", "err")
    return render_template("login.html", figures=auth_figures())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "err")
        else:
            try:
                db().execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                             (name, email, generate_password_hash(password)))
                db().commit()
                flash("Your membership is ready. Sign in to start borrowing.", "ok")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "err")
    return render_template("register.html", figures=auth_figures())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# circulation rules
def borrow(user_id, book_id):
    b = query("SELECT * FROM book_stock WHERE book_id=?", (book_id,), one=True)
    if not b:
        return False, "That book no longer exists."
    if b["available"] < 1:
        return False, f"All copies of “{b['title']}” are out on loan."
    if query("SELECT 1 FROM issues WHERE user_id=? AND book_id=? AND return_date IS NULL",
             (user_id, book_id), one=True):
        return False, f"“{b['title']}” is already on loan to this member."
    if scalar("SELECT COUNT(*) FROM issues WHERE user_id=? AND return_date IS NULL", (user_id,)) >= MAX_LOANS:
        return False, f"Members can hold at most {MAX_LOANS} books at a time."
    if scalar("SELECT COUNT(*) FROM issues WHERE user_id=? AND return_date IS NULL AND due_date < ?",
              (user_id, today())):
        return False, "Overdue books must be returned before borrowing another."
    due = (date.today() + timedelta(days=LOAN_DAYS)).isoformat()
    db().execute("INSERT INTO issues(user_id,book_id,issue_date,due_date) VALUES(?,?,?,?)",
                 (user_id, book_id, today(), due))
    db().commit()
    return True, f"“{b['title']}” issued. Due back on {nice(due)}."


def return_loan(issue_id, user_id=None):
    sql = "SELECT i.*, b.title FROM issues i JOIN books b USING(book_id) WHERE issue_id=? AND return_date IS NULL"
    args = [issue_id]
    if user_id:
        sql += " AND user_id=?"
        args.append(user_id)
    loan = query(sql, args, one=True)
    if not loan:
        flash("That loan has already been closed.", "err")
        return
    db().execute("UPDATE issues SET return_date=? WHERE issue_id=?", (today(), issue_id))
    db().commit()
    fine = scalar("SELECT fine FROM issues WHERE issue_id=?", (issue_id,))
    msg = f"“{loan['title']}” returned."
    flash(msg + (f" Late fine of Rs {fine} recorded." if fine else " No fine due."), "ok")


# librarian
@app.route("/admin")
@login_required("admin")
def overview():
    t = today()
    stats = dict(
        titles=scalar("SELECT COUNT(*) FROM books"),
        copies=scalar("SELECT COALESCE(SUM(copies),0) FROM books"),
        on_loan=scalar("SELECT COUNT(*) FROM issues WHERE return_date IS NULL"),
        overdue=scalar("SELECT COUNT(*) FROM issues WHERE return_date IS NULL AND due_date < ?", (t,)),
        members=scalar("SELECT COUNT(*) FROM users WHERE role='user'"),
        fines=scalar("SELECT COALESCE(SUM(fine),0) FROM issues"),
    )
    overdue = query("""SELECT i.*, u.name AS member, b.title, b.book_id FROM issues i
                       JOIN users u USING(user_id) JOIN books b USING(book_id)
                       WHERE i.return_date IS NULL AND i.due_date < ? ORDER BY i.due_date""", (t,))
    due_soon = query("""SELECT i.*, u.name AS member, b.title, b.book_id FROM issues i
                        JOIN users u USING(user_id) JOIN books b USING(book_id)
                        WHERE i.return_date IS NULL AND i.due_date >= ? ORDER BY i.due_date LIMIT 5""", (t,))
    popular = query("""SELECT b.book_id, b.title, b.author, COUNT(*) AS loans FROM issues i
                       JOIN books b USING(book_id) GROUP BY b.book_id ORDER BY loans DESC, b.title LIMIT 5""")
    by_cat = query("""SELECT b.category, COUNT(*) AS loans FROM issues i JOIN books b USING(book_id)
                      GROUP BY b.category ORDER BY loans DESC""")
    activity = query("""SELECT i.*, u.name AS member, b.title, b.book_id,
                               COALESCE(i.return_date, i.issue_date) AS at FROM issues i
                        JOIN users u USING(user_id) JOIN books b USING(book_id)
                        ORDER BY at DESC, i.issue_id DESC LIMIT 7""")
    return render_template("admin/overview.html", stats=stats, overdue=overdue, due_soon=due_soon,
                           popular=popular, by_cat=by_cat, activity=activity,
                           long_date=f"{date.today():%A}, {date.today().day} {date.today():%B %Y}")


@app.route("/admin/books")
@login_required("admin")
def books():
    q, cat = request.args.get("q", "").strip(), request.args.get("cat", "")
    like = f"%{q}%"
    rows = query("""SELECT * FROM book_stock
                    WHERE (title LIKE ? OR author LIKE ? OR isbn LIKE ?) AND (? = '' OR category = ?)
                    ORDER BY title""", (like, like, like, cat, cat))
    return render_template("admin/books.html", books=rows, q=q, cat=cat, cats=categories())


@app.route("/admin/books/new", methods=["GET", "POST"])
@app.route("/admin/books/<int:book_id>/edit", methods=["GET", "POST"])
@login_required("admin")
def book_form(book_id=None):
    book = query("SELECT * FROM book_stock WHERE book_id=?", (book_id,), one=True) if book_id else None
    if book_id and not book:
        abort(404)
    if request.method == "POST":
        f = request.form
        data = dict(title=f["title"].strip(), author=f["author"].strip(), category=f["category"].strip(),
                    isbn=f["isbn"].strip() or None, year=f["year"].strip(), copies=f["copies"].strip())
        on_loan = book["copies"] - book["available"] if book else 0
        error = None
        if not data["copies"].isdigit():
            error = "Copies must be a whole number."
        elif int(data["copies"]) < on_loan:
            error = f"{on_loan} copies are on loan right now, so copies can't go below {on_loan}."
        elif data["year"] and not (data["year"].isdigit() and 1450 <= int(data["year"]) <= date.today().year):
            error = "Enter a valid publication year."
        if not error:
            vals = (data["title"], data["author"], data["category"], data["isbn"],
                    int(data["year"]) if data["year"] else None, int(data["copies"]))
            try:
                if book:
                    db().execute("UPDATE books SET title=?,author=?,category=?,isbn=?,year=?,copies=? WHERE book_id=?",
                                 vals + (book_id,))
                else:
                    db().execute("INSERT INTO books(title,author,category,isbn,year,copies) VALUES(?,?,?,?,?,?)", vals)
                db().commit()
                flash(f"“{data['title']}” {'updated' if book else 'added to the catalogue'}.", "ok")
                return redirect(url_for("books"))
            except sqlite3.IntegrityError:
                error = "Another book already uses that ISBN."
        flash(error, "err")
        book = dict(book or {}, **data, book_id=book_id or 0)
    return render_template("admin/book_form.html", book=book, cats=categories(), editing=bool(book_id))


@app.route("/admin/books/<int:book_id>/delete", methods=["POST"])
@login_required("admin")
def delete_book(book_id):
    b = query("SELECT * FROM book_stock WHERE book_id=?", (book_id,), one=True)
    if b and b["available"] < b["copies"]:
        flash(f"“{b['title']}” can't be removed while copies are on loan.", "err")
    elif b:
        db().execute("DELETE FROM books WHERE book_id=?", (book_id,))
        db().commit()
        flash(f"“{b['title']}” removed from the catalogue.", "ok")
    return redirect(url_for("books"))


@app.route("/admin/members")
@login_required("admin")
def members():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = query("""SELECT u.user_id, u.name, u.email, u.joined_on,
                           COUNT(i.issue_id) AS total,
                           SUM(i.issue_id IS NOT NULL AND i.return_date IS NULL) AS active,
                           SUM(i.return_date IS NULL AND i.due_date < ?) AS overdue,
                           COALESCE(SUM(i.fine), 0) AS fines
                    FROM users u LEFT JOIN issues i ON i.user_id = u.user_id
                    WHERE u.role='user' AND (u.name LIKE ? OR u.email LIKE ?)
                    GROUP BY u.user_id ORDER BY u.name""", (today(), like, like))
    return render_template("admin/members.html", members=rows, q=q)


@app.route("/admin/members/<int:user_id>/delete", methods=["POST"])
@login_required("admin")
def delete_member(user_id):
    u = query("SELECT * FROM users WHERE user_id=? AND role='user'", (user_id,), one=True)
    if u and scalar("SELECT COUNT(*) FROM issues WHERE user_id=? AND return_date IS NULL", (user_id,)):
        flash(f"{u['name']} still has books on loan.", "err")
    elif u:
        db().execute("DELETE FROM users WHERE user_id=?", (user_id,))
        db().commit()
        flash(f"{u['name']}'s membership was closed.", "ok")
    return redirect(url_for("members"))


LOAN_FILTERS = {
    "active": "i.return_date IS NULL",
    "overdue": "i.return_date IS NULL AND i.due_date < :t",
    "returned": "i.return_date IS NOT NULL",
    "all": "1",
}


@app.route("/admin/loans")
@login_required("admin")
def loans():
    status = request.args.get("status", "active")
    status = status if status in LOAN_FILTERS else "active"
    q = request.args.get("q", "").strip()
    args = dict(t=today(), q=f"%{q}%")
    counts = {k: scalar(f"SELECT COUNT(*) FROM issues i WHERE {w}", args) for k, w in LOAN_FILTERS.items()}
    rows = query(f"""SELECT i.*, u.name AS member, u.email, b.title, b.author FROM issues i
                     JOIN users u USING(user_id) JOIN books b USING(book_id)
                     WHERE {LOAN_FILTERS[status]} AND (u.name LIKE :q OR b.title LIKE :q)
                     ORDER BY i.return_date IS NOT NULL, CASE WHEN i.return_date IS NULL THEN i.due_date END, i.return_date DESC""", args)
    return render_template("admin/loans.html", loans=rows, status=status, counts=counts, q=q)


@app.route("/admin/loans/new", methods=["GET", "POST"])
@login_required("admin")
def new_loan():
    if request.method == "POST":
        ok, msg = borrow(int(request.form["user_id"]), int(request.form["book_id"]))
        flash(msg, "ok" if ok else "err")
        if ok:
            return redirect(url_for("loans"))
    return render_template("admin/loan_form.html",
                           members=query("SELECT user_id, name, email FROM users WHERE role='user' ORDER BY name"),
                           books=query("SELECT * FROM book_stock WHERE available > 0 ORDER BY title"),
                           pick_user=request.values.get("user_id", type=int),
                           pick_book=request.values.get("book_id", type=int))


@app.route("/admin/loans/<int:issue_id>/return", methods=["POST"])
@login_required("admin")
def admin_return(issue_id):
    return_loan(issue_id)
    return redirect(request.referrer or url_for("loans"))


# member
@app.route("/catalogue")
@login_required("user")
def catalogue():
    q, cat = request.args.get("q", "").strip(), request.args.get("cat", "")
    like = f"%{q}%"
    rows = query("""SELECT * FROM book_stock
                    WHERE (title LIKE ? OR author LIKE ?) AND (? = '' OR category = ?)
                    ORDER BY title""", (like, like, cat, cat))
    mine = {r[0] for r in db().execute(
        "SELECT book_id FROM issues WHERE user_id=? AND return_date IS NULL", (session["uid"],))}
    return render_template("member/catalogue.html", books=rows, q=q, cat=cat, cats=categories(),
                           mine=mine, at_limit=len(mine) >= MAX_LOANS)


@app.route("/catalogue/<int:book_id>/borrow", methods=["POST"])
@login_required("user")
def member_borrow(book_id):
    ok, msg = borrow(session["uid"], book_id)
    flash(msg, "ok" if ok else "err")
    return redirect(request.referrer or url_for("catalogue"))


@app.route("/my-loans")
@login_required("user")
def my_loans():
    rows = query("""SELECT i.*, b.title, b.author FROM issues i JOIN books b USING(book_id)
                    WHERE i.user_id=? ORDER BY i.return_date IS NOT NULL, CASE WHEN i.return_date IS NULL THEN i.due_date END, i.return_date DESC""",
                 (session["uid"],))
    active = [r for r in rows if not r["return_date"]]
    history = [r for r in rows if r["return_date"]]
    fines = sum(r["fine"] for r in rows)
    return render_template("member/loans.html", active=active, history=history, fines=fines)


@app.route("/my-loans/<int:issue_id>/return", methods=["POST"])
@login_required("user")
def member_return(issue_id):
    return_loan(issue_id, session["uid"])
    return redirect(url_for("my_loans"))


@app.errorhandler(403)
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=e.code), e.code


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=8000)
