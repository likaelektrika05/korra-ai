/**
 * Filename: json_output.h
 * Author: Professor Denis O. Núñez
 * Email: donunez@programmingjourneys.com
 * Organization: Programming Journeys
 * Project: Project 07 - C Programming Project
 * Module: Module 07 - C Programming (Part I)
 * Layer: Application - Tools
 * Date Created: October 2, 2026
 * Date Modified: October 2, 2026
 * Version: 3.0
 * License: Educational Use
 *
 * Requirements:
 *     C standard library only
 *
 * Description:
 *     Public interface of json_output.c: the two functions that write an
 *     analysis result or an error to stdout as one JSON object. Kept
 *     separate from file_stats.h so each source file has its own header.
 *
 * Usage Instructions:
 *     Include from any source file that reports results:
 *         #include "json_output.h"
 *     Build the complete tool with the project Makefile:
 *         make
 */

#ifndef JSON_OUTPUT_H
#define JSON_OUTPUT_H


// ============================================================
// INCLUDES
// ============================================================

// Needed for the FileStats type in print_success_json()
#include "file_stats.h"


// ============================================================
// FUNCTION PROTOTYPES
// ============================================================

void print_success_json(const FileStats *stats);
void print_error_json(const char *message);

#endif  // JSON_OUTPUT_H
