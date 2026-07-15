"""
Ojas AI API - Main FastAPI Application
Production-ready FastAPI backend with Supabase integration.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


# Initialize FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Ojas AI fitness tracking application",
    version="1.0.0",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json"
)


# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers for API responses
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify API is running.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
            "project": settings.PROJECT_NAME
        }
    )


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "message": "Welcome to Ojas AI API",
        "version": "1.0.0",
        "docs": f"{settings.API_V1_PREFIX}/docs",
        "health": "/health"
    }


# Application startup event
@app.on_event("startup")
async def startup_event():
    """
    Initialize services on application startup.
    """
    logger.info("Starting %s", settings.PROJECT_NAME)
    logger.info("Environment: %s", settings.ENVIRONMENT)
    logger.info("API docs: %s/docs", settings.API_V1_PREFIX)
    if not settings.OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY is not set. AI Trainer feature will not work until configured.")


# Application shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on application shutdown.
    """
    logger.info("Shutting down %s", settings.PROJECT_NAME)


# Include API routers
from app.routes import workouts, trainer, profile, food, auth

app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_PREFIX}/auth",
    tags=["Auth"]
)

app.include_router(
    workouts.router, 
    prefix=f"{settings.API_V1_PREFIX}/workouts",
    tags=["Workouts"]
)

app.include_router(
    trainer.router,
    prefix=f"{settings.API_V1_PREFIX}/trainer",
    tags=["Trainer"]
)

app.include_router(
    profile.router,
    prefix=f"{settings.API_V1_PREFIX}/profile",
    tags=["Profile"]
)

app.include_router(
    food.router,
    prefix=f"{settings.API_V1_PREFIX}/food",
    tags=["Food AI"]
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.ENVIRONMENT == "development" else False
    )
