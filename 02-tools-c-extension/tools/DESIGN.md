# Design and Interface Specification: file_stats

Lia Surguladze, COMPE 475, Fall 2026, Project 07
(C source files supplied in the course project package; this document describes their design.)

## Purpose
`file_stats` is a command-line tool that counts the lines, words, characters, and bytes of one text file and reports the result as a single JSON object. Project 08 calls it from Korra (Python/LangGraph) through a subprocess.

## Inputs
- Exactly one command-line argument: the path of the file to analyze.
- Path length: at most 255 characters (`MAX_FILENAME_LEN`). Longer names are rejected, never truncated.
- The file is read in **binary mode**, so counts are identical on Windows and Linux.

## Counting Rules
| Count | Rule |
|---|---|
| lines | number of `\n` characters |
| words | each transition from whitespace to non-whitespace (`isspace`) |
| characters | every byte read (a CRLF counts as 2) |
| size_bytes | every byte read (equal to characters in binary mode) |

## File Organization
| File | Responsibility |
|---|---|
| `main.c` | Validate arguments, call the analysis, choose the output and exit code |
| `file_stats.h` / `file_stats.c` | `StatsStatus`, `FileStats`, and `analyze_file()`: analysis only, prints nothing |
| `json_output.h` / `json_output.c` | Print success or error JSON, with string escaping |
| `test_file_stats.c` | Automated tests (28 checks) against `file_stats.o` |
| `Makefile` | Separate compilation, linking, clean, rebuild, test, and demo |

Each declaration lives in exactly one header; sources include the headers they need instead of duplicating declarations.

## Shared Data Structures (`file_stats.h`)
```c
typedef enum {
    STATS_OK                = 0,
    STATS_ERR_USAGE         = 1,
    STATS_ERR_OPEN          = 2,
    STATS_ERR_READ          = 3,
    STATS_ERR_NAME_TOO_LONG = 4
} StatsStatus;

typedef struct {
    long lines;
    long words;
    long characters;
    long size_bytes;
    char filename[MAX_FILENAME_LEN + 1];
} FileStats;
```

## Function Prototypes
```c
StatsStatus analyze_file(const char *filename, FileStats *stats);  // file_stats.h
void print_success_json(const FileStats *stats);                    // json_output.h
void print_error_json(const char *message);                         // json_output.h
```

## Project 08 Output Contract
- **stdout:** exactly one JSON object, always.
- **stderr:** a one-line diagnostic, on errors only.
- **exit code:** a `StatsStatus` value. These numbers must not change.

Success:
```json
{
  "tool": "file_stats",
  "filename": "test.txt",
  "lines": 12,
  "words": 64,
  "characters": 379,
  "size_bytes": 379,
  "status": "success"
}
```

Error:
```json
{
  "tool": "file_stats",
  "error": "Cannot open file",
  "status": "error"
}
```

Project 08 should check `status` first. Counts are present only when it is `"success"`. Filenames are JSON-escaped, so Windows paths with backslashes remain valid JSON.

## Safety
- Filename length is checked before copying into the fixed-size `filename` array.
- `fopen()` and `ferror()` return values are checked; read errors are reported, not ignored.
- `errno` is saved immediately after the analysis, before output can change it.