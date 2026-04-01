# ElixirX Sales Portal

A full-stack sales portal built with React, FastAPI, and Supabase.

## Tech Stack

| Layer    | Technology                              |
|----------|-----------------------------------------|
| Frontend | React 19, TypeScript, Vite, Tailwind v4 |
| Backend  | Python, FastAPI, Uvicorn                |
| Database | Supabase (PostgreSQL)                   |
| Auth     | Supabase Auth                           |
| Email    | Resend                                  |

## Project Structure

```
elixirx-portal/
├── frontend/   # React + TypeScript + Vite + Tailwind CSS
└── backend/    # Python FastAPI application
```

## Setup

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at http://localhost:5173

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Runs at http://localhost:8000

API health check: http://localhost:8000/api/health

## Environment Variables

### frontend/.env
```
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_API_URL=http://localhost:8000
```

### backend/.env
```
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
ADMIN_SETUP_CODE=...
RESEND_API_KEY=...
FRONTEND_URL=http://localhost:5173
```
