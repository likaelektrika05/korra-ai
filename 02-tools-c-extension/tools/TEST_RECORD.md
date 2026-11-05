# Test Record: file_stats

Lia Surguladze, COMPE 475, Fall 2026, Project 07
Platform: Windows 11, MinGW GCC 6.3.0, GNU Make 3.82.90 (`mingw32-make`)
Full log: `evidence/test_output.txt`. Result: **ALL TESTS PASSED, 0 failed checks (28/28).**

## Automated Checks (`mingw32-make test`)
| # | Category | Input | Check | Expected | Actual | Result |
|---|---|---|---|---|---|---|
| 1-6 | Normal | test.txt | status, lines, words, chars, bytes, filename | OK, 12, 64, 379, 379, same | OK, 12, 64, 379, 379, same | PASS |
| 7-12 | Boundary | tests/empty.txt | same six checks | OK, 0, 0, 0, 0, same | OK, 0, 0, 0, 0, same | PASS |
| 13-18 | Boundary | tests/no_newline.txt | same six checks | OK, 1, 3, 13, 13, same | OK, 1, 3, 13, 13, same | PASS |
| 19-24 | Boundary | tests/whitespace_only.txt | same six checks | OK, 3, 0, 9, 9, same | OK, 3, 0, 9, 9, same | PASS |
| 25 | Invalid | tests/does_not_exist.txt | status | 2 (ERR_OPEN) | 2 | PASS |
| 26 | Invalid | tests (a directory) | status | 2 or 3 | 2 (Windows) | PASS |
| 27 | Boundary | 255-character name | status | 2 (accepted, then not found) | 2 | PASS |
| 28 | Invalid | 256-character name | status | 4 (ERR_NAME_TOO_LONG) | 4 | PASS |

## Program Output (`mingw32-make demo`)
| Case | Expected JSON `status` | Expected exit | Actual |
|---|---|---|---|
| test.txt | success, counts 12/64/379/379 | 0 | matches |
| empty file | success, all 0 | 0 | matches |
| no trailing newline | success, 1/3/13/13 | 0 | matches |
| whitespace only | success, 3/0/9/9 | 0 | matches |
| no arguments | error "Usage: file_stats <filename>" | 1 | matches |
| missing file | error "Cannot open file" | 2 | matches |
| directory | error "Cannot open file" (Windows) | 2 | matches |
| 256-character name | error "Filename too long" | 4 | matches |

Each run printed exactly one JSON object on stdout, plus a stderr diagnostic only on errors, so the output is stable and machine-readable for Project 08.

## Build Behavior
| Action | Expected | Actual |
|---|---|---|
| `mingw32-make rebuild` | clean, compile 3 `.c` files to `.o` separately, link | as expected, 0 warnings |
| `mingw32-make` (no changes) | "Nothing to be done" | as expected |
| touch `json_output.h`, then `mingw32-make` | recompile only main.o and json_output.o, relink | as expected |

## Evidence
| File | Shows |
|---|---|
| 01_rebuild.png | clean, separate compilation, linking, no warnings |
| 02_tests_*.png, test_output.txt | all 28 checks passing |
| 03_demo_*.png | JSON output and exit codes for every case |
| 04_incremental.png | incremental rebuild after a header change |