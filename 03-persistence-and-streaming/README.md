# Korra: Persistence and Streaming (Project 10)

Lia Surguladze · COMPE 475, Fall 2026

Korra gets a memory that outlives the program: an in-memory checkpointer (S1), a SQLite checkpoint file with thread IDs and token streaming (S2), database tools the agent calls on their own graph nodes (S3), and the database moved into its own PostgreSQL container whose records survive the containers being destroyed (S4). Model: OpenAI `gpt-4o-mini`.

All screenshots are in `images/` (named by section) and collected, labeled, in `Project10_Evidence.pdf`.

## Folder layout

```
Surguladze_Lia_Project10/
├── README.md
├── Project10_Evidence.pdf          every screenshot, labeled by section
├── .env.example                    key names only (the real .env is not submitted)
├── images/                         S1-*, S2-*, S3-*, S4-* screenshots
├── s1/Lesson_4_Student.ipynb       executed lesson notebook + written answer
├── s2/
│   ├── FA26_MD_10_S02_chatbot.py   Project 06 chatbot + SqliteSaver + thread IDs + streaming
│   └── korra_checkpoints.db        its checkpoint database (threads message1, message2)
├── s3/korra/                       LangGraph project served with langgraph dev
│   ├── langgraph.json, pyproject.toml, requirements.txt
│   └── src/korra_m10/
│       ├── graph.py                korra -> read_database_node | save_database_node
│       └── tools/
│           ├── student_db_tools.py read_student_records, save_student_record
│           ├── test_database.db    the Module 10 student database (6 students after S3)
│           └── create_db.py, add_student.py, remove_student.py, test_queries.py (supplied)
└── s4/
    ├── docker-compose.yml          db (postgres:17 + named volume) and korra
    ├── schema.sql                  tables + seed rows, run only on an empty volume
    └── korra/                      same graph and tools as S3 + Dockerfile, .dockerignore
```

## Keys (`.env`, never submitted)

```
OPENAI_API_KEY=...        S1, S2, S3, S4
TAVILY_API_KEY=...        S1, S2 (web search)
POSTGRES_PASSWORD=...     S4 only
LANGSMITH_API_KEY=...     optional, for Studio
```
Keep one `.env` in the project root. S1, S2 and S3 find it by walking up from their folder; for S4 copy it beside `docker-compose.yml`.

## Section 1: Persistence and Streaming Foundations

```
conda activate korra
cd s1
jupyter notebook Lesson_4_Student.ipynb      (Kernel > Restart & Run All)
```
The DeepLearning.AI Lesson 4 notebook with author/purpose/date. The few lines changed so it runs on current LangGraph releases are listed in the notebook (`TavilySearch`, `SqliteSaver` built from a `sqlite3` connection, `langgraph.checkpoint.sqlite.aio`, `astream_events` v2, `gpt-4o-mini`).

- Thread `1`: SF weather → LA weather → "Which one is warmer?" → *Los Angeles is warmer than San Francisco* (kept its context).
- Thread `2`: the same "Which one is warmer?" → *Could you please clarify what you are comparing?* (no history).
- Streaming cell prints the reply token by token (`The| current| weather| …`).
- The written answer on why an in-memory checkpointer loses everything on restart is the last cell.

## Section 2: A Chatbot That Remembers

```
cd s2
python FA26_MD_10_S02_chatbot.py
python FA26_MD_10_S02_chatbot.py --db C:\nope\x.db                 (bad path test)
python FA26_MD_10_S02_chatbot.py --db FA26_MD_10_S02_chatbot.py    (not-a-database test)
```
- `SqliteSaver` on the file `korra_checkpoints.db` (beside the script), passed to `compile(checkpointer=...)`.
- Asks for a thread ID; prints *Continuing thread 'X': N saved messages* or *New thread 'X'*.
- `graph.stream(..., stream_mode="messages")` prints tokens as they arrive.
- A checkpoint database that cannot be opened prints `Cannot open the checkpoint database … Reason: …` and exits with status 1, no traceback.

Evidence: the Project 06 chatbot forgets the name after a restart (S2-1, S2-2); this chatbot told the name on `message1` (S2-3), remembers it after closing and reopening (S2-4), knows nothing on `message2` (S2-5), and reports both bad databases cleanly (S2-6).

## Section 3: Database Tools the Agent Calls

```
cd s3\korra
python src\korra_m10\tools\create_db.py        (builds test_database.db: 5 students, 5 courses, 10 enrollments)
pip install -e .
langgraph dev
```
Studio: `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`

```
START -> korra --route_tool_call--> read_database_node -> korra
                               \--> save_database_node -> korra
                               \--> END
```
- **Two tools, two nodes.** `read_student_records(email="")` lists every student or looks one up (with enrollments); `save_student_record(name, email, major, gpa, enrollment_date)` inserts one. Each is in its own `ToolNode`.
- **Routing by name.** `route_tool_call` reads the tool name on the model's call and returns the node that owns it; the model is bound with `parallel_tool_calls=False`.
- **Parameterized statements only.** Every query uses `?` placeholders; the model supplies values, never SQL (a name like `x'); DROP TABLE students;--` is stored as plain text).
- **Failures are data.** `{"status": "refused", "reasons": [...]}` for invalid input or a duplicate email, `{"status": "not_found", ...}` for a missing record, `{"status": "error", ...}` when the database cannot be opened. The SQLite file is opened with `mode=rw`, so a missing file is reported instead of silently creating an empty one.

Evidence: list (S3-3), Korra asks for details (S3-4), saved as id 6 (S3-5), list shows the new student (S3-6), refused duplicate email from the tool in a fresh thread (S3-7), not_found (S3-8), unreadable database while the file was renamed (S3-9), and the saved student still present after the server was stopped and restarted (S3-10).

## Section 4: The Database as Its Own Service

```
cd s4
copy ..\.env .env
docker compose up --build -d
docker compose ps
```
- **Two services.** `db` (`postgres:17`, data in the named volume `korra_pgdata`) and `korra` (the S3 graph served on port 2024).
- **Database gates the app.** `korra` has `depends_on: db: condition: service_healthy`, with a `pg_isready` health check.
- **Same tools, only the connection changes.** `student_db_tools.py` is identical to S3; when `DATABASE_URL` is set it connects to PostgreSQL through psycopg and swaps `?` for `%s`. Tool names and result shapes are unchanged.
- **Seeded once.** `schema.sql` is mounted at `/docker-entrypoint-initdb.d/`, which the postgres image runs only when the data directory is empty. The first start logs `running /docker-entrypoint-initdb.d/01_schema.sql`; every later start logs `Database directory appears to contain a database; Skipping initialization`.
- **No credential in the image.** `.env` is excluded by `.dockerignore`; keys reach the container at run time through `env_file`, and the password through `DATABASE_URL` built by compose. `docker image inspect s4-korra` shows no key in the image's environment (S4-7).

Records surviving a rebuild:
```
(save a student in Studio)
docker compose down        containers and network removed, volume kept
docker compose up -d       new containers, same volume
(list students in Studio: the student is still there)
```
`docker compose down -v` would delete the volume and the records with it.

Evidence: build with db Healthy before korra started (S4-1), schema run on the empty volume (S4-1b), fresh volume holds only the 5 seed students, not the S3 student (S4-3), student saved into PostgreSQL (S4-4), containers removed and recreated (S4-5a), initialization skipped (S4-5b), student still present after the rebuild (S4-6), no credentials in the image (S4-7).
