"""
Webhook Router Module

This module defines FastAPI routes for handling webhooks from external services
like Typeform. It processes webhook payloads to extract address information,
matches addresses to the nearest delivery hub, and sends notifications with
the results.

Routes:
- POST /typeform: Handle webhooks from Typeform
- POST /generic: Handle generic webhooks with a standard format
"""

import logging
import time
import hmac
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.models.location import AddressInput, TypeformWebhook, MatchResult
from app.services.geocoding_service import GeocodingService, GeocodingError
from app.services.location_service import LocationService, LocationServiceError
from app.services.notification_service import NotificationService, NotificationError
from app.api.routes.address_router import get_geocoding_service, get_location_service, get_notification_service, send_match_notification

# Configure logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["webhooks"])


@router.post("/typeform", status_code=200)
async def handle_typeform_webhook(
    webhook: TypeformWebhook,
    background_tasks: BackgroundTasks,
    request: Request,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    location_service: LocationService = Depends(get_location_service),
    notification_service: NotificationService = Depends(get_notification_service),
    x_typeform_signature: Optional[str] = Header(None)
):
    """
    Handle webhooks from Typeform.
    
    This endpoint:
    1. Validates the webhook signature (if configured)
    2. Extracts address and contact information from the form response
    3. Geocodes the address and finds the nearest delivery hub
    4. Sends a notification with the result
    5. Returns a success response
    
    Args:
        webhook: Typeform webhook payload
        background_tasks: FastAPI background tasks
        request: FastAPI request object
        geocoding_service: Geocoding service dependency
        location_service: Location service dependency
        notification_service: Notification service dependency
        x_typeform_signature: Typeform signature header
        
    Returns:
        JSONResponse: Success response
        
    Raises:
        HTTPException: If webhook validation fails or processing fails
    """
    start_time = time.time()
    logger.info(f"Received Typeform webhook: {webhook.event_id}")
    
    # Validate webhook signature if configured
    if settings.TYPEFORM_WEBHOOK_SECRET and settings.TYPEFORM_WEBHOOK_SECRET.get_secret_value():
        if not x_typeform_signature:
            raise HTTPException(status_code=401, detail="Missing Typeform signature")
        
        # Get request body for signature validation
        body = await request.body()
        
        # Validate signature
        if not _validate_typeform_signature(body, x_typeform_signature):
            raise HTTPException(status_code=401, detail="Invalid Typeform signature")
    
    try:
        # Extract address input from Typeform response
        address_input = _extract_address_from_typeform(webhook)
        
        if not address_input:
            raise HTTPException(status_code=400, detail="Could not extract address from form response")
        
        logger.info(f"Extracted address: {address_input.address}")
        
        # Geocode the address
        coordinates, formatted_address = await geocoding_service.geocode_address(address_input.address)
        logger.info(f"Address geocoded to: {coordinates.latitude}, {coordinates.longitude}")
        
        # Find the nearest location
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
        
        # Send notification in background
        background_tasks.add_task(
            send_match_notification,
            match_result=match_result,
            address_input=address_input,
            notification_service=notification_service
        )
        
        logger.info(f"Webhook processed in {processing_time_ms:.2f}ms")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Webhook processed successfully",
                "event_id": webhook.event_id,
                "matched_location": nearest_location.name,
                "processing_time_ms": processing_time_ms
            }
        )
        
    except GeocodingError as e:
        logger.error(f"Geocoding error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Geocoding error: {str(e)}")
        
    except LocationServiceError as e:
        logger.error(f"Location service error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Location service error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/generic", status_code=200)
