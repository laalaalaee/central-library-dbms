-- Central Library : Library Management System
-- Database schema (SQLite)

CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    email      TEXT    NOT NULL UNIQUE,
    password   TEXT    NOT NULL,
    role       TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    joined_on  TEXT    NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS books (
    book_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    author     TEXT    NOT NULL,
    category   TEXT,
    isbn       TEXT    UNIQUE,
    year       INTEGER CHECK (year BETWEEN 1450 AND 2100),
    copies     INTEGER NOT NULL DEFAULT 1 CHECK (copies >= 0)
);

CREATE TABLE IF NOT EXISTS issues (
    issue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    book_id     INTEGER NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    issue_date  TEXT    NOT NULL,
    due_date    TEXT    NOT NULL,
    return_date TEXT,
    fine        INTEGER NOT NULL DEFAULT 0 CHECK (fine >= 0),
    CHECK (due_date >= issue_date)
);

CREATE INDEX IF NOT EXISTS idx_issues_user ON issues(user_id);
CREATE INDEX IF NOT EXISTS idx_issues_book ON issues(book_id);

-- Available copies are derived, never stored, so stock can't drift out of sync.
CREATE VIEW IF NOT EXISTS book_stock AS
SELECT b.*,
       b.copies - (SELECT COUNT(*) FROM issues i
                   WHERE i.book_id = b.book_id AND i.return_date IS NULL) AS available
FROM books b;

-- Fine of Rs 2 per late day, worked out by the database the moment a book is returned.
CREATE TRIGGER IF NOT EXISTS calc_fine
AFTER UPDATE OF return_date ON issues
WHEN NEW.return_date IS NOT NULL AND OLD.return_date IS NULL
BEGIN
    UPDATE issues
    SET fine = MAX(0, CAST(julianday(NEW.return_date) - julianday(NEW.due_date) AS INTEGER)) * 2
    WHERE issue_id = NEW.issue_id;
END;
