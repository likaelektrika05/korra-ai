/**
 * Filename: test_file_stats.c
 * Author: Professor Denis O. Núñez
 * Email: donunez@programmingjourneys.com
 * Organization: Programming Journeys
 * Project: Project 07 - C Programming Project
 * Module: Module 07 - C Programming (Part I)
 * Layer: Application - Tools - Tests
 * Date Created: October 2, 2026
 * Date Modified: October 2, 2026
 * Version: 3.0
 * License: Educational Use
 *
 * Requirements:
 *     C standard library only
 *
 * Description:
 *     Automated tests for analyze_file(). Runs every normal, boundary, and
 *     invalid-input case, compares each result with its expected value,
 *     and prints PASS or FAIL per check. Exits with 0 only when every
 *     check passes, so `make test` fails whenever the tool is wrong. Links
 *     against file_stats.o and tests the analysis directly, which works the
 *     same on Windows and Linux. The usage error in main() is checked by
 *     running the program with `make demo`.
 *
 * Usage Instructions:
 *     Build and run through the project Makefile, from the project folder:
 *         make test
 */


// ============================================================
// INCLUDES
// ============================================================

#include <stdio.h>
#include <string.h>

#include "file_stats.h"


// ============================================================
// CONSTANTS
// ============================================================

// Number of files whose counts are checked, and room for each path
#define COUNT_CASES 4
#define MAX_CASE_PATH 32

// One row per test file; each path is a character array in a 2D array
static const char COUNT_CASE_FILES[COUNT_CASES][MAX_CASE_PATH] = {
    "test.txt",
    "tests/empty.txt",
    "tests/no_newline.txt",
    "tests/whitespace_only.txt"
};

// Expected lines, words, and bytes; row i belongs to COUNT_CASE_FILES[i]
static const long COUNT_CASE_EXPECTED[COUNT_CASES][3] = {
    {12, 64, 379},
    {0, 0, 0},
    {1, 3, 13},
    {3, 0, 9}
};


// ============================================================
// STATIC FUNCTIONS
// ============================================================

/**
 * Compare one expected value with the actual value and report the result.
 *
 * Args:
 *     label (const char *): Name of the check, shown in the report
 *     expected (long): Correct value
 *     actual (long): Value the code produced
 *
 * Returns:
 *     int: 0 if the values match, 1 if they differ (added to the failure count)
 */
static int check(const char *label, long expected, long actual) {
    // Static storage keeps the count between calls, so every check in the
    // whole run gets its own number
    static int check_number = 0;
    check_number++;

    if (expected == actual) {
        printf("  %2d PASS  %-42s %ld\n", check_number, label, actual);
        return 0;
    }
    printf("  %2d FAIL  %-42s expected %ld, got %ld\n", check_number, label, expected,
           actual);
    return 1;
}

/**
 * Analyze a file that should succeed and check all four counts.
 *
 * Args:
 *     path (const char *): Test input file
 *     lines (long): Expected line count
 *     words (long): Expected word count
 *     bytes (long): Expected character and byte count (equal in binary mode)
 *
 * Returns:
 *     int: Number of failed checks
 */
static int check_counts(const char *path, long lines, long words, long bytes) {
    FileStats stats;
    StatsStatus status = analyze_file(path, &stats);

    printf("%s\n", path);
    int failures = check("status is STATS_OK", STATS_OK, status);

    // Counts are meaningless after a failure, so stop at the status check
    if (status != STATS_OK) {
        return failures;
    }

    failures += check("lines", lines, stats.lines);
    failures += check("words", words, stats.words);
    failures += check("characters", bytes, stats.characters);
    failures += check("size_bytes", bytes, stats.size_bytes);
    failures += check("filename echoed unchanged", 0, strcmp(stats.filename, path));
    return failures;
}

/**
 * Analyze an input that should fail and check the returned status.
 *
 * Args:
 *     label (const char *): Description of the case, shown in the report
 *     path (const char *): Input passed to analyze_file()
 *     expected (StatsStatus): Status the input must produce
 *
 * Returns:
 *     int: 0 if the status matches, 1 otherwise
 */
static int check_status(const char *label, const char *path, StatsStatus expected) {
    FileStats stats;

    printf("%s\n", label);
    return check("status", expected, analyze_file(path, &stats));
}


// ============================================================
// MAIN
// ============================================================

/**
 * Run every test case and report the total.
 *
 * Returns:
 *     int: 0 if every check passed, 1 if any failed
 */
int main(void) {
    int failures = 0;

    // Row 0 is the normal case; the remaining rows are boundary cases
    printf("===== NORMAL AND BOUNDARY =====\n");
    for (int i = 0; i < COUNT_CASES; i++) {
        failures += check_counts(COUNT_CASE_FILES[i], COUNT_CASE_EXPECTED[i][0],
                                 COUNT_CASE_EXPECTED[i][1], COUNT_CASE_EXPECTED[i][2]);
    }

    printf("\n===== INVALID =====\n");
    failures += check_status("missing file", "tests/does_not_exist.txt", STATS_ERR_OPEN);

    // Windows refuses to open a directory (STATS_ERR_OPEN); Linux opens it
    // and fails on the first read (STATS_ERR_READ). Both are correct.
    FileStats stats;
    StatsStatus dir_status = analyze_file("tests", &stats);
    printf("directory instead of file\n");
    failures += check("status is STATS_ERR_OPEN or STATS_ERR_READ", 1,
                      dir_status == STATS_ERR_OPEN || dir_status == STATS_ERR_READ);

    // Names built at run time: exactly at the limit, then one over it
    char long_name[MAX_FILENAME_LEN + 2];
    memset(long_name, 'a', MAX_FILENAME_LEN);
    long_name[MAX_FILENAME_LEN] = '\0';

    // At the limit the name is accepted, so the error comes from fopen()
    failures += check_status("filename of exactly 255 characters", long_name,
                             STATS_ERR_OPEN);

    long_name[MAX_FILENAME_LEN] = 'a';
    long_name[MAX_FILENAME_LEN + 1] = '\0';
    failures += check_status("filename of 256 characters", long_name,
                             STATS_ERR_NAME_TOO_LONG);

    printf("\n%s: %d failed check(s)\n", failures == 0 ? "ALL TESTS PASSED" : "TESTS FAILED",
           failures);
    return failures == 0 ? 0 : 1;
}
