# ============================================================
# Filename: Makefile
# Author: Professor Denis O. Núñez
# Email: donunez@programmingjourneys.com
# Organization: Programming Journeys
# Project: Project 07 - C Programming Project
# Module: Module 07 - C Programming (Part I)
# Layer: Deployment - Build
# Date Created: October 2, 2026
# Date Modified: October 2, 2026
# Version: 3.0
# License: Educational Use
#
# Requirements:
#     gcc with C11 support
#     GNU Make (mingw32-make on Windows)
#
# Description:
#     Builds file_stats by compiling each translation unit to its own
#     object file and linking the objects into one executable. Rebuilds
#     only what changed: editing a header rebuilds only the objects whose
#     sources include it. Also builds and runs the automated test
#     program. Works on Windows (MinGW) and Linux/macOS/Docker.
#
# Usage Instructions:
#     make            Build the executable (only what changed)
#     make clean      Delete object files and the executable
#     make rebuild    Clean, then build everything
#     make test       Build and run the automated tests (fails if any check fails)
#     make demo       Run the program on every test case to show its output
#     On Windows with MinGW, the command may be mingw32-make
# ============================================================


# ============================================================
# COMPILER SETTINGS
# ============================================================

CC      = gcc
CFLAGS  = -Wall -Wextra -Wpedantic -std=c11 -O2

SRCS      = main.c file_stats.c json_output.c
OBJS      = $(SRCS:.c=.o)
# The test program reuses the analysis object, not main.o
TEST_OBJS = test_file_stats.o file_stats.o


# ============================================================
# PLATFORM SETTINGS
# ============================================================

# Windows needs the .exe suffix, cmd.exe syntax, and del instead of rm
ifeq ($(OS),Windows_NT)
    SHELL       := cmd.exe
    TARGET      = file_stats.exe
    RUN         = file_stats.exe
    TEST_TARGET = test_file_stats.exe
    RUN_TEST    = test_file_stats.exe
    RM          = del /Q /F
    NULLDEV     = NUL
else
    TARGET      = file_stats
    RUN         = ./file_stats
    TEST_TARGET = test_file_stats
    RUN_TEST    = ./test_file_stats
    RM          = rm -f
    NULLDEV     = /dev/null
endif


# ============================================================
# BUILD TARGETS
# ============================================================

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS)

# Compile: each .c file to its own .o file
%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Header dependencies: each object lists exactly the headers its source
# includes, directly or through another header, so editing a header
# rebuilds only the objects that use it
main.o:            main.c file_stats.h json_output.h
file_stats.o:      file_stats.c file_stats.h
json_output.o:     json_output.c json_output.h file_stats.h
test_file_stats.o: test_file_stats.c file_stats.h

clean:
	-$(RM) $(OBJS) $(TARGET) test_file_stats.o $(TEST_TARGET) 2>$(NULLDEV)

# Two separate make runs, so clean always finishes before the build starts,
# even under make -j
rebuild:
	$(MAKE) clean
	$(MAKE) all


# ============================================================
# TEST TARGETS
# ============================================================

$(TEST_TARGET): $(TEST_OBJS)
	$(CC) $(CFLAGS) -o $@ $(TEST_OBJS)

# Fails (non-zero exit) when any check fails
test: $(TEST_TARGET)
	$(RUN_TEST)

# Runs the program on every case so the JSON, stderr, and exit codes can be
# seen. A leading "-" lets make continue after the expected non-zero exits
demo: $(TARGET)
	@echo ===== NORMAL: test.txt =====
	-$(RUN) test.txt
	@echo ===== BOUNDARY: empty file =====
	-$(RUN) tests/empty.txt
	@echo ===== BOUNDARY: no trailing newline =====
	-$(RUN) tests/no_newline.txt
	@echo ===== BOUNDARY: whitespace only =====
	-$(RUN) tests/whitespace_only.txt
	@echo ===== INVALID: no arguments =====
	-$(RUN)
	@echo ===== INVALID: missing file =====
	-$(RUN) tests/does_not_exist.txt
	@echo ===== INVALID: directory instead of file =====
	-$(RUN) tests
	@echo ===== INVALID: filename of 256 characters =====
	-$(RUN) aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

.PHONY: all clean rebuild test demo
