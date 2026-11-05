/**
 * Filename: json_output.c
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
 *     Writes analysis results and errors to stdout as JSON, the format
 *     Project 08 parses. Strings are escaped so filenames containing
 *     quotes, backslashes (every Windows path), or control characters
 *     still produce valid JSON. This file owns output formatting only.
 *
 * Usage Instructions:
 *     Call print_success_json() or print_error_json() from main.c after
 *     including json_output.h. Compiled to json_output.o and linked by the
 *     project Makefile:
 *         make
 */


// ============================================================
// INCLUDES
// ============================================================

#include "json_output.h"

#include <stdio.h>


// ============================================================
// STATIC FUNCTIONS
// ============================================================

/**
 * Print a string as a JSON string literal, including the quotes.
 *
 * Escapes the characters JSON does not allow inside a string: the
 * quote, the backslash, and control characters below 0x20.
 *
 * Args:
 *     text (const char *): NUL-terminated string to print
 *
 * Returns:
 *     void
 */
static void print_json_string(const char *text) {
    putchar('"');

    for (size_t i = 0; text[i] != '\0'; i++) {
        // Converted to unsigned so bytes above 127 (UTF-8 accents) are
        // never negative and never mistaken for control characters
        unsigned char c = (unsigned char)text[i];

        switch (c) {
            case '"':  fputs("\\\"", stdout); break;
            case '\\': fputs("\\\\", stdout); break;
            case '\n': fputs("\\n", stdout);  break;
            case '\r': fputs("\\r", stdout);  break;
            case '\t': fputs("\\t", stdout);  break;
            case '\b': fputs("\\b", stdout);  break;
            case '\f': fputs("\\f", stdout);  break;
            default:
                if (c < 0x20) {
                    printf("\\u%04x", (unsigned int)c);  // Remaining control characters
                } else {
                    putchar(c);
                }
        }
    }

    putchar('"');
}


// ============================================================
// PUBLIC FUNCTIONS
// ============================================================

/**
 * Print a successful analysis as one JSON object on stdout.
 *
 * Args:
 *     stats (const FileStats *): Results to print; not modified
 *
 * Returns:
 *     void
 */
void print_success_json(const FileStats *stats) {
    printf("{\n");
    printf("  \"tool\": \"file_stats\",\n");
    printf("  \"filename\": ");
    print_json_string(stats->filename);
    printf(",\n");
    printf("  \"lines\": %ld,\n", stats->lines);
    printf("  \"words\": %ld,\n", stats->words);
    printf("  \"characters\": %ld,\n", stats->characters);
    printf("  \"size_bytes\": %ld,\n", stats->size_bytes);
    printf("  \"status\": \"success\"\n");
    printf("}\n");
}

/**
 * Print an error as one JSON object on stdout.
 *
 * Args:
 *     message (const char *): Short description of the error
 *
 * Returns:
 *     void
 */
void print_error_json(const char *message) {
    printf("{\n");
    printf("  \"tool\": \"file_stats\",\n");
    printf("  \"error\": ");
    print_json_string(message);
    printf(",\n");
    printf("  \"status\": \"error\"\n");
    printf("}\n");
}
