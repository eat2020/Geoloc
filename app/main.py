"""
Driver-Hub Matching Service - Main Application Entry Point

This FastAPI application matches driver applicants with their nearest delivery hub
based on their address. It uses the HERE API for geocoding and calculates distances
using the Haversine formula.

Author: Factory AI
Date: June 16, 2025
"""

import logging
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Internal imports
from app.core.config import settings
from app.api.routes import address_router, webhook_router
from app.services.location_service import LocationService
from app.services.geocoding_service import GeocodingService
from app.services.notification_service import NotificationService
from app.models.location import Location, AddressInput, MatchResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="Driver-Hub Matching Service",
    description="A service that matches driver applicants to their nearest delivery hub",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(address_router.router, prefix="/api/v1")
app.include_router(webhook_router.router, prefix="/api/v1/webhooks")

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services and load location data on startup."""
    logger.info("Starting Driver-Hub Matching Service")
    
    # Initialize services
    location_service = LocationService()
    await location_service.load_locations()
    
    logger.info(f"Loaded {len(location_service.locations)} delivery hub locations")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint to verify the service is running."""
    return {"status": "healthy", "service": "Driver-Hub Matching Service"}

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Driver-Hub Matching Service",
        "version": "1.0.0",
        "documentation": "/docs",
    }

# Main execution block
if __name__ == "__main__":
    import uvicorn
    
    # Run the application with uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
