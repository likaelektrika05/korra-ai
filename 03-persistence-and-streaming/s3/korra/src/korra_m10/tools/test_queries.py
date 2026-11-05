"""
Filename: test_queries.py
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
    Test various SQL queries using Python and SQLite.
    Demonstrates how to retrieve data from a relational
    database using different query techniques:
        - SELECT all records from a table
        - WHERE clause filtering by column value
        - ORDER BY for sorting results
        - JOIN to combine data across multiple tables

    Each query is run on its own, so one failure reports itself and the
    remaining queries still run.

    Exemption claimed by this file:
        LG-01 - Console Application: print() carries the result tables the
                student reads. Diagnostics, warnings and errors use the
                logger.

Usage Instructions:
    1. Run create_db.py first to create the database
    2. Run the script: python test_queries.py
    3. Review the output for each query result
    The exit status is 0 when every query ran and 1 when any did not.
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

# Anchored to this file so the same database is read no matter which
# directory the student runs the command from
DB_PATH = Path(__file__).resolve().parent / "test_database.db"

# Query 4 joins all three tables, so all three have to exist
REQUIRED_TABLES = ("students", "courses", "enrollments")

# Width of the rules drawn above and below each result table
DIVIDER_WIDTH = 60

QUERIES = [
    (
        "Query 1: All Students",
        "SELECT * FROM students"
    ),
    (
        "Query 2: Computer Science Students",
        "SELECT name, gpa FROM students WHERE major = 'Computer Science'"
    ),
    (
        "Query 3: Students with GPA > 3.7",
        "SELECT name, major, gpa FROM students WHERE gpa > 3.7 ORDER BY gpa DESC"
    ),
    (
        "Query 4: Students in COMPE 475",
        """
        SELECT s.name, e.grade
        FROM students s
        JOIN enrollments e ON s.id = e.student_id
        JOIN courses c ON e.course_id = c.id
        WHERE c.course_code = 'COMPE475'
        """
    )
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
# QUERY DISPLAY
# ============================================================

def run_query(cursor: sqlite3.Cursor, title: str, query: str) -> bool:
    """
    Execute and display query results in a formatted table.

    A failing query is reported through the logger and turned into a False
    result, so one bad query does not stop the ones after it.

    Args:
        cursor: SQLite cursor object
        title: Description of the query
        query: SQL query string

    Returns:
        bool: True if the query ran, False if the database refused it
    """

    # LG-01 exemption - Console Application: the heading and the result table
    # are the program's output, so they go to stdout
    print("\n%s" % ('=' * DIVIDER_WIDTH))
    print("%s" % title)
    print('=' * DIVIDER_WIDTH)

    # Reading the rows is inside the handler as well as running the query,
    # because SQLite can also fail partway through fetching them
    try:
        cursor.execute(query)

        # The cursor.description attribute carries one entry per selected
        # column, which is the only place the column names of a SELECT * are
        # available
        columns = [description[0] for description in cursor.description]
        results = cursor.fetchall()
    except sqlite3.Error as error:
        logger.error("Query failed (%s): %s", title, error)
        return False

    print(" | ".join(columns))
    print('-' * DIVIDER_WIDTH)

    for row in results:
        print(" | ".join(str(item) for item in row))

    print("\nRows returned: %s" % len(results))
    return True


# ============================================================
# MAIN PROGRAM
# ============================================================

def main() -> int:
    """
    Run each sample query in turn and show what it returned.

    Returns:
        int: 0 when every query ran, 1 when any query failed or the
        database could not be opened
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            if not tables_ready(conn, REQUIRED_TABLES):
                logger.error("Tables missing from %s; run create_db.py first",
                             DB_PATH)
                return 1

            cursor = conn.cursor()
            failures = [title for title, query in QUERIES
                        if not run_query(cursor, title, query)]
    except sqlite3.Error as error:
        logger.error("Could not read the database at %s: %s", DB_PATH, error)
        return 1

    if failures:
        logger.error("%s of %s queries could not run", len(failures), len(QUERIES))
        return 1

    print("\n[SUCCESS] All queries completed successfully!")
    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    configure_logging()
    sys.exit(main())
