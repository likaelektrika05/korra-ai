# file_stats: C File Statistics Tool (Project 07)

Lia Surguladze, COMPE 475, Fall 2026

Counts the lines, words, characters, and bytes of a text file and prints the result as JSON. This is the C tool that Project 08 connects to Korra.

See `DESIGN.md` for the design and interface contract and `TEST_RECORD.md` for test results.

## Requirements
- gcc with C11 support (tested: MinGW GCC 6.3.0)
- GNU Make (on Windows: `mingw32-make`)

## Build and Run (Windows PowerShell)
```
mingw32-make            # build file_stats.exe (only what changed)
mingw32-make rebuild    # clean, then build everything
mingw32-make test       # run the 28 automated checks
mingw32-make demo       # show the output for every test case
mingw32-make clean      # delete .o and .exe files

.\file_stats.exe test.txt
```

## Build and Run (Linux / Docker)
```
make
make test
./file_stats test.txt
```

## Compiler Flags
`-Wall -Wextra -Wpedantic -std=c11 -O2` (the build produces no warnings)

## Exit Codes
| Code | Meaning |
|---|---|
| 0 | success |
| 1 | wrong number of arguments |
| 2 | file cannot be opened |
| 3 | not a regular file or read error |
| 4 | filename longer than 255 characters |