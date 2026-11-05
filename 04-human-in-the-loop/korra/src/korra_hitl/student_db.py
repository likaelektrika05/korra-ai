"""
Filename: student_db.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 11 (Human in the Loop)

The Project 10 student-database tools, on PostgreSQL.

    read_student_records   UNPROTECTED  - runs as soon as the model asks
    save_student_record    PROTECTED    - the model may only PROPOSE it; the
                                          insert runs from save_database_node
                                          after an authorized human decision

The tool object for save_student_record is bound to the model so it can
propose the call with arguments, but the graph never sends that call to a
ToolNode. The real insert is insert_student(), called inside the decision
transaction (oversight.execute_approved_save) so it can happen only once.

Every statement is parameterized; the model supplies values, never SQL.
"""

from __future__ import annotations

import os
import re
from contextlib import closing
from datetime import date

import psycopg
from langchain_core.tools import tool

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDENT_FIELDS = ("name", "email", "major", "gpa", "enrollment_date")


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5)


def _rows(cur) -> list[dict]:
    names = [c[0] for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


# ============================================================
# VALIDATION (shared by the reviewer's revisions and the insert)
# ============================================================

def validate_student(args: dict) -> tuple[dict, list[str]]:
    """Return (normalized fields, problems). Empty problems = valid."""
    name = str(args.get("name", "") or "").strip()
    email = str(args.get("email", "") or "").strip().lower()
    major = str(args.get("major", "") or "").strip()
    problems = []
    if not name:
        problems.append("name is empty")
    if not EMAIL_RE.match(email):
        problems.append("email is not a valid address")
    if not major:
        problems.append("major is empty")
    try:
        gpa = float(args.get("gpa"))
        if not 0.0 <= gpa <= 4.0:
            problems.append("GPA must be between 0.0 and 4.0")
    except (TypeError, ValueError):
        gpa = None
        problems.append("GPA is not a number")
    enrolled = str(args.get("enrollment_date", "") or "")
    try:
        date.fromisoformat(enrolled)
    except ValueError:
        problems.append("enrollment_date must be YYYY-MM-DD")
    return ({"name": name, "email": email, "major": major, "gpa": gpa,
             "enrollment_date": enrolled}, problems)


def insert_student(cur, args: dict) -> dict:
    """Insert one student on an open cursor. Result is data, never an exception."""
    fields, problems = validate_student(args)
    if problems:
        return {"status": "refused", "reasons": problems}
    cur.execute("SELECT id FROM students WHERE lower(email) = %s", (fields["email"],))
    if cur.fetchone():
        return {"status": "refused",
                "reasons": [f"a student with email {fields['email']} already exists"]}
    cur.execute(
        "INSERT INTO students (name, email, major, gpa, enrollment_date) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (fields["name"], fields["email"], fields["major"], fields["gpa"],
         fields["enrollment_date"]))
    return {"status": "saved", "student_id": cur.fetchone()[0], "student": fields}


def decision_context(args: dict) -> dict:
    """Relevant database state shown to the reviewer next to the proposal."""
    fields, problems = validate_student(args)
    try:
        with closing(connect()) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM students")
            count = cur.fetchone()[0]
            cur.execute("SELECT id, name FROM students WHERE lower(email) = %s",
                        (fields["email"],))
            clash = cur.fetchone()
        return {"students_on_record": count,
                "email_already_used_by": f"#{clash[0]} {clash[1]}" if clash else None,
                "validation_problems": problems}
    except psycopg.Error as exc:
        return {"database": f"unavailable ({type(exc).__name__})",
                "validation_problems": problems}


# ============================================================
# TOOLS BOUND TO THE MODEL
# ============================================================

@tool
def read_student_records(email: str = "") -> dict:
    """
    Read students from the student database. Leave email empty to list
    every student, or give an email to look one up.

    Args:
        email: Student email to look up, or empty for all students
    """
    email = (email or "").strip().lower()
    try:
        with closing(connect()) as conn:
            cur = conn.cursor()
            if not email:
                cur.execute("SELECT id, name, email, major, gpa, enrollment_date "
                            "FROM students ORDER BY id")
                students = _rows(cur)
                return {"status": "success", "count": len(students), "students": students}
            cur.execute("SELECT id, name, email, major, gpa, enrollment_date "
                        "FROM students WHERE lower(email) = %s", (email,))
            found = _rows(cur)
            if not found:
                return {"status": "not_found", "message": f"No student with email {email}."}
            return {"status": "success", "student": found[0]}
    except psycopg.Error as exc:
        return {"status": "error", "error": f"Student database unavailable: {type(exc).__name__}"}


@tool
def save_student_record(name: str, email: str, major: str, gpa: float,
                        enrollment_date: str) -> dict:
    """
    Propose saving one new student. This is a protected action: it pauses
    for a human reviewer, who approves, rejects, revises or cancels it.

    Args:
        name: Full name
        email: Email address; must be unique
        major: Major, for example Computer Engineering
        gpa: GPA between 0.0 and 4.0
        enrollment_date: Date in YYYY-MM-DD format
    """
    # Never executed directly: the graph routes this call to approval_gate
    raise RuntimeError("save_student_record runs only after human approval")
