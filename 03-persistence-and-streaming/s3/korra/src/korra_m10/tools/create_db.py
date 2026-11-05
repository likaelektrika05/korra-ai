"""
Filename: create_db.py
Author: Professor Denis O. Núñez
Email: donunez@programmingjourneys.com
Organization: Programming Journeys
Project: Project 10 - Korra: Persistence and Streaming
Module: Module 10 - Memory System Organization
Layer: Application - Database
Date Created: March 10, 2026
Date Modified: October 10, 2026
Version: 1.1
License: Educational Use

Requirements:
    Standard library only

Description:
    Create and populate a sample SQLite database for testing.
    Demonstrates how to build a relational database with
    multiple tables and relationships:
        - Students table with personal and academic info
        - Courses table with course details
        - Enrollments table linking students to courses

    Running the script again is safe. Students and courses are protected by
    their unique email and course code, and each enrollment is checked before
    it is inserted, so the sample data is never duplicated.

    Foreign keys are enforced on this connection, so no change made here can
    leave an enrollment pointing at a student or course that does not exist.
    Rows already orphaned by earlier runs are not repaired; PRAGMA
    foreign_key_check reports those.

    Exemption claimed by this file:
        LG-01 - Console Application: print() reports the record counts the
                student reads. Diagnostics, warnings and errors use the
                logger.

Usage Instructions:
    1. Run the script: python create_db.py
    2. A file called test_database.db will be created beside this script
    3. Use SQLite Viewer extension in VS Code to inspect the data
    The exit status is 0 when the database is built and 1 when it is not.
"""


# ============================================================
# IMPORTS
# ============================================================

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


# ============================================================
# CONSTANTS
# ============================================================

# Anchored to this file so the database is created beside the script instead
# of in whatever directory the student happened to run the command from
DB_PATH = Path(__file__).resolve().parent / "test_database.db"

STUDENTS_DATA = [
    ('Alice Johnson', 'alice@sdsu.edu', 'Computer Science', 3.8, '2024-08-20'),
    ('Bob Smith', 'bob@sdsu.edu', 'Mathematics', 3.5, '2024-08-20'),
    ('Carol Davis', 'carol@sdsu.edu', 'Computer Science', 3.9, '2024-08-20'),
    ('David Wilson', 'david@sdsu.edu', 'Engineering', 3.7, '2024-08-20'),
    ('Eve Martinez', 'eve@sdsu.edu', 'Mathematics', 3.6, '2024-08-20')
]

COURSES_DATA = [
    ('COMPE475', 'Microprocessors', 3, 'Prof. Núñez'),
    ('CS101', 'Introduction to Programming', 4, 'Prof. Smith'),
    ('MATH150', 'Calculus I', 4, 'Prof. Johnson'),
    ('CS201', 'Data Structures', 3, 'Prof. Davis'),
    ('MATH210', 'Linear Algebra', 3, 'Prof. Wilson')
]

# Identified by email and course code rather than by row number, because
# AUTOINCREMENT never reuses an id: once a student has been removed, the
# positions 1 through 5 no longer name the people they originally named
ENROLLMENTS_DATA = [
    ('alice@sdsu.edu', 'COMPE475', 'A', 'Spring 2026'),
    ('alice@sdsu.edu', 'CS101', 'A-', 'Spring 2026'),
    ('bob@sdsu.edu', 'COMPE475', 'B+', 'Spring 2026'),
    ('bob@sdsu.edu', 'MATH150', 'A', 'Spring 2026'),
    ('carol@sdsu.edu', 'COMPE475', 'A', 'Spring 2026'),
    ('carol@sdsu.edu', 'CS201', 'A', 'Spring 2026'),
    ('david@sdsu.edu', 'CS101', 'B', 'Spring 2026'),
    ('david@sdsu.edu', 'MATH210', 'B+', 'Spring 2026'),
    ('eve@sdsu.edu', 'MATH150', 'A-', 'Spring 2026'),
    ('eve@sdsu.edu', 'MATH210', 'A', 'Spring 2026')
]


# ============================================================
# LOGGER
# ============================================================

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """
    Set up log output for a direct run of this script.

    Called from the main guard rather than at import time, because
    basicConfig reconfigures the root logger for the whole process and a
    module must not do that to whatever imported it.

    Returns:
        None
    """

    # No timestamp: a student reads these at a prompt, rather than collecting
    # them from a long-running service
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ============================================================
# TABLE CREATION
# ============================================================

def create_tables(cursor: sqlite3.Cursor) -> None:
    """
    Define the three tables the sample database is built from.

    Args:
        cursor: Open cursor on the database being built

    Raises:
        sqlite3.Error: If the statements cannot be executed.

    Returns:
        None
    """
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        major TEXT,
        gpa REAL,
        enrollment_date TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT UNIQUE NOT NULL,
        course_name TEXT NOT NULL,
        credits INTEGER,
        instructor TEXT
    )
    ''')

    # Two foreign keys make this the join table of a many-to-many relationship
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        course_id INTEGER,
        grade TEXT,
        semester TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    ''')


