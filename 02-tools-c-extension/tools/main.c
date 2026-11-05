/**
 * Filename: main.c
 * Author: Professor Denis O. Núñez
 * Email: donunez@programmingjourneys.com
 * Organization: Programming Journeys
 * Project: Project 07 - C Programming Project
 * Module: Module 07 - C Programming (Part I)
 * Layer: Application - Tools
 * Date Created: March 10, 2026
 * Date Modified: October 4, 2026
 * Version: 3.0
 * License: Educational Use
 *
 * Requirements:
 *     C standard library only
 *
 * Description:
 *     Command-line entry point for the file statistics tool. Validates
 *     the arguments, runs the analysis, and reports the result. This
 *     file decides how outcomes are reported; analysis lives in
 *     file_stats.c and JSON formatting in json_output.c.
 *
 *     Output contract (consumed by Project 08):
 *         stdout - exactly one JSON object, success or error
 *         stderr - a one-line diagnostic on errors only
 *         exit   - a StatsStatus value (see file_stats.h)
 *
 * Usage Instructions:
 *     Build with the project Makefile, then run:
 *         make
 *         ./file_stats <filename>        (Linux, macOS, Docker)
 *         file_stats <filename>          (Windows)
 */


// ============================================================
// INCLUDES
// ============================================================

#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "file_stats.h"
#include "json_output.h"


// ============================================================
// MAIN
// ============================================================

/**
 * Validate the command line, analyze the file, and report the result.
 *
 * Args:
 *     argc (int): Number of command-line arguments, including the program name
 *     argv (char *[]): Command-line arguments; argv[1] is the file to analyze
 *
 * Returns:
 *     int: A StatsStatus value used as the process exit code (0 on success)
 */
int main(int argc, char *argv[]) {
    if (argc != 2) {
        print_error_json("Usage: file_stats <filename>");
        fprintf(stderr, "file_stats: usage: file_stats <filename>\n");
        return STATS_ERR_USAGE;
    }

    FileStats stats;

    StatsStatus status = analyze_file(argv[1], &stats);
    int saved_errno = errno;  // Capture before output can change errno

    switch (status) {
        case STATS_OK:
            print_success_json(&stats);
            break;
        case STATS_ERR_NAME_TOO_LONG:
            print_error_json("Filename too long");
            fprintf(stderr, "file_stats: filename longer than %d characters\n",
                    MAX_FILENAME_LEN);
            break;
        case STATS_ERR_OPEN:
            print_error_json("Cannot open file");
            fprintf(stderr, "file_stats: cannot open '%s': %s\n",
                    argv[1], strerror(saved_errno));
            break;
        case STATS_ERR_READ:
            print_error_json("Cannot read file (not a regular file or read error)");
            fprintf(stderr, "file_stats: cannot read '%s'\n", argv[1]);
            break;
        default:
            print_error_json("Unknown error");
            fprintf(stderr, "file_stats: unknown error\n");
            break;
    }

    return status;
}
