"""
Address Router Module

This module defines FastAPI routes for handling address matching requests.
It provides endpoints for matching addresses to the nearest delivery hub
and retrieving location information.

Routes:
- POST /match: Match an address to the nearest delivery hub
- GET /locations: Get all delivery hub locations
- GET /locations/{location_id}: Get a specific delivery hub location
"""

import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.models.location import AddressInput, MatchResult, Location, Coordinates
from app.services.geocoding_service import GeocodingService, GeocodingError
from app.services.location_service import LocationService, LocationServiceError
from app.services.notification_service import NotificationService, NotificationError

# Configure logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["address"])


# Dependency for geocoding service
async def get_geocoding_service():
    """Dependency for the geocoding service."""
    async with GeocodingService() as service:
        yield service


# Dependency for location service
async def get_location_service():
    """Dependency for the location service."""
    service = LocationService()
    if not service.locations:
        await service.load_locations()
    yield service


# Dependency for notification service
async def get_notification_service():
    """Dependency for the notification service."""
    async with NotificationService() as service:
        yield service


@router.post("/match", response_model=MatchResult, status_code=200)
async def match_address(
    address_input: AddressInput,
    background_tasks: BackgroundTasks,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    location_service: LocationService = Depends(get_location_service),
    notification_service: NotificationService = Depends(get_notification_service),
    send_notification: bool = Query(True, description="Whether to send a notification with the result")
):
    """
    Match an address to the nearest delivery hub.
    
    This endpoint:
    1. Geocodes the input address to coordinates
    2. Finds the nearest delivery hub
    3. Optionally sends a notification with the result
    4. Returns the match result
    
    Args:
        address_input: Address input with contact information
        background_tasks: FastAPI background tasks
        geocoding_service: Geocoding service dependency
        location_service: Location service dependency
        notification_service: Notification service dependency
        send_notification: Whether to send a notification
        
    Returns:
        MatchResult: The result of matching the address to the nearest hub
        
    Raises:
        HTTPException: If geocoding or matching fails
    """
    start_time = time.time()
    logger.info(f"Processing address match request: {address_input.address}")
    
    try:
        # Step 1: Geocode the address
        coordinates, formatted_address = await geocoding_service.geocode_address(address_input.address)
        logger.info(f"Address geocoded to: {coordinates.latitude}, {coordinates.longitude}")
        
        # Step 2: Find the nearest location
        nearest_location, distance_km = location_service.find_nearest_location(coordinates)
        logger.info(f"Nearest location: {nearest_location.name} at {distance_km:.2f}km")
        
        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Create match result
        match_result = MatchResult(
            input_address=address_input.address,
            geocoded_address=formatted_address,
            geocoded_coordinates=coordinates,
            matched_location=nearest_location,
            distance_km=distance_km,
            distance_miles=distance_km * 0.621371,
            processing_time_ms=processing_time_ms,
            timestamp=datetime.utcnow()
        )
        
        # Step 3: Send notification if requested
        if send_notification:
            # Add notification task to background tasks
            background_tasks.add_task(
                send_match_notification,
                match_result=match_result,
                address_input=address_input,
                notification_service=notification_service
            )
            logger.info(f"Notification queued for {address_input.email}")
        
        return match_result
        
    except GeocodingError as e:
        logger.error(f"Geocoding error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Geocoding error: {str(e)}")
        
    except LocationServiceError as e:
        logger.error(f"Location service error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Location service error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/match/batch", response_model=List[MatchResult], status_code=200)
