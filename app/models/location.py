"""
Location Models Module

This module defines Pydantic models for locations, address inputs, and match results
used throughout the Driver-Hub Matching Service.

Models:
- Location: Represents a delivery hub location with coordinates
- AddressInput: Represents an address input from a webhook or form
- MatchResult: Represents the result of matching an address to a location
"""

from pydantic import BaseModel, Field, EmailStr, validator, root_validator
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import re


class Coordinates(BaseModel):
    """Geographic coordinates model."""
    
    latitude: float = Field(..., description="Latitude coordinate", ge=-90, le=90)
    longitude: float = Field(..., description="Longitude coordinate", ge=-180, le=180)


class Location(BaseModel):
    """
    Delivery hub location model.
    
    Represents a delivery hub with its address and geographic coordinates.
    """
    
    id: Optional[str] = Field(None, description="Unique identifier for the location")
    name: str = Field(..., description="Name of the delivery hub")
    address: str = Field(..., description="Full address of the delivery hub")
    city: Optional[str] = Field(None, description="City of the delivery hub")
    state: Optional[str] = Field(None, description="State/province of the delivery hub")
    postal_code: Optional[str] = Field(None, description="Postal/ZIP code of the delivery hub")
    country: Optional[str] = Field(None, description="Country of the delivery hub")
    coordinates: Coordinates = Field(..., description="Geographic coordinates of the location")
    
    # Optional metadata
    region: Optional[str] = Field(None, description="Region or zone identifier")
    type: Optional[str] = Field(None, description="Type of delivery hub (e.g., warehouse, store)")
    active: bool = Field(True, description="Whether the location is active")
    
    class Config:
        """Pydantic model configuration."""
        
        schema_extra = {
            "example": {
                "id": "loc_001",
                "name": "Downtown Walmart",
                "address": "123 Main St, Springfield, IL 62701",
                "city": "Springfield",
                "state": "IL",
                "postal_code": "62701",
                "country": "USA",
                "coordinates": {
                    "latitude": 39.7817,
                    "longitude": -89.6501
                },
                "region": "Midwest",
                "type": "store",
                "active": True
            }
        }


class AddressInput(BaseModel):
    """
    Address input model for geocoding and matching.
    
    Represents an address submitted by a user or webhook for processing.
    """
    
    address: str = Field(..., description="Full address to geocode and match")
    email: EmailStr = Field(..., description="Email address for notifications")
    
    # Optional fields
    name: Optional[str] = Field(None, description="Name of the applicant")
    phone: Optional[str] = Field(None, description="Phone number of the applicant")
    application_id: Optional[str] = Field(None, description="ID from the application system")
    
    # Optional metadata from form submission
    metadata: Optional[Dict[str, Any]] = Field(
        default={}, 
        description="Additional metadata from the form submission"
    )
    
    @validator('phone')
    def validate_phone(cls, v):
        """Validate phone number format if provided."""
        if v is not None:
            # Remove any non-digit characters for validation
            digits_only = re.sub(r'\D', '', v)
            if not (7 <= len(digits_only) <= 15):  # International phone number length range
                raise ValueError("Phone number must have between 7 and 15 digits")
        return v
    
    class Config:
        """Pydantic model configuration."""
        
        schema_extra = {
            "example": {
                "address": "456 Oak St, Chicago, IL 60601",
                "email": "applicant@example.com",
                "name": "John Doe",
                "phone": "555-123-4567",
                "application_id": "app_12345",
                "metadata": {
                    "source": "typeform",
                    "submission_date": "2025-06-16T10:30:00Z"
                }
            }
        }


class MatchResult(BaseModel):
    """
    Match result model.
    
    Represents the result of matching an address to the nearest delivery hub.
    """
    
    input_address: str = Field(..., description="Original input address")
    geocoded_address: str = Field(..., description="Geocoded address from the API")
    geocoded_coordinates: Coordinates = Field(..., description="Geocoded coordinates")
    
    matched_location: Location = Field(..., description="Matched delivery hub location")
    distance_km: float = Field(..., description="Distance to the matched location in kilometers")
    distance_miles: float = Field(..., description="Distance to the matched location in miles")
    
    # Processing metadata
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of the match")
    
    # Optional fields
    alternative_locations: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="List of alternative locations (if requested)"
    )
    
    @root_validator
    def calculate_miles(cls, values):
        """Calculate distance in miles from kilometers if not provided."""
        if "distance_km" in values and "distance_miles" not in values:
            values["distance_miles"] = values["distance_km"] * 0.621371
        return values
    
    class Config:
        """Pydantic model configuration."""
        
        schema_extra = {
            "example": {
                "input_address": "456 Oak St, Chicago, IL 60601",
                "geocoded_address": "456 Oak Street, Chicago, Illinois, 60601, United States",
                "geocoded_coordinates": {
                    "latitude": 41.8781,
                    "longitude": -87.6298
                },
                "matched_location": {
                    "id": "loc_001",
                    "name": "Downtown Walmart",
                    "address": "123 Main St, Springfield, IL 62701",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62701",
                    "country": "USA",
                    "coordinates": {
                        "latitude": 39.7817,
                        "longitude": -89.6501
                    },
                    "region": "Midwest",
                    "type": "store",
                    "active": True
                },
                "distance_km": 28.5,
                "distance_miles": 17.7,
                "processing_time_ms": 156.32,
                "timestamp": "2025-06-16T10:30:05.123456Z",
                "alternative_locations": [
                    {
                        "id": "loc_002",
                        "name": "North Walmart",
                        "distance_km": 32.1
                    }
                ]
            }
        }


class TypeformWebhook(BaseModel):
    """
    Typeform webhook payload model.
    
    Represents the webhook payload sent by Typeform when a form is submitted.
    """
    
    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Type of event (e.g., form_response)")
    form_response: Dict[str, Any] = Field(..., description="Form response data")
    
    class Config:
        """Pydantic model configuration."""
        
        schema_extra = {
            "example": {
                "event_id": "01H5XVNFQPKJBV9XKGZ6QWERTY",
                "event_type": "form_response",
                "form_response": {
                    "form_id": "abcdef",
                    "token": "xyz123",
                    "submitted_at": "2025-06-16T10:30:00Z",
                    "answers": [
                        {
                            "field": {"id": "address", "type": "text"},
                            "text": "456 Oak St, Chicago, IL 60601"
                        },
                        {
                            "field": {"id": "email", "type": "email"},
                            "email": "applicant@example.com"
                        },
                        {
                            "field": {"id": "name", "type": "text"},
                            "text": "John Doe"
                        }
                    ]
                }
            }
        }
