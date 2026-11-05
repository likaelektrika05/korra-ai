"""
Filename: add_student.py
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
    Manually add a new student record to the SQLite database.
    Demonstrates the SQL INSERT operation through an
    interactive command-line interface:
        - Collects student information from user input
        - Inserts the record into the students table
        - Handles duplicate email errors gracefully

    Exemption claimed by this file:
        LG-01 - Console Application: print() carries the prompts and the
                results the student reads. Diagnostics, warnings and errors
                use the logger.

Usage Instructions:
    1. Run create_db.py first to create the database
    2. Run the script: python add_student.py
    3. Follow the prompts to enter student information
    The exit status is 0 when a student is added and 1 when none is.
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

# Anchored to this file so the same database is used no matter which
# directory the student runs the command from
DB_PATH = Path(__file__).resolve().parent / "test_database.db"

# Only the students table is read or written here
REQUIRED_TABLES = ("students",)

MIN_GPA = 0.0
MAX_GPA = 4.0


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
# DATABASE OPERATIONS
# ============================================================

def tables_ready(conn: sqlite3.Connection, required: tuple[str, ...]) -> bool:
    """
    Report whether create_db.py has already built the tables this script uses.

    Checking the tables an operation actually touches is what separates "the
    database has not been set up" from every other database failure, so the
    student is only told to run create_db.py when that is really the problem.

    Args:
        conn: Open connection to the database being checked
        required: Names of the tables the calling operation reads or writes

    Raises:
        sqlite3.Error: If the database file cannot be read at all.

    Returns:
        bool: True when every required table exists
    """

    # Only the placeholders are built into the text; the names are bound
    placeholders = ", ".join("?" for _ in required)
    cursor = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type = 'table' AND name IN (%s)" % placeholders, required)
    return cursor.fetchone()[0] == len(required)


def email_taken(conn: sqlite3.Connection, email: str) -> bool:
    """
    Report whether a student with this email is already on file.

    Checked before inserting so the common refusal can name its real reason
    rather than guessing. It does not rule the violation out: another
    connection can insert the same email between this check and the insert,
    so the caller still handles a UNIQUE violation.

    Args:
        conn: Open connection to the database being checked
        email: Email address to look for

    Raises:
        sqlite3.Error: If the query cannot be executed.

    Returns:
        bool: True when the email is already present
    """
    cursor = conn.execute("SELECT 1 FROM students WHERE email = ?", (email,))
    return cursor.fetchone() is not None


def add_student(name: str, email: str, major: str, gpa: float,
                enrollment_date: str) -> bool:
    """
    Store one new student row and report whether it was stored.

    Every database failure is reported through the logger and turned into a
    False result, so no caller of this function sees an exception.

    Args:
        name: Student's full name
        email: Student's email address
        major: Student's major
        gpa: Student's GPA (0.0-4.0)
        enrollment_date: Enrollment date (YYYY-MM-DD)

    Returns:
        bool: True if the row was inserted, False if it was not
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            if not tables_ready(conn, REQUIRED_TABLES):
                logger.error("No students table in %s; run create_db.py first",
                             DB_PATH)
                return False

            if email_taken(conn, email):
                logger.error("A student with email %s is already on file", email)
                return False

            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO students (name, email, major, gpa, enrollment_date)
            VALUES (?, ?, ?, ?, ?)
            ''', (name, email, major, gpa, enrollment_date))

            conn.commit()

            # LG-01 exemption - Console Application: the confirmation is the
            # result the student reads, so it goes to stdout
            print("[SUCCESS] Added student: %s" % name)
            print("Student ID: %s" % cursor.lastrowid)
            return True

    # Any constraint the table declares can land here: the NOT NULL on name,
    # or the UNIQUE email when another connection claimed it after the check
    except sqlite3.IntegrityError as error:
        logger.error("The database refused the record: %s", error)
        return False

    except sqlite3.Error as error:
        logger.error("Could not write to the database at %s: %s", DB_PATH, error)
        return False


def count_students() -> int | None:
    """
    Report how many students the table currently holds.

    Every database failure is reported through the logger and turned into a
    None result, so no caller of this function sees an exception.

    Returns:
        int | None: The number of students, or None if it could not be read
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            if not tables_ready(conn, REQUIRED_TABLES):
                return None

            cursor = conn.execute("SELECT COUNT(*) FROM students")
            return cursor.fetchone()[0]
    except sqlite3.Error as error:
        logger.error("Could not count the students in %s: %s", DB_PATH, error)
        return None


# ============================================================
# USER INPUT
# ============================================================

def read_gpa() -> float:
    """
    Ask for a GPA until the answer is a number inside the allowed range.

    Reprompting rather than failing keeps a mistyped entry from ending the
    session, which a bare float() call would do.

    Raises:
        EOFError: If input ends before an acceptable GPA is given.

    Returns:
        float: A GPA between MIN_GPA and MAX_GPA
    """
    while True:
        entered = input("GPA (0.0-4.0): ").strip()

        try:
            gpa = float(entered)

        # A reprompt is part of the prompt flow, not a diagnostic
        except ValueError:
            print("Please enter a number, for example 3.5")
            continue

        if not MIN_GPA <= gpa <= MAX_GPA:
            print("GPA must be between %s and %s" % (MIN_GPA, MAX_GPA))
            continue

        return gpa


# ============================================================
# MAIN PROGRAM
# ============================================================

def main() -> int:
    """
    Collect one student's details and store them.

    Returns:
        int: 0 when a student was added, 1 when none was added or the
        entry was cancelled
    """
    print("=== Add New Student ===\n")

    # Ctrl+C, Ctrl+Z, or redirected input that ends before the last answer
    # would otherwise end the session with a traceback
    try:
        name = input("Student name: ")
        email = input("Email: ")
        major = input("Major: ")
        gpa = read_gpa()
        enrollment_date = input("Enrollment date (YYYY-MM-DD): ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No student was added.")
        return 1

    added = add_student(name, email, major, gpa, enrollment_date)

    total = count_students()
    if total is not None:
        print("\nTotal students in database: %s" % total)

    return 0 if added else 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    configure_logging()
    sys.exit(main())