async def handle_generic_webhook(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    location_service: LocationService = Depends(get_location_service),
    notification_service: NotificationService = Depends(get_notification_service),
    x_webhook_signature: Optional[str] = Header(None)
):
    """
    Handle generic webhooks with a standard format.
    
    This endpoint accepts webhooks from any source with a standard format:
    {
        "address": "123 Main St, City, State ZIP",
        "email": "user@example.com",
        "name": "John Doe",
        "phone": "555-123-4567",
        "metadata": { ... }
    }
    
    Args:
        payload: Webhook payload
        background_tasks: FastAPI background tasks
        geocoding_service: Geocoding service dependency
        location_service: Location service dependency
        notification_service: Notification service dependency
        x_webhook_signature: Webhook signature header
        
    Returns:
        JSONResponse: Success response
        
    Raises:
        HTTPException: If webhook validation fails or processing fails
    """
    start_time = time.time()
    logger.info("Received generic webhook")
    
    # Validate webhook signature if configured
    if settings.WEBHOOK_SECRET and settings.WEBHOOK_SECRET.get_secret_value():
        if not x_webhook_signature:
            raise HTTPException(status_code=401, detail="Missing webhook signature")
        
        # Validate signature (implementation depends on your signature format)
        # This is a placeholder for actual signature validation
        if not _validate_generic_signature(payload, x_webhook_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    try:
        # Extract address input from payload
        try:
            address_input = AddressInput(
                address=payload["address"],
                email=payload["email"],
                name=payload.get("name"),
                phone=payload.get("phone"),
                application_id=payload.get("application_id"),
                metadata=payload.get("metadata", {})
            )
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f"Missing required field: {str(e)}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
        
        logger.info(f"Processing address: {address_input.address}")
        
        # Geocode the address
        coordinates, formatted_address = await geocoding_service.geocode_address(address_input.address)
        logger.info(f"Address geocoded to: {coordinates.latitude}, {coordinates.longitude}")
        
        # Find the nearest location
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
        
        # Send notification in background
        background_tasks.add_task(
            send_match_notification,
            match_result=match_result,
            address_input=address_input,
            notification_service=notification_service
        )
        
        logger.info(f"Webhook processed in {processing_time_ms:.2f}ms")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Webhook processed successfully",
                "matched_location": nearest_location.name,
                "processing_time_ms": processing_time_ms
            }
        )
        
    except GeocodingError as e:
        logger.error(f"Geocoding error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Geocoding error: {str(e)}")
        
    except LocationServiceError as e:
        logger.error(f"Location service error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Location service error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


def _extract_address_from_typeform(webhook: TypeformWebhook) -> Optional[AddressInput]:
    """
    Extract address input from Typeform webhook.
    
    Args:
        webhook: Typeform webhook payload
        
    Returns:
        AddressInput object or None if extraction fails
    """
    try:
        # Get answers from form response
        answers = webhook.form_response.get("answers", [])
        
        # Initialize variables
        address = None
        email = None
        name = None
        phone = None
        
        # Extract fields from answers
        for answer in answers:
            field = answer.get("field", {})
            field_id = field.get("id", "").lower()
            field_type = field.get("type", "")
            
            # Extract address
            if "address" in field_id and field_type == "text":
                address = answer.get("text", "")
            
            # Extract email
            elif "email" in field_id and field_type == "email":
                email = answer.get("email", "")
            
            # Extract name
            elif "name" in field_id and field_type == "text":
                name = answer.get("text", "")
            
            # Extract phone
            elif "phone" in field_id and field_type in ["text", "phone_number"]:
                phone = answer.get("text", "") or answer.get("phone_number", "")
        
        # Check if we have the minimum required fields
        if not address or not email:
            logger.warning("Missing required fields in Typeform response")
            return None
        
        # Create metadata
        metadata = {
            "source": "typeform",
            "form_id": webhook.form_response.get("form_id", ""),
            "submission_id": webhook.form_response.get("token", ""),
            "submitted_at": webhook.form_response.get("submitted_at", "")
        }
        
        # Create and return AddressInput
        return AddressInput(
            address=address,
            email=email,
            name=name,
            phone=phone,
            application_id=webhook.form_response.get("token", ""),
            metadata=metadata
        )
        
    except Exception as e:
        logger.error(f"Error extracting address from Typeform: {str(e)}")
        return None


def _validate_typeform_signature(body: bytes, signature: str) -> bool:
    """
    Validate Typeform webhook signature.
    
    Args:
        body: Request body bytes
        signature: Typeform signature header
        
    Returns:
        bool: True if signature is valid, False otherwise
    """
    if not settings.TYPEFORM_WEBHOOK_SECRET:
        return True
    
    try:
        # Get webhook secret
        secret = settings.TYPEFORM_WEBHOOK_SECRET.get_secret_value()
        
        # Calculate HMAC
        h = hmac.new(secret.encode(), body, hashlib.sha256)
        calculated_signature = h.hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(calculated_signature, signature)
        
    except Exception as e:
        logger.error(f"Error validating Typeform signature: {str(e)}")
        return False


def _validate_generic_signature(payload: Dict[str, Any], signature: str) -> bool:
    """
    Validate generic webhook signature.
    
    Args:
        payload: Webhook payload
        signature: Webhook signature header
        
    Returns:
        bool: True if signature is valid, False otherwise
    """
    if not settings.WEBHOOK_SECRET:
        return True
    
    try:
        # Get webhook secret
        secret = settings.WEBHOOK_SECRET.get_secret_value()
        
        # Convert payload to JSON string
        payload_str = json.dumps(payload, sort_keys=True)
        
        # Calculate HMAC
        h = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256)
        calculated_signature = h.hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(calculated_signature, signature)
        
    except Exception as e:
        logger.error(f"Error validating generic signature: {str(e)}")
        return False
