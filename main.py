from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.twilio_endpoints import router as twilio_router
from app.api.user_endpoints import router as user_router
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
app.include_router(twilio_router, tags=["twilio"])
app.include_router(user_router, prefix="/users", tags=["users"])


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
        "admin_endpoints": {
            "create_tenant": "POST /admin/tenants",
            "list_tenants": "GET /admin/tenants",
            "create_agent": "POST /admin/agents",
            "list_agents": "GET /admin/agents",
            "tenant_conversations": "GET /admin/tenants/{tenant_id}/conversations",
            "agent_conversations": "GET /admin/agents/{agent_id}/conversations",
        },
        "user_endpoints": {
            "register": "POST /users/register",
            "login": "POST /users/login",
            "validate_token": "POST /users/validate-token",
            "password_reset_request": "POST /users/password-reset-request",
            "password_reset": "POST /users/password-reset",
            "profile": "GET /users/profile",
            "user_tenants": "GET /users/tenants",
            "associate_tenant": "POST /users/tenants/associate",
            "tenant_users": "GET /users/tenants/{tenant_id}/users",
            "tenant_agents": "GET /users/tenants/{tenant_id}/agents",
            "create_agent": "POST /users/tenants/{tenant_id}/agents",
            "update_agent": "PUT /users/tenants/{tenant_id}/agents/{agent_id}",
            "delete_agent": "DELETE /users/tenants/{tenant_id}/agents/{agent_id}",
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
