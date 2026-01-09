from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from .models import Base
from .routers import nutrition, weight, workouts, metrics, dashboard

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Forge API",
    description="Fitness tracking API with natural language parsing",
    version="1.0.0"
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


@app.get("/")
def root():
    return {"status": "ok", "service": "forge-api"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