# ============================================================
# SAMPLE DATA
# ============================================================

def find_student_id(cursor: sqlite3.Cursor, email: str) -> int | None:
    """
    Find which row a student's email belongs to.

    Args:
        cursor: Open cursor on the database being built
        email: Email address to look for

    Raises:
        sqlite3.Error: If the query cannot be executed.

    Returns:
        int | None: The student's id, or None when no student has that email
    """
    cursor.execute("SELECT id FROM students WHERE email = ?", (email,))
    result = cursor.fetchone()
    return result[0] if result else None


def find_course_id(cursor: sqlite3.Cursor, course_code: str) -> int | None:
    """
    Find which row a course code belongs to.

    Args:
        cursor: Open cursor on the database being built
        course_code: Course code to look for

    Raises:
        sqlite3.Error: If the query cannot be executed.

    Returns:
        int | None: The course's id, or None when no course has that code
    """
    cursor.execute("SELECT id FROM courses WHERE course_code = ?", (course_code,))
    result = cursor.fetchone()
    return result[0] if result else None


def insert_students(cursor: sqlite3.Cursor) -> None:
    """
    Add the sample students, skipping any email already in the table.

    Args:
        cursor: Open cursor on the database being built

    Raises:
        sqlite3.Error: If the insert cannot be executed.

    Returns:
        None
    """

    # OR IGNORE relies on the UNIQUE email, so a repeat run adds nobody twice
    cursor.executemany('''
    INSERT OR IGNORE INTO students (name, email, major, gpa, enrollment_date)
    VALUES (?, ?, ?, ?, ?)
    ''', STUDENTS_DATA)


def insert_courses(cursor: sqlite3.Cursor) -> None:
    """
    Add the sample courses, skipping any code already in the table.

    Args:
        cursor: Open cursor on the database being built

    Raises:
        sqlite3.Error: If the insert cannot be executed.

    Returns:
        None
    """

    # OR IGNORE relies on the UNIQUE course_code, as insert_students does
    cursor.executemany('''
    INSERT OR IGNORE INTO courses (course_code, course_name, credits, instructor)
    VALUES (?, ?, ?, ?)
    ''', COURSES_DATA)


def insert_enrollments(cursor: sqlite3.Cursor) -> None:
    """
    Pair each sample student with the courses they take this semester.

    Every pairing is checked before it is added. The enrollments table has no
    unique constraint, so OR IGNORE has nothing to ignore there and a second
    run would otherwise append the whole sample set a second time.

    Args:
        cursor: Open cursor on the database being built

    Raises:
        sqlite3.Error: If a lookup or insert cannot be executed.

    Returns:
        None
    """
    for email, course_code, grade, semester in ENROLLMENTS_DATA:
        student_id = find_student_id(cursor, email)
        course_id = find_course_id(cursor, course_code)

        if student_id is None or course_id is None:
            logger.warning("Skipped enrollment: no student %s or no course %s",
                           email, course_code)
            continue

        cursor.execute('''
        SELECT 1 FROM enrollments
        WHERE student_id = ? AND course_id = ? AND semester = ?
        ''', (student_id, course_id, semester))

        if cursor.fetchone():
            continue

        cursor.execute('''
        INSERT INTO enrollments (student_id, course_id, grade, semester)
        VALUES (?, ?, ?, ?)
        ''', (student_id, course_id, grade, semester))


# ============================================================
# VERIFICATION
# ============================================================

def report_counts(cursor: sqlite3.Cursor) -> None:
    """
    Print how many rows each table ended up holding.

    Args:
        cursor: Open cursor on the database being built

    Raises:
        sqlite3.Error: If a count cannot be executed.

    Returns:
        None
    """
    cursor.execute("SELECT COUNT(*) FROM students")

    # LG-01 exemption - Console Application: these counts are the result the
    # student reads, so they go to stdout rather than through the logger
    print("Students: %s" % cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM courses")
    print("Courses: %s" % cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM enrollments")
    print("Enrollments: %s" % cursor.fetchone()[0])


# ============================================================
# MAIN PROGRAM
# ============================================================

def main() -> int:
    """
    Build the sample database and report what it contains.

    Creating the tables is this script's job, so unlike the other scripts in
    this folder it never checks whether they already exist.

    Returns:
        int: 0 when the database was built, 1 when it could not be
    """

    # Wrapped in closing() because sqlite3's own context manager commits
    # or rolls back the transaction but leaves the connection open
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:

            # SQLite ignores the FOREIGN KEY clauses in create_tables() unless
            # this is set, and it is set per connection, not stored in the file
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            create_tables(cursor)
            insert_students(cursor)
            insert_courses(cursor)
            insert_enrollments(cursor)
            conn.commit()

            report_counts(cursor)
    except sqlite3.Error as error:
        logger.error("Could not create the database at %s: %s", DB_PATH, error)
        return 1

    print("\nDatabase created successfully: test_database.db")
    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    configure_logging()
    sys.exit(main())
