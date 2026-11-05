"""
Filename: file_stats_tool.py
Author: Professor Denis O. Núñez
Email: donunez@programmingjourneys.com
Organization: Programming Journeys
Project: Project 08 - Korra Tools
Module: Module 08 - C Programming (Part II)
Layer: Application - Tools
Date Created: March 10, 2026
Date Modified: October 4, 2026
Version: 4.1
License: Educational Use

Requirements:
    langchain-core

Description:
    Wraps the compiled file_stats C tool as a LangGraph-compatible tool, so
    an agent can ask for the line, word, character, and byte counts of a text
    file and receive them as structured data. The C program does the analysis
    and prints one JSON object; this module runs it, parses that object, and
    returns it unchanged. It exists so Project 08 can call Project 07's tool
    without reimplementing the analysis in Python, and its scope stops at
    process invocation and result parsing: it performs no counting of its own
    and formats nothing for display.

    The executable is located beside this file. Windows builds produce
    file_stats.exe and other platforms produce file_stats, and both names are
    tried so the same wrapper works in Windows, Linux, and Docker.

    Exemption: LG-01 is claimed under the Console Application exemption for
    the standalone block only. When this file is run directly its printed
    output is the user interface a student reads. Diagnostics use the logger.

Usage Instructions:
    1. Build the tool from the project folder, which compiles main.c,
       file_stats.c, and json_output.c and links them:
           make
       On Windows the executable is file_stats.exe; elsewhere file_stats.
    2. Run from a terminal for testing, from this tools folder:
           python file_stats_tool.py test.txt
       The exit status is 0 when the analysis succeeds and 1 when it fails.
    3. Use with LangGraph. Import it with this folder's parent on the import
       path, or from within that folder:
           from tools.file_stats_tool import analyze_file_statistics
           llm_with_tools = llm.bind_tools([analyze_file_statistics])
"""


# ============================================================
# IMPORTS
# ============================================================

import json
import logging
import subprocess
import sys
from pathlib import Path

from langchain_core.tools import tool


# ============================================================
# CONSTANTS
# ============================================================

# Windows builds carry the .exe suffix, other platforms do not; the Makefile
# chooses the name, so both are tried rather than assuming the platform
EXECUTABLE_NAMES = ("file_stats.exe", "file_stats")

# The C tool reads one file and exits, so anything slower than this is a hang
EXECUTION_TIMEOUT_SECONDS = 10


# ============================================================
# LOGGER
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# FUNCTIONS
# ============================================================

def _find_executable() -> Path:
    """
    Return the path of the compiled file_stats executable.

    Do not call directly; analyze_file_statistics() uses it to locate the
    program before running it.

    Raises:
        FileNotFoundError: If no build of the tool is next to this file.

    Returns:
        Path: Full path of the executable that will be run
    """
    # The build and this wrapper are distributed in the same folder
    here = Path(__file__).resolve().parent
    for name in EXECUTABLE_NAMES:
        candidate = here / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "No file_stats build found in %s; run make in that folder" % here
    )


@tool
def analyze_file_statistics(filename: str) -> dict:
    """
    Report the line, word, character, and byte counts of a text file.

    Runs the compiled C tool on the named file and returns the JSON object it
    prints. Characters and bytes are both counts of bytes read, so for any
    input they hold the same value. A relative filename is resolved against
    the current working directory of this process, which is not necessarily
    the folder holding the tool.

    Args:
        filename: Path of the text file to analyze, relative or absolute

    Returns:
        dict: On success, the analysis as printed by the C tool:
              {
                  "tool": "file_stats",
                  "filename": "C:\\path\\to\\file.txt",
                  "lines": 12,
                  "words": 64,
                  "characters": 379,
                  "size_bytes": 379,
                  "status": "success"
              }

              On failure, a description of what went wrong:
              {
                  "error": "Cannot open file",
                  "status": "error"
              }
    """
    try:
        executable = _find_executable()
        target = Path(filename).resolve()

        result = subprocess.run(
            [str(executable), str(target)],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT_SECONDS,
        )

        stdout_clean = result.stdout.strip()
        stderr_clean = result.stderr.strip()

        if result.returncode != 0 or not stdout_clean:
            logger.error("file_stats exited %d: %s", result.returncode,
                         stderr_clean)
            return {"error": stderr_clean or "Tool produced no output",
                    "status": "error"}

        # The C tool already emits escaped JSON, so it is parsed as printed
        return json.loads(stdout_clean)

    except FileNotFoundError as exc:
        logger.error("Executable missing: %s", exc)
        return {"error": str(exc), "status": "error"}
    except subprocess.TimeoutExpired:
        logger.error("file_stats exceeded %d seconds",
                     EXECUTION_TIMEOUT_SECONDS)
        return {"error": "Tool execution timed out", "status": "error"}
    except json.JSONDecodeError as exc:
        logger.error("Unparsable output from file_stats: %s", exc)
        return {"error": "Invalid JSON output from tool",
                "raw_output": stdout_clean, "status": "error"}
    except Exception as exc:
        # The docstring promises a dict on every failure, so an unexpected
        # error is reported the same way rather than reaching the agent
        logger.exception("Unexpected failure running file_stats")
        return {"error": "Integration error: %s" % exc, "status": "error"}


# ============================================================
# MAIN GUARD
# ============================================================

if __name__ == "__main__":
    # LG-01 is exempt in this block under the Console Application exemption:
    # when the file is run directly, this printed output is the interface the
    # student reads, so it is not routed through the logger
    if len(sys.argv) != 2:
        print("Usage: python file_stats_tool.py <filename>")
        sys.exit(1)

    analysis = analyze_file_statistics.invoke({"filename": sys.argv[1]})

    print("LangGraph Tool Result:")
    print(json.dumps(analysis, indent=2))

    if analysis.get("status") == "error":
        # A non-zero status lets a calling script detect the failure
        sys.exit(1)

    print("\nTool Name: %s" % analyze_file_statistics.name)
    print("Tool Schema: %s" % analyze_file_statistics.args)
    print("\nThis tool is ready for LangGraph model.bind_tools()!")
