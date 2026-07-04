# Backend

Flask API for the associative chat prototype.

## Run

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 app.py
```

Environment variables:

- `PORT`, default `5000`
- `FRONTEND_ORIGIN`, default `*`
- `MODEL_ENDPOINT_URL`, default `http://localhost:8080/v1`
- `MODEL_NAME`, default `local-placeholder-model`
- `DATABASE_PATH`, default `backend/data/associative_chat.sqlite3`

## API

- `GET /api/health`
- `GET /api/conversations`
- `POST /api/conversations` with `{ "title": "Optional title" }`
- `GET /api/conversations/:id/messages`
- `POST /api/conversations/:id/messages` with `{ "role": "user", "content": "..." }`
- `POST /api/chat` with `{ "message": "..." }`
