from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, get_db
from .models import Base
from .routers import nutrition, weight, workouts, metrics, dashboard, fasting, conversation
from .services.reminder_scheduler import init_scheduler, start_scheduler, shutdown_scheduler, load_user_reminders

# Create tables
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    init_scheduler()
    start_scheduler()

    # Load existing reminders into scheduler
    db = next(get_db())
    try:
        load_user_reminders(db)
    finally:
        db.close()

    yield

    # Shutdown
    shutdown_scheduler()


app = FastAPI(
    title="Forge API",
    description="Fitness tracking API with natural language parsing and conversational AI",
    version="2.0.0",
    lifespan=lifespan
)

# CORS for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(nutrition.router, prefix="/api")
app.include_router(weight.router, prefix="/api")
app.include_router(workouts.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(fasting.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "service": "forge-api", "version": "2.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
