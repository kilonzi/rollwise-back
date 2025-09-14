from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_endpoints import router as admin_router
from app.api.twilio_endpoints import router as twilio_router
from app.api.dataset_endpoints import router as dataset_router
from app.config.settings import settings
from app.models import create_tables


@asynccontextmanager
async def lifespan(fapp: FastAPI):
    print("🚀 Starting RollWise Multi-Tenant AI Voice Agent Platform...")
    print(f"📊 Database: {settings.DATABASE_URL}")
    print(f"🌐 Base URL: {settings.BASE_URL}")
    print(
        f"🎤 Deepgram API: {'✅ Configured' if settings.DEEPGRAM_API_KEY else '❌ Not configured'}"
    )
    create_tables()
    print("✅ Database tables created/verified")
    print("📋 Multi-tenant schema ready:")
    print("   - Tenants (businesses)")
    print("   - Users (tenant members)")
    print("   - Agents (AI voice agents)")
    print("   - Conversations (call/SMS sessions)")
    print("   - Transcripts (conversation content)")
    print("   - ToolCalls (agent actions)")
    print("   - BusinessDatasets (ChromaDB knowledge)")

    print("\n🎯 Platform ready for multi-tenant agent deployment!")
    print(f"📡 Admin API: http://{settings.HOST}:{settings.PORT}/admin/")
    print(f"📖 API Docs: http://{settings.HOST}:{settings.PORT}/docs")
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
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(twilio_router, tags=["twilio"])
app.include_router(admin_router, tags=["admin"])
app.include_router(dataset_router, tags=["datasets"])


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
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL,
        reload=True,  # Set to False in production
    )
