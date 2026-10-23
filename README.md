# Central Library: Library Management System

CSE201 Database Management Systems, Mini Project.

A client–server web application. The browser is the client, a Python (Flask) server handles requests,
and all data lives in a relational SQL database (SQLite). It has two roles: **Librarian (admin)** and **Member (user)**.

## Run it

```
pip install flask
python app.py
```

Open **http://localhost:8000**. On the first run the app creates `library.db` and fills it with sample books,
members and loans. To start again from fresh demo data, stop the server, delete `library.db` and run it again.

| Role      | Email               | Password  |
|-----------|---------------------|-----------|
| Librarian | admin@lib.com       | admin123  |
| Member    | aarav@student.edu   | member123 |

All sample members (aarav, priya, rohan, sneha, karan @student.edu) use `member123`.
The sign-in page also has one-click demo buttons.

## Features

**Librarian**
- Overview: totals, overdue loans, books coming due, recent activity, most borrowed books, loans by subject
- Catalogue: add, edit, delete and search books (CRUD)
- Members: list with loan counts and fines; issue a book to a member; close a membership
- Circulation: every loan, filtered by On loan / Overdue / Returned / All; mark a book returned

**Member**
- Register and sign in
- Browse the catalogue by subject or search, and borrow available books
- My loans: due dates, days left or days overdue, return books, see past loans and fines

**Rules enforced**
- Loans last 14 days; the fine is Rs 2 for each late day
- At most 3 books per member at a time
- A member with an overdue book can't borrow until it is returned
- A book can't be deleted while copies are on loan, and copies can't be set below the number on loan
- Passwords are stored hashed, never as plain text

## Database design

```
users   (user_id PK, name, email UNIQUE, password, role CHECK admin|user, joined_on)
books   (book_id PK, title, author, category, isbn UNIQUE, year CHECK, copies CHECK >= 0)
issues  (issue_id PK, user_id FK → users, book_id FK → books,
         issue_date, due_date, return_date NULL = still on loan, fine CHECK >= 0)
```

- **Relationships:** a user borrows many books and a book is borrowed by many users. This is a
  many-to-many relationship, resolved by the `issues` table, which records each loan.
- **Normalisation:** each fact is stored once. Available copies are not stored. They are
  calculated by the `book_stock` **view** (`copies − active loans`), so stock can never go out of sync.
- **Trigger:** `calc_fine` runs inside the database when `return_date` is set and works out the late fine.
- **Constraints used:** PRIMARY KEY, FOREIGN KEY (ON DELETE CASCADE), UNIQUE, NOT NULL, CHECK, DEFAULT.
- **Indexes** on `issues(user_id)` and `issues(book_id)` speed up joins.

The full DDL is in [`schema.sql`](schema.sql).

### SQL concepts used in the app (`app.py`)

| Concept | Where |
|---|---|
| INSERT / SELECT / UPDATE / DELETE | add book, list, edit, delete; issue and return |
| INNER JOIN (3 tables) | circulation list: issues ⋈ users ⋈ books |
| LEFT JOIN + GROUP BY | members page: members with zero loans still appear |
| Aggregates COUNT, SUM, COALESCE | overview figures, fines per member |
| Subquery | `book_stock` view counts active loans per book |
| LIKE pattern search | every search box |
| ORDER BY / LIMIT | most borrowed, recent activity |
| VIEW | `book_stock` |
| TRIGGER | `calc_fine` |
| Parameterised queries (`?`) | everywhere: protects against SQL injection |

## Project structure

```
app.py              Flask server: routes, rules, SQL queries
schema.sql          tables, view, trigger, indexes
static/style.css    styling
templates/          pages (Jinja2)
  auth.html, login.html, register.html
  app.html          sidebar layout shared by signed-in pages
  admin/            overview, books, book_form, members, loans, loan_form
  member/           catalogue, loans
```
