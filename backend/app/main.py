from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import FRONTEND_URL
from app.routers import auth

app = FastAPI(title="ElixirX API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "elixirx-api"}
