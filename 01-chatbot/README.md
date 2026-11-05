# Korra: AI Chatbot (Project 06)

Lia Surguladze, COMPE 475, Fall 2026

A minimal conversational chatbot built with LangGraph and Google Gemini, runnable locally and in Docker.

## Environment
- OS: Windows 11
- Python 3.11 (Anaconda environment `korra`)
- Packages: see `requirements.txt` (langgraph 1.2.14, langchain-google-genai 4.4.1, python-dotenv 1.2.4)
- Model: `gemini-3.8-flash` via Google AI Studio API key
- Docker Desktop (image based on `python:3.11-slim`)

## Project Structure
```
korra/
├── app/
│   ├── __init__.py
│   ├── graph.py        # LangGraph state, node, edges
│   └── main.py         # terminal chat loop (entry point)
├── evidence/           # screenshots and graph diagram
├── .env.example        # redacted configuration template
├── .gitignore
├── .dockerignore
├── Dockerfile
├── requirements.txt
└── README.md
```

## Configuration
Copy the template and add your own key (never commit `.env`):
```
copy .env.example .env
```
`.env` contains:
```
GOOGLE_API_KEY=your_api_key_here
MODEL_NAME=gemini-3.8-flash
```

## Run Locally
```
conda create -n korra python=3.11 -y
conda activate korra
pip install -r requirements.txt
python -m app.main
```
Type `quit` to exit.

## Run in Docker
```
docker build -t korra:1.0 .
docker run -it --rm --env-file .env korra:1.0
```
Credentials are supplied at runtime with `--env-file`; `.env` is excluded by `.dockerignore`, so no key is stored in the image.

## LangGraph Workflow
- **State:** `messages`, the conversation history (`add_messages` reducer appends new messages).
- **Node:** `chatbot` reads `messages`, calls the model, and writes one AI reply.
- **Edges:** `START → chatbot → END` (entry, single step, termination).
- The chat loop keeps the state between turns in memory, so Korra remembers earlier messages in the session. There is no persistence, tools, or multi-agent behavior (those come in later projects).

See `evidence/03_graph.mmd` for the generated diagram.

## Evidence
| File | Shows |
|---|---|
| 01_environment.png | Python version and conda environment |
| 02_local_chat_*.png | Local conversation, including context memory |
| 03_graph.png / .mmd | LangGraph workflow diagram |
| 04_docker_build.png | Successful image build |
| 05_no_credentials.png | No API key inside the image |
| 06_docker_chat.png | Korra running in the container |