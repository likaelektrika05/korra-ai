# Korra: Tools (Project 08)

Lia Surguladze, COMPE 475, Fall 2026

Korra (LangGraph + Google Gemini) with two tools bound to the model:
- **tavily_search**: web search (Tavily)
- **analyze_file_statistics**: the Project 07 C program, called through the supplied wrapper `tools/file_stats_tool.py`, which runs it as a subprocess and parses its JSON

## Project Structure
```
korra08/
├── FA26_MD_06_S03_chatbot.py   # Korra graph + chat loop (prints tool calls and results)
├── tools/
│   ├── file_stats_tool.py      # supplied wrapper (@tool)
│   ├── main.c, file_stats.c/.h, json_output.c/.h, Makefile
│   ├── test_file_stats.c, test.txt, tests/   # 28 checks and fixtures
├── Dockerfile                  # two-stage: build+test C tool, then runtime
├── docker-compose.yml          # builds image korra-phase-01
├── .dockerignore               # supplied
├── requirements.txt
├── .env.example                # redacted template
└── evidence/
```

## Configuration
Create `.env` from the template (never submitted):
```
GOOGLE_API_KEY=your_gemini_key
MODEL_NAME=gemini-3.8-flash
TAVILY_API_KEY=tvly-your_key
```

## Run on Windows (Anaconda Prompt, from this folder)
```
conda activate korra
pip install -r requirements.txt
cd tools
mingw32-make
mingw32-make test
file_stats.exe test.txt
python file_stats_tool.py test.txt
cd ..
python FA26_MD_06_S03_chatbot.py
```

## Run in Docker
```
docker compose build
docker run --rm -it korra-phase-01
docker run --rm korra-phase-01 python tools/file_stats_tool.py tools/test.txt
```
Note: per the supplied `.dockerignore`, `.env` is copied into the image so it runs without `--env-file`. The image is for local use only and must not be pushed to a registry. `.env` is not included in this submission.

## Graph
`START → chatbot →(tools_condition)→ tools → chatbot → … → END`
- **chatbot**: Gemini with both tools bound; either answers or requests tool calls.
- **tools**: `ToolNode([tavily_search, analyze_file_statistics])` executes the calls and returns `ToolMessage`s to the model, so the final answer uses the actual C counts.
- Model errors (such as 503 or rate limits) are retried, then reported as a controlled Korra reply instead of a crash.

## Docker Build
- **Stage 1** (`python:3.11-slim` + gcc/make): `make rebuild && make test`. All 28 checks must pass, or the build fails and no image is produced.
- **Stage 2** (`python:3.11-slim`): Python packages, the wrapper, the test fixtures, and the Linux `file_stats` binary copied into the same `tools/` folder. No compiler is present.

## Results (Windows and Docker match)
| Scenario | Lines | Words | Chars | Bytes |
|---|---|---|---|---|
| tools/test.txt | 12 | 64 | 379 | 379 |
| tools/tests/empty.txt | 0 | 0 | 0 | 0 |
| tools/tests/no_newline.txt | 1 | 3 | 13 | 13 |
| tools/tests/whitespace_only.txt | 3 | 0 | 9 | 9 |
| tools/tests/does_not_exist.txt | error: cannot open file (no crash) | | | |

Evidence for every scenario (with the `[TOOL CALL]` and `[TOOL RESULT]` lines) is in `evidence/`.