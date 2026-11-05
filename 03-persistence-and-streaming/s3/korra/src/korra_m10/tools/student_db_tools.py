"""
Filename: student_db_tools.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026
Project: Project 10 - Korra: Persistence and Streaming (Sections 3 and 4)

Description:
    Two LangGraph tools over the Module 10 student database
    (students / courses / enrollments, built by create_db.py):

        read_student_records(email="")  - list every student, or look one up
        save_student_record(...)        - add one new student

    Safety rules:
      * Every statement is parameterized. The model only supplies VALUES;
        it never writes SQL, so nothing it types can change a query.
      * Failures come back as data, never as exceptions:
            {"status": "refused",   ...}  invalid input or email already used
            {"status": "not_found", ...}  no student with that email
            {"status": "error",     ...}  the database cannot be opened/read
        so the model can explain what happened.

    Connection (the ONLY thing that differs between Section 3 and 4):
      * DATABASE_URL not set  -> SQLite file test_database.db beside this
                                 module (Section 3). Opened read/write but
                                 never created: a missing file is an error.
      * DATABASE_URL set      -> PostgreSQL through psycopg (Section 4,
                                 the "db" container). Same SQL, same results.
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from langchain_core.tools import tool


DB_PATH = Path(os.getenv("STUDENT_DB_PATH",
                         Path(__file__).resolve().parent / "test_database.db"))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ============================================================
# CONNECTION LAYER
# ============================================================

def _using_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL"))


def _connect():
    """Open the configured database. Raises on failure (callers turn it into data)."""
    if _using_postgres():
        import psycopg
        return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5)
    # mode=rw: open an existing file only; never create an empty database
    return sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=rw", uri=True)


def _sql(statement: str) -> str:
    """The statements are written with ? placeholders; psycopg uses %s."""
    return statement.replace("?", "%s") if _using_postgres() else statement


def _db_errors() -> tuple:
    errors = [sqlite3.Error, OSError]
    if _using_postgres():
        import psycopg
        errors.append(psycopg.Error)
    return tuple(errors)


def _rows(cursor) -> list[dict]:
    names = [col[0] for col in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _unavailable(exc: Exception) -> dict:
    backend = "PostgreSQL" if _using_postgres() else f"SQLite file {DB_PATH.name}"
    return {"status": "error",
            "error": f"Student database unavailable ({backend}): {exc}"}


# ============================================================
# TOOLS
# ============================================================

@tool
def read_student_records(email: str = "") -> dict:
    """
    Read students from the student database.

    Leave email empty to list every student. Give an email to look up one
    student, including the courses they are enrolled in.

    Args:
        email: Student email to look up, or empty for all students
    """
    email = (email or "").strip().lower()
    try:
        with closing(_connect()) as conn:
            cur = conn.cursor()
            if not email:
                cur.execute(_sql(
                    "SELECT id, name, email, major, gpa, enrollment_date "
                    "FROM students ORDER BY id"))
                students = _rows(cur)
                return {"status": "success", "count": len(students),
                        "students": students}

            cur.execute(_sql(
                "SELECT id, name, email, major, gpa, enrollment_date "
                "FROM students WHERE lower(email) = ?"), (email,))
            found = _rows(cur)
            if not found:
                return {"status": "not_found",
                        "message": f"No student with email {email}."}
            student = found[0]
            cur.execute(_sql(
                "SELECT c.course_code, c.course_name, e.grade, e.semester "
                "FROM enrollments e JOIN courses c ON c.id = e.course_id "
                "WHERE e.student_id = ? ORDER BY c.course_code"), (student["id"],))
            student["enrollments"] = _rows(cur)
            return {"status": "success", "student": student}
    except _db_errors() as exc:
        return _unavailable(exc)


@tool
def save_student_record(name: str, email: str, major: str, gpa: float,
                        enrollment_date: str) -> dict:
    """
    Save one new student to the student database.

    All five fields are required. Ask the user for any that are missing
    instead of guessing.

    Args:
        name: Full name
        email: Email address; must be unique
        major: Major, for example Computer Engineering
        gpa: GPA between 0.0 and 4.0
        enrollment_date: Date in YYYY-MM-DD format
    """
    name, major = (name or "").strip(), (major or "").strip()
    email = (email or "").strip().lower()

    problems = []
    if not name:
        problems.append("name is empty")
    if not EMAIL_RE.match(email):
        problems.append("email is not a valid address")
    if not major:
        problems.append("major is empty")
    try:
        gpa = float(gpa)
        if not 0.0 <= gpa <= 4.0:
            problems.append("GPA must be between 0.0 and 4.0")
    except (TypeError, ValueError):
        problems.append("GPA is not a number")
    try:
        date.fromisoformat(str(enrollment_date))
    except ValueError:
        problems.append("enrollment_date must be YYYY-MM-DD")
    if problems:
        return {"status": "refused", "reasons": problems}

    try:
        with closing(_connect()) as conn:
            cur = conn.cursor()
            cur.execute(_sql("SELECT id FROM students WHERE lower(email) = ?"),
                        (email,))
            if cur.fetchone():
                return {"status": "refused",
                        "reasons": [f"a student with email {email} already exists"]}
            insert = ("INSERT INTO students (name, email, major, gpa, enrollment_date) "
                      "VALUES (?, ?, ?, ?, ?)")
            values = (name, email, major, gpa, str(enrollment_date))
            if _using_postgres():
                cur.execute(_sql(insert) + " RETURNING id", values)
                new_id = cur.fetchone()[0]
            else:
                cur.execute(insert, values)
                new_id = cur.lastrowid
            conn.commit()
            return {"status": "saved", "student_id": new_id,
                    "student": {"name": name, "email": email, "major": major,
                                "gpa": gpa, "enrollment_date": str(enrollment_date)}}
    except _db_errors() as exc:
        # A UNIQUE violation from a race still comes back as data
        if "unique" in str(exc).lower():
            return {"status": "refused",
                    "reasons": [f"a student with email {email} already exists"]}
        return _unavailable(exc)
