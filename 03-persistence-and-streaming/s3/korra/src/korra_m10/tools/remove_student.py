"""
Filename: remove_student.py
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
    Remove a student record from the SQLite database.
    Demonstrates the SQL DELETE operation through an
    interactive command-line interface:
        - Lists all current students for reference
        - Supports removal by student ID or email address
        - Handles foreign key cleanup by removing enrollments first

    Foreign keys are enforced on the connection, so the enrollments-first
    order is a rule the database checks rather than a convention.

    Exemption claimed by this file:
        LG-01 - Console Application: print() carries the prompts, the student
                table, and the results. Diagnostics, warnings and errors use
                the logger.

Usage Instructions:
    1. Run create_db.py first to create the database
    2. Run the script: python remove_student.py
    3. Choose removal method (by ID or by email)
    4. Enter the identifier for the student to remove
    The exit status is 0 when a student is removed and 1 when none is.
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

# Enrollments are deleted alongside the student, so both tables are needed
REQUIRED_TABLES = ("students", "enrollments")

# Width of the separator under the student table header
TABLE_WIDTH = 70


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
# READINESS
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


# ============================================================
# DISPLAY
# ============================================================

def list_students() -> int | None:
    """
    Show every student on file so the user can pick one to remove.

    Every database failure is reported through the logger and turned into a
    None result, so no caller of this function sees an exception.

    Returns:
        int | None: Number of students currently in the database, or None
        when the table could not be read
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            if not tables_ready(conn, REQUIRED_TABLES):
                logger.error("Tables missing from %s; run create_db.py first",
                             DB_PATH)
                return None

            cursor = conn.execute(
                "SELECT id, name, email, major FROM students ORDER BY id")
            students = cursor.fetchall()
    except sqlite3.Error as error:
        logger.error("Could not read the database at %s: %s", DB_PATH, error)
        return None

    # LG-01 exemption - Console Application: this table is the program's
    # output, so it goes to stdout rather than through the logger
    print("\n=== Current Students ===")
    print("%-5s %-20s %-25s %-20s" % ('ID', 'Name', 'Email', 'Major'))
    print("-" * TABLE_WIDTH)

    for student_id, name, email, major in students:

        # The major column is nullable, and "or" shows a student with no
        # major as a blank cell rather than the word None
        print("%-5s %-20s %-25s %-20s" % (student_id, name, email, major or ""))

    return len(students)


# ============================================================
# DATABASE OPERATIONS
# ============================================================

def _delete_student(cursor: sqlite3.Cursor, student_id: int) -> int:
    """
    Delete one student together with the enrollments pointing at them.

    Do not call directly; remove_student_by_id() and
    remove_student_by_email() use it after they have resolved the id.

    Args:
        cursor: Open cursor on the database being modified
        student_id: Row id of the student to delete

    Raises:
        sqlite3.Error: If either delete cannot be executed.

    Returns:
        int: Number of enrollment rows that were deleted alongside them
    """

    # Enrollments go first: with foreign keys enforced, deleting the student
    # while rows still point at them is refused
    cursor.execute("DELETE FROM enrollments WHERE student_id = ?", (student_id,))
    enrollments_removed = cursor.rowcount

    cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
    return enrollments_removed


def remove_student_by_id(student_id: int) -> bool:
    """
    Look a student up by row id and delete them.

    Every database failure is reported through the logger and turned into a
    False result, so no caller of this function sees an exception.

    Args:
        student_id: The student's database ID

    Returns:
        bool: True if student was removed, False if they were not
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            if not tables_ready(conn, REQUIRED_TABLES):
                logger.error("Tables missing from %s; run create_db.py first",
                             DB_PATH)
                return False

            # Enforced per connection, so the enrollments-first order in
            # _delete_student() is a rule the database now checks
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM students WHERE id = ?", (student_id,))
            result = cursor.fetchone()

            if not result:
                logger.error("No student found with ID %s", student_id)
                return False

            student_name = result[0]
            enrollments_removed = _delete_student(cursor, student_id)
            conn.commit()
    except sqlite3.Error as error:
        logger.error("Could not remove student ID %s: %s", student_id, error)
        return False

    print("[SUCCESS] Removed student: %s" % student_name)
    print("Also removed %s enrollment records" % enrollments_removed)
    return True


def remove_student_by_email(email: str) -> bool:
    """
    Look a student up by email address and delete them.

    Every database failure is reported through the logger and turned into a
    False result, so no caller of this function sees an exception.

    Args:
        email: The student's email address

    Returns:
        bool: True if student was removed, False if they were not
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            if not tables_ready(conn, REQUIRED_TABLES):
                logger.error("Tables missing from %s; run create_db.py first",
                             DB_PATH)
                return False

            # Enforced per connection, as in remove_student_by_id()
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            cursor.execute("SELECT id, name FROM students WHERE email = ?", (email,))
            result = cursor.fetchone()

            if not result:
                logger.error("No student found with email %s", email)
                return False

            student_id, student_name = result
            enrollments_removed = _delete_student(cursor, student_id)
            conn.commit()
    except sqlite3.Error as error:
        logger.error("Could not remove student %s: %s", email, error)
        return False

    print("[SUCCESS] Removed student: %s" % student_name)
    print("Also removed %s enrollment records" % enrollments_removed)
    return True


# ============================================================
# USER INPUT
# ============================================================

def read_student_id() -> int | None:
    """
    Ask for a student id until the answer is a whole number.

    Reprompting rather than failing keeps a mistyped entry from ending the
    session, which a bare int() call would do. An empty entry cancels.

    Raises:
        EOFError: If input ends before an answer is given.

    Returns:
        int | None: The id entered, or None if the user cancelled
    """
    while True:
        entered = input("Enter student ID to remove: ").strip()

        if not entered:
            return None

        try:
            return int(entered)

        # A reprompt is part of the prompt flow, not a diagnostic
        except ValueError:
            print("Please enter a whole number, or press Enter to cancel")


# ============================================================
# MAIN PROGRAM
# ============================================================

def main() -> int:
    """
    Show the roster, take a removal choice, and carry it out.

    Returns:
        int: 0 when a student was removed, 1 when none was removed, the
        roster could not be read, or the choice was cancelled
    """
    count = list_students()

    # None means the table could not be read and list_students already said
    # so; 0 means it was read and is genuinely empty
    if count is None:
        return 1

    if count == 0:
        print("\nNo students in database.")
        return 1

    print("\n=== Remove Student ===")
    print("Choose removal method:")
    print("1. Remove by ID")
    print("2. Remove by Email")

    # Ctrl+C, Ctrl+Z, or redirected input that ends before the last answer
    # would otherwise end the session with a traceback
    try:
        choice = input("\nYour choice (1 or 2): ").strip()

        if choice == "1":
            student_id = read_student_id()
            removed = (student_id is not None
                       and remove_student_by_id(student_id))
        elif choice == "2":
            email = input("Enter student email to remove: ")
            removed = remove_student_by_email(email)
        else:
            logger.error("Invalid removal choice: %s", choice)
            removed = False
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No student was removed.")
        return 1

    # Called on its own line: embedding it in the message hid the fact that
    # it reprints the whole table
    remaining = list_students()
    if remaining is not None:
        print("\nTotal students remaining: %s" % remaining)

    return 0 if removed else 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    configure_logging()
    sys.exit(main())
