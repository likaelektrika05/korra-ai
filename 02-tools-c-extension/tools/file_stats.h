/**
 * Filename: file_stats.h
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
 *     Public interface of file_stats.c: the status codes, the FileStats
 *     structure, and the analyze_file() prototype. Every source file that
 *     analyzes files or uses FileStats includes this header instead of
 *     repeating the declarations, so the interface is defined in exactly
 *     one place.
 *
 * Usage Instructions:
 *     Include from any source file that analyzes files or uses FileStats:
 *         #include "file_stats.h"
 *     Build the complete tool with the project Makefile:
 *         make
 */

#ifndef FILE_STATS_H
#define FILE_STATS_H


// ============================================================
// CONSTANTS
// ============================================================

// Longest filename accepted; longer names are rejected, never truncated,
// so the reported filename always matches the one the user typed
#define MAX_FILENAME_LEN 255


// ============================================================
// TYPES
// ============================================================

/**
 * Result of a file analysis, also used as the process exit code.
 * Values are part of the Project 08 interface and must not be renumbered.
 *
 * Attributes:
 *     STATS_OK: Analysis succeeded
 *     STATS_ERR_USAGE: Wrong number of command-line arguments
 *     STATS_ERR_OPEN: File missing or not readable
 *     STATS_ERR_READ: Not a regular file, or a read error occurred
 *     STATS_ERR_NAME_TOO_LONG: Filename longer than MAX_FILENAME_LEN
 */
typedef enum {
    STATS_OK                = 0,
    STATS_ERR_USAGE         = 1,
    STATS_ERR_OPEN          = 2,
    STATS_ERR_READ          = 3,
    STATS_ERR_NAME_TOO_LONG = 4
} StatsStatus;

/**
 * Statistics collected for one analyzed file.
 *
 * Attributes:
 *     lines: Number of newline characters
 *     words: Number of whitespace-separated words
 *     characters: Number of characters read, including whitespace and
 *         every carriage return, so a CRLF line ending counts as two
 *     size_bytes: File size in bytes, counted while reading
 *     filename: Name of the analyzed file, NUL-terminated
 */
typedef struct {
    long lines;
    long words;
    long characters;
    long size_bytes;
    char filename[MAX_FILENAME_LEN + 1];
} FileStats;


// ============================================================
// FUNCTION PROTOTYPES
// ============================================================

StatsStatus analyze_file(const char *filename, FileStats *stats);

#endif  // FILE_STATS_H