async def batch_match_addresses(
    addresses: List[AddressInput],
    background_tasks: BackgroundTasks,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    location_service: LocationService = Depends(get_location_service),
    notification_service: NotificationService = Depends(get_notification_service),
    send_notification: bool = Query(True, description="Whether to send notifications with the results"),
    max_batch_size: int = Query(100, description="Maximum batch size")
):
    """
    Match multiple addresses to their nearest delivery hubs in a batch.
    
    This endpoint:
    1. Validates the batch size
    2. Processes each address in the batch
    3. Returns a list of match results
    
    Args:
        addresses: List of address inputs
        background_tasks: FastAPI background tasks
        geocoding_service: Geocoding service dependency
        location_service: Location service dependency
        notification_service: Notification service dependency
        send_notification: Whether to send notifications
        max_batch_size: Maximum batch size
        
    Returns:
        List[MatchResult]: The results of matching each address
        
    Raises:
        HTTPException: If batch size exceeds maximum or processing fails
    """
    # Validate batch size
    if len(addresses) > max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds maximum of {max_batch_size}"
        )
    
    logger.info(f"Processing batch of {len(addresses)} addresses")
    results = []
    
    # Process each address
    for address_input in addresses:
        try:
            # Geocode the address
            coordinates, formatted_address = await geocoding_service.geocode_address(address_input.address)
            
            # Find the nearest location
            nearest_location, distance_km = location_service.find_nearest_location(coordinates)
            
            # Create match result
            match_result = MatchResult(
                input_address=address_input.address,
                geocoded_address=formatted_address,
                geocoded_coordinates=coordinates,
                matched_location=nearest_location,
                distance_km=distance_km,
                distance_miles=distance_km * 0.621371,
                processing_time_ms=0,  # Not tracking individual processing time in batch
                timestamp=datetime.utcnow()
            )
            
            # Add to results
            results.append(match_result)
            
            # Send notification if requested
            if send_notification:
                background_tasks.add_task(
                    send_match_notification,
                    match_result=match_result,
                    address_input=address_input,
                    notification_service=notification_service
                )
                
        except Exception as e:
            logger.error(f"Error processing address {address_input.address}: {str(e)}")
            # Continue processing other addresses
    
    return results


@router.get("/locations", response_model=List[Location], status_code=200)
async def get_locations(
    location_service: LocationService = Depends(get_location_service),
    active_only: bool = Query(True, description="Whether to return only active locations"),
    region: Optional[str] = Query(None, description="Filter by region")
):
    """
    Get all delivery hub locations.
    
    This endpoint returns all delivery hub locations, optionally filtered by
    active status and region.
    
    Args:
        location_service: Location service dependency
        active_only: Whether to return only active locations
        region: Filter by region
        
    Returns:
        List[Location]: List of delivery hub locations
        
    Raises:
        HTTPException: If retrieving locations fails
    """
    try:
        # Get all locations
        locations = location_service.locations
        
        # Apply filters
        if active_only:
            locations = [loc for loc in locations if loc.active]
            
        if region:
            locations = [loc for loc in locations if loc.region == region]
            
        return locations
        
    except Exception as e:
        logger.error(f"Error retrieving locations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving locations: {str(e)}")


@router.get("/locations/{location_id}", response_model=Location, status_code=200)
async def get_location(
    location_id: str = Path(..., description="Location ID"),
    location_service: LocationService = Depends(get_location_service)
):
    """
    Get a specific delivery hub location by ID.
    
    Args:
        location_id: Location ID
        location_service: Location service dependency
        
    Returns:
        Location: The requested delivery hub location
        
    Raises:
        HTTPException: If location not found
    """
    location = location_service.get_location_by_id(location_id)
    
    if not location:
        raise HTTPException(status_code=404, detail=f"Location with ID {location_id} not found")
        
    return location


@router.get("/locations/stats", response_model=Dict[str, int], status_code=200)
async def get_location_stats(
    location_service: LocationService = Depends(get_location_service)
):
    """
    Get location statistics.
    
    Returns:
        Dict with location count statistics
    """
    return location_service.get_locations_count()


async def send_match_notification(
    match_result: MatchResult,
    address_input: AddressInput,
    notification_service: NotificationService
):
    """
    Send a notification with the match result.
    
    This function is intended to be run as a background task.
    
    Args:
        match_result: The match result to send notification about
        address_input: The original address input with contact information
        notification_service: Notification service
    """
    try:
        await notification_service.send_notification(match_result, address_input)
        logger.info(f"Notification sent successfully to {address_input.email}")
    except NotificationError as e:
        logger.error(f"Failed to send notification: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error sending notification: {str(e)}")
