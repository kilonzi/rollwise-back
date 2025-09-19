from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, users, tenants, agents, conversations, twilio
from app.config.settings import settings
from app.models import create_tables
from app.utils.logging_config import app_logger as logger


@asynccontextmanager
async def lifespan(fapp: FastAPI):
    logger.info("🚀 Starting RollWise Multi-Tenant AI Voice Agent Platform...")
    logger.info("📊 Database: %s", settings.DATABASE_URL)
    logger.info("🌐 Base URL: %s", settings.BASE_URL)
    logger.info(
        "🎤 Deepgram API: %s",
        "✅ Configured" if settings.DEEPGRAM_API_KEY else "❌ Not configured",
    )
    create_tables()
    logger.info("✅ Database tables created/verified")
    logger.info("📋 Multi-tenant schema ready:")
    logger.info("   - Tenants (businesses)")
    logger.info("   - Users (tenant members)")
    logger.info("   - Agents (AI voice agents)")
    logger.info("   - Conversations (call/SMS sessions)")
    logger.info("   - Messages (chronological conversation content)")
    logger.info("   - ToolCalls (function execution logs)")
    logger.info("   - BusinessDatasets (ChromaDB knowledge)")

    logger.info("🎯 Platform ready for multi-tenant agent deployment!")
    logger.info("📡 Admin API: http://%s:%s/admin/", settings.HOST, settings.PORT)
    logger.info("📖 API Docs: http://%s:%s/docs", settings.HOST, settings.PORT)
    yield


app = FastAPI(
    title="RollWise Multi-Tenant AI Voice Agent",
    description="Multi-tenant AI voice agent platform for small businesses using Twilio and Deepgram",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(twilio.router, tags=["Twilio"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(tenants.router, tags=["Tenants"])
app.include_router(agents.router, tags=["Agents"])
app.include_router(conversations.router, tags=["Conversations"])


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "rollwise-ai-agent"}


# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "RollWise Multi-Tenant AI Voice Agent Platform",
        "version": "2.0.0",
        "description": "AI-powered voice agents for small businesses with multi-tenant support",
        "features": [
            "Multi-tenant architecture",
            "Agent-specific routing",
            "Dynamic agent configuration",
            "Conversation tracking",
            "Business tools integration",
        ],
        "endpoints": {
            "agent_voice": "/agent/{agent_id}/voice",
            "agent_messages": "/agent/{agent_id}/messages",
            "agent_callback": "/agent/{agent_id}/callback",
            "websocket": "/ws/{agent_id}/twilio",
            "admin": "/admin/*",
            "users": "/users/*",
            "health": "/health",
        },
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL,
        reload=True,  # Set to False in production
    )
