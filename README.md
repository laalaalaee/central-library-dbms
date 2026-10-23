<h1 align="center">Central Library</h1>

<p align="center">
  A library management system with librarian and member dashboards.<br>
  Flask · SQLite · plain HTML and CSS, no frontend framework.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-1e4a3c?style=flat-square">
  <img alt="Flask" src="https://img.shields.io/badge/flask-3.x-1e4a3c?style=flat-square">
  <img alt="SQLite" src="https://img.shields.io/badge/database-SQLite-1e4a3c?style=flat-square">
  <img alt="Course" src="https://img.shields.io/badge/CSE201-DBMS-555?style=flat-square">
</p>

---

Mini project for **CSE201 Database Management Systems**, Amity University.

It is a client–server application: the browser is the client, a Flask server handles requests and enforces
the rules, and every piece of data lives in a relational SQL database. Librarians run the catalogue and
circulation desk, and members browse, borrow and return books.

## Quick start

```bash
git clone https://github.com/laalaalaee/central-library-dbms
cd central-library-dbms
pip install flask
python app.py
```

Open **http://localhost:8000**.

The repo ships with a populated `library.db`. To start again from clean demo data, stop the server,
delete `library.db` and run it again. The app rebuilds the database from `schema.sql`.

### Demo accounts

| Role      | Email               | Password    |
|-----------|---------------------|-------------|
| Librarian | `admin@lib.com`     | `admin123`  |
| Member    | `aarav@student.edu` | `member123` |

The other members (`priya`, `rohan`, `sneha`, `karan` at `@student.edu`) also use `member123`.
The sign-in page has one-click buttons for the demo accounts.

## Features

### Librarian
- **Overview:** totals, overdue loans, books coming due, recent activity, most borrowed titles, loans by subject
- **Catalogue:** add, edit, delete and search books, with a live cover preview in the form
- **Members:** loan counts and fines per member, issue a book to a member, close a membership
- **Circulation:** every loan, filtered by on loan, overdue or returned, with one-click returns

### Member
- Register, sign in and browse the catalogue by subject or search
- Borrow available books
- **My loans:** due dates, days left or days overdue, return books, history and fines

### Library rules
- Loans last 14 days, and the fine is Rs 2 for each late day
- A member can hold at most 3 books at a time
- A member with an overdue book cannot borrow until it is returned
- A book cannot be deleted while copies are on loan, and its copy count cannot go below the number on loan
- Passwords are stored hashed, and each page checks the user's role (403 for the wrong one)

## Database design

```
users   (user_id PK, name, email UNIQUE, password, role CHECK admin|user, joined_on)
books   (book_id PK, title, author, category, isbn UNIQUE, year CHECK, copies CHECK >= 0)
issues  (issue_id PK, user_id FK → users, book_id FK → books,
         issue_date, due_date, return_date NULL = still on loan, fine CHECK >= 0)
```

- **Relationships:** a member borrows many books and a book is borrowed by many members. This is a
  many-to-many relationship, resolved by the `issues` table, which holds one row per loan.
- **No redundant data:** available copies are never stored. The `book_stock` **view** calculates them
  as `copies − active loans`, so stock cannot drift out of sync.
- **Fines in the database:** the `calc_fine` **trigger** fires when `return_date` is set and computes
  the late fine, so the rule holds no matter which code path closes the loan.
- **Constraints:** PRIMARY KEY, FOREIGN KEY with `ON DELETE CASCADE`, UNIQUE, NOT NULL, CHECK, DEFAULT.
- **Indexes** on `issues(user_id)` and `issues(book_id)` for the join-heavy pages.

The full DDL is in [`schema.sql`](schema.sql).

### SQL concepts, and where to find them

| Concept | Where it is used |
|---|---|
| INSERT / SELECT / UPDATE / DELETE | add, list, edit and delete books; issue and return |
| INNER JOIN (3 tables) | circulation list: `issues ⋈ users ⋈ books` |
| LEFT JOIN + GROUP BY | members page; members with no loans still appear |
| COUNT, SUM, COALESCE | overview figures, fines per member |
| Subquery | the `book_stock` view counts active loans per book |
| LIKE | every search box |
| ORDER BY / LIMIT | most borrowed titles, recent activity |
| VIEW | `book_stock` |
| TRIGGER | `calc_fine` |
| Parameterised queries (`?`) | every query, which prevents SQL injection |

## Project structure

```
app.py              Flask server: routes, library rules, SQL queries
schema.sql          tables, view, trigger, indexes
library.db          sample database (rebuilt from schema.sql if deleted)
static/style.css    all styling
templates/
  base.html, auth.html, app.html     layouts (public, sign-in, signed-in shell)
  login.html, register.html
  admin/                             overview, books, book_form, members, loans, loan_form
  member/                            catalogue, loans
```

## Configuration

| Setting | Default | How to change |
|---|---|---|
| Port | `8000` | last line of `app.py` |
| Session secret | built-in dev key | set the `SECRET_KEY` environment variable |
| Loan length, fine, loan limit | 14 days, Rs 2/day, 3 books | constants at the top of `app.py` |

If you change the fine rate, change it in the `calc_fine` trigger in `schema.sql` too.
