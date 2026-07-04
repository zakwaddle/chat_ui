# Associative Chat

Small local-first chatbot prototype for testing bounded conversational memory.

## Phase 1

- Flask backend with `/api/health` and `/api/chat`
- React + Vite frontend with a simple chat UI
- Frontend can send a message to the backend and display a placeholder assistant response

## Phase 2

- SQLite database initialized at startup
- `conversations`, `messages`, and `embeddings` tables
- Conversations can be created and listed through the API
- Messages can be saved and loaded by conversation

## Run

Start the backend:

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 app.py
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173`.
