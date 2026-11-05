/**
 * Filename: file_stats.c
 * Author: Professor Denis O. Núñez
 * Email: donunez@programmingjourneys.com
 * Organization: Programming Journeys
 * Project: Project 07 - C Programming Project
 * Module: Module 07 - C Programming (Part I)
 * Layer: Application - Tools
 * Date Created: March 10, 2026
 * Date Modified: October 2, 2026
 * Version: 3.0
 * License: Educational Use
 *
 * Requirements:
 *     C standard library only
 *
 * Description:
 *     Counts the lines, words, characters, and bytes of a text file.
 *     The file is read in binary mode, so the counts are the same on
 *     Windows and Linux. This file owns the analysis only and prints
 *     nothing; main.c decides how results and errors are reported. Every
 *     library call that can fail has its return value checked.
 *
 * Usage Instructions:
 *     Call analyze_file() from main.c after including file_stats.h.
 *     Compiled to file_stats.o and linked by the project Makefile:
 *         make
 */


// ============================================================
// INCLUDES
// ============================================================

#include "file_stats.h"

#include <ctype.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>


// ============================================================
// PUBLIC FUNCTIONS
// ============================================================

/**
 * Analyze a text file and fill in its statistics.
 *
 * Reads the file one byte at a time in binary mode, so the counts are
 * identical on Windows and Linux. A newline ends a line, a transition
 * from whitespace to non-whitespace starts a word, and every byte read
 * adds to both the character count and the byte count.
 *
 * Args:
 *     filename (const char *): Path of the file to analyze
 *     stats (FileStats *): Structure to fill in; owned by the caller
 *
 * Returns:
 *     StatsStatus: STATS_OK on success; STATS_ERR_NAME_TOO_LONG,
 *     STATS_ERR_OPEN, or STATS_ERR_READ on failure, in which case the
 *     contents of stats are undefined
 */
StatsStatus analyze_file(const char *filename, FileStats *stats) {
    size_t name_len = strlen(filename);

    // Reject instead of truncating so the output never misreports the name
    if (name_len > MAX_FILENAME_LEN) {
        return STATS_ERR_NAME_TOO_LONG;
    }

    // Binary mode: Windows text mode would turn each CRLF into one
    // character, so the same file would give different counts per platform
    FILE *file = fopen(filename, "rb");
    if (file == NULL) {
        return STATS_ERR_OPEN;
    }

    stats->lines = 0;
    stats->words = 0;
    stats->characters = 0;
    stats->size_bytes = 0;

    // Length was checked above, so the name and its terminator always fit
    memcpy(stats->filename, filename, name_len + 1);

    int ch;
    bool in_word = false;  // True while the previous character was part of a word

    while ((ch = fgetc(file)) != EOF) {
        stats->characters++;
        stats->size_bytes++;

        if (ch == '\n') {
            stats->lines++;
        }

        if (isspace(ch)) {
            in_word = false;
        } else if (!in_word) {
            in_word = true;
            stats->words++;
        }
    }

    // EOF means either end of file or a read error; ferror() tells them
    // apart. Opening a directory succeeds on Linux but every read fails here.
    int read_failed = ferror(file);
    fclose(file);

    return read_failed ? STATS_ERR_READ : STATS_OK;
}
