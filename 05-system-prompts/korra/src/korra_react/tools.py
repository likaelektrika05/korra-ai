"""
Filename: tools.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 12 (System Prompts)

The APPROVED capabilities: four read-only tools over the Project 10 student
database (PostgreSQL). There is no write tool here at all; writes belong to
the supervised Project 11 workflow.

Defense in depth: the system prompt tells Korra that students may only see
their own GPA and grades, AND the tool layer enforces it. When the caller's
role is student, other students' gpa/grade fields are removed from tool
results before the model ever sees them.

Every statement is parameterized. Every failure comes back as data:
{"status": "error", "error": ...}.
"""

from __future__ import annotations

import contextvars
import os
from contextlib import closing

import psycopg
from langchain_core.tools import tool

# Who is asking (set by the graph for each request)
CURRENT_ROLE: contextvars.ContextVar[str] = contextvars.ContextVar("role", default="student")
CURRENT_EMAIL: contextvars.ContextVar[str | None] = contextvars.ContextVar("email", default=None)


def _connect():
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5)


def _query(sql: str, params: tuple = ()) -> list[dict]:
    with closing(_connect()) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        names = [c[0] for c in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]


def _privacy_filter(rows: list[dict]) -> tuple[list[dict], bool]:
    """Students see their own gpa/grade only. Returns (rows, redacted?)."""
    if CURRENT_ROLE.get() == "instructor":
        return rows, False
    me = (CURRENT_EMAIL.get() or "").lower()
    redacted = False
    out = []
    for r in rows:
        if r.get("email", "").lower() != me and ("gpa" in r or "grade" in r):
            r = {k: v for k, v in r.items() if k not in ("gpa", "grade")}
            redacted = True
        out.append(r)
    return out, redacted


def _fail(exc: Exception) -> dict:
    # Error type only: no connection string, host or password in the observation
    return {"status": "error", "error": f"student database unavailable ({type(exc).__name__})"}


@tool
def list_students(reason: str, major: str = "", min_gpa: float | None = None) -> dict:
    """
    List students, optionally filtered by major (exact, case-insensitive) and/or minimum GPA.

    Args:
        reason: One short public sentence explaining why this step is needed
        major: Major to filter by, or empty for all majors
        min_gpa: Minimum GPA from 0.0 to 4.0, or null for no GPA filter
    """
    if min_gpa is not None and not 0.0 <= float(min_gpa) <= 4.0:
        return {"status": "error", "error": "min_gpa must be between 0.0 and 4.0"}
    if min_gpa is not None and CURRENT_ROLE.get() != "instructor":
        return {"status": "refused", "error": "students may not filter other students by GPA"}
    sql = "SELECT name, email, major, gpa FROM students WHERE 1=1"
    params: list = []
    if major.strip():
        sql += " AND lower(major) = lower(%s)"
        params.append(major.strip())
    if min_gpa is not None:
        sql += " AND gpa >= %s"
        params.append(float(min_gpa))
    try:
        rows, redacted = _privacy_filter(_query(sql + " ORDER BY name", tuple(params)))
    except psycopg.Error as exc:
        return _fail(exc)
    return {"status": "success", "count": len(rows), "students": rows,
            "privacy_redacted": redacted}


@tool
def get_student(reason: str, email: str) -> dict:
    """
    Get one student by email, including the courses they are enrolled in.

    Args:
        reason: One short public sentence explaining why this step is needed
        email: The student's email address
    """
    email = (email or "").strip().lower()
    if "@" not in email:
        return {"status": "error", "error": "a full email address is required"}
    try:
        found = _query("SELECT id, name, email, major, gpa, enrollment_date FROM students "
                       "WHERE lower(email) = %s", (email,))
        if not found:
            return {"status": "not_found", "message": f"no student with email {email}"}
        student = found[0]
        student["enrollments"] = _query(
            "SELECT c.course_code, c.course_name, e.grade, e.semester FROM enrollments e "
            "JOIN courses c ON c.id = e.course_id WHERE e.student_id = %s "
            "ORDER BY c.course_code", (student.pop("id"),))
    except psycopg.Error as exc:
        return _fail(exc)
    if CURRENT_ROLE.get() != "instructor" and email != (CURRENT_EMAIL.get() or "").lower():
        student.pop("gpa", None)
        for e in student["enrollments"]:
            e.pop("grade", None)
        return {"status": "success", "student": student, "privacy_redacted": True}
    return {"status": "success", "student": student, "privacy_redacted": False}


@tool
def list_courses(reason: str) -> dict:
    """
    List every course with its code, name, credits and instructor.

    Args:
        reason: One short public sentence explaining why this step is needed
    """
    try:
        rows = _query("SELECT course_code, course_name, credits, instructor FROM courses "
                      "ORDER BY course_code")
    except psycopg.Error as exc:
        return _fail(exc)
    return {"status": "success", "count": len(rows), "courses": rows}


@tool
def course_roster(reason: str, course_code: str) -> dict:
    """
    List the students enrolled in one course, by course code (for example COMPE475).

    Args:
        reason: One short public sentence explaining why this step is needed
        course_code: Course code, for example COMPE475
    """
    code = (course_code or "").strip().upper().replace(" ", "")
    try:
        exists = _query("SELECT course_name FROM courses WHERE upper(course_code) = %s", (code,))
        if not exists:
            return {"status": "not_found", "message": f"no course with code {code}"}
        rows = _query(
            "SELECT s.name, s.email, e.grade, e.semester FROM enrollments e "
            "JOIN students s ON s.id = e.student_id JOIN courses c ON c.id = e.course_id "
            "WHERE upper(c.course_code) = %s ORDER BY s.name", (code,))
    except psycopg.Error as exc:
        return _fail(exc)
    rows, redacted = _privacy_filter(rows)
    return {"status": "success", "course_code": code, "course_name": exists[0]["course_name"],
            "count": len(rows), "students": rows, "privacy_redacted": redacted}


APPROVED_TOOLS = [list_students, get_student, list_courses, course_roster]
APPROVED_NAMES = {t.name for t in APPROVED_TOOLS}
