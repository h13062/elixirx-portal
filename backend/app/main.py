from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import FRONTEND_URL
from app.routers import (
    auth_router,
    dashboard,
    inventory_router,
    issues,
    machine_lifecycle,
    notifications,
    reservations,
    warranty,
)

app = FastAPI(title="ElixirX API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
# machine_lifecycle MUST be registered before inventory_router so that the
# static /machines/status-summary and /machines/bulk-status paths resolve
# before inventory_router's /machines/{machine_id} catches them.
app.include_router(machine_lifecycle.router)
app.include_router(warranty.router)
app.include_router(reservations.router)
app.include_router(issues.router)
app.include_router(notifications.router)
app.include_router(dashboard.router)
app.include_router(inventory_router.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "elixirx-api"}
