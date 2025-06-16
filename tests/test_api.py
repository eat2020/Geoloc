"""
Tests for the Driver-Hub Matching Service API endpoints.

This module contains pytest tests for the FastAPI endpoints, using
httpx.AsyncClient for async testing and mocking external dependencies.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.models.location import Location, Coordinates, AddressInput, MatchResult, TypeformWebhook
from app.services.geocoding_service import GeocodingService, GeocodingError
from app.services.location_service import LocationService, LocationServiceError
from app.services.notification_service import NotificationService, NotificationError


# Test data
TEST_ADDRESS = "123 Test St, Chicago, IL 60601"
TEST_EMAIL = "test@example.com"
TEST_COORDINATES = Coordinates(latitude=41.8781, longitude=-87.6298)
TEST_FORMATTED_ADDRESS = "123 Test Street, Chicago, Illinois, 60601, United States"

# Sample location data
TEST_LOCATIONS = [
    Location(
        id="loc_001",
        name="Downtown Test Location",
        address="100 Main St, Chicago, IL 60601",
        city="Chicago",
        state="IL",
        postal_code="60601",
        country="USA",
        coordinates=Coordinates(latitude=41.8801, longitude=-87.6321),
        region="Midwest",
        type="supercenter",
        active=True
    ),
    Location(
        id="loc_002",
        name="North Test Location",
        address="200 North Ave, Chicago, IL 60610",
        city="Chicago",
        state="IL",
        postal_code="60610",
        country="USA",
        coordinates=Coordinates(latitude=41.9100, longitude=-87.6350),
        region="Midwest",
        type="market",
        active=True
    ),
    Location(
        id="loc_003",
        name="Inactive Test Location",
        address="300 South St, Chicago, IL 60605",
        city="Chicago",
        state="IL",
        postal_code="60605",
        country="USA",
        coordinates=Coordinates(latitude=41.8700, longitude=-87.6280),
        region="Midwest",
        type="supercenter",
        active=False
    ),
]


# Fixtures
@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_geocoding_service():
    """Create a mock for the geocoding service."""
    mock_service = AsyncMock(spec=GeocodingService)
    mock_service.geocode_address.return_value = (TEST_COORDINATES, TEST_FORMATTED_ADDRESS)
    return mock_service


@pytest.fixture
def mock_location_service():
    """Create a mock for the location service."""
    mock_service = MagicMock(spec=LocationService)
    mock_service.locations = TEST_LOCATIONS
    mock_service.find_nearest_location.return_value = (TEST_LOCATIONS[0], 2.5)  # 2.5 km distance
    mock_service.get_location_by_id.side_effect = lambda id: next((loc for loc in TEST_LOCATIONS if loc.id == id), None)
    mock_service.get_locations_count.return_value = {"total": 3, "active": 2, "inactive": 1}
    return mock_service


@pytest.fixture
def mock_notification_service():
    """Create a mock for the notification service."""
    mock_service = AsyncMock(spec=NotificationService)
    mock_service.send_notification.return_value = {
        "status": "success",
        "method": "email",
        "results": {"email": {"provider": "sendgrid", "status_code": 202}},
        "timestamp": datetime.utcnow().isoformat()
    }
    return mock_service


# Override dependencies
@pytest.fixture
def override_dependencies(mock_geocoding_service, mock_location_service, mock_notification_service):
    """Override FastAPI dependencies with mocks."""
    
    # Save original dependencies
    from app.api.routes.address_router import get_geocoding_service as original_get_geocoding
    from app.api.routes.address_router import get_location_service as original_get_location
    from app.api.routes.address_router import get_notification_service as original_get_notification
    
    # Override dependencies
    app.dependency_overrides[original_get_geocoding] = lambda: mock_geocoding_service
    app.dependency_overrides[original_get_location] = lambda: mock_location_service
    app.dependency_overrides[original_get_notification] = lambda: mock_notification_service
    
    yield
    
    # Restore original dependencies
    app.dependency_overrides = {}


# Tests
@pytest.mark.asyncio
async def test_health_check():
    """Test the health check endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_root():
    """Test the root endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "service" in response.json()
        assert "version" in response.json()


@pytest.mark.asyncio
async def test_match_address(override_dependencies):
    """Test the match address endpoint."""
    address_input = {
        "address": TEST_ADDRESS,
        "email": TEST_EMAIL,
        "name": "Test User",
        "phone": "555-123-4567"
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/match", json=address_input)
        assert response.status_code == 200
        
        result = response.json()
        assert result["input_address"] == TEST_ADDRESS
        assert result["geocoded_address"] == TEST_FORMATTED_ADDRESS
        assert result["matched_location"]["name"] == TEST_LOCATIONS[0].name
        assert "distance_km" in result
        assert "distance_miles" in result
        assert "processing_time_ms" in result


@pytest.mark.asyncio
async def test_match_address_validation_error():
    """Test validation error for match address endpoint."""
    # Missing required fields
    invalid_input = {
        "address": TEST_ADDRESS
        # Missing email
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/match", json=invalid_input)
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_match_address_geocoding_error(override_dependencies, mock_geocoding_service):
    """Test geocoding error handling."""
    mock_geocoding_service.geocode_address.side_effect = GeocodingError("Invalid address")
    
    address_input = {
        "address": "Invalid Address",
        "email": TEST_EMAIL
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/match", json=address_input)
        assert response.status_code == 400
        assert "Geocoding error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_batch_match_addresses(override_dependencies):
    """Test the batch match addresses endpoint."""
    batch_input = [
        {
            "address": TEST_ADDRESS,
            "email": TEST_EMAIL,
            "name": "Test User 1"
        },
        {
            "address": "456 Another St, Chicago, IL 60602",
            "email": "test2@example.com",
            "name": "Test User 2"
        }
    ]
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/match/batch", json=batch_input)
        assert response.status_code == 200
        
        results = response.json()
        assert len(results) == 2
        assert results[0]["input_address"] == TEST_ADDRESS
        assert results[1]["input_address"] == "456 Another St, Chicago, IL 60602"


@pytest.mark.asyncio
async def test_batch_match_max_size(override_dependencies):
    """Test batch size limit enforcement."""
    # Create a batch with 101 items (over the default 100 limit)
    large_batch = [
        {
            "address": f"{i} Test St, Chicago, IL 60601",
            "email": f"test{i}@example.com"
        }
        for i in range(101)
    ]
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/match/batch", json=large_batch)
        assert response.status_code == 400
        assert "Batch size exceeds maximum" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_locations(override_dependencies):
    """Test getting all locations."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test with active_only=True (default)
        response = await client.get("/api/v1/locations")
        assert response.status_code == 200
        
        locations = response.json()
        assert len(locations) == 2  # Only active locations
        assert all(loc["active"] for loc in locations)
        
        # Test with active_only=False
        response = await client.get("/api/v1/locations?active_only=false")
        assert response.status_code == 200
        
        locations = response.json()
        assert len(locations) == 3  # All locations
        
        # Test with region filter
        response = await client.get("/api/v1/locations?region=Midwest")
        assert response.status_code == 200
        
        locations = response.json()
        assert all(loc["region"] == "Midwest" for loc in locations)


@pytest.mark.asyncio
async def test_get_location_by_id(override_dependencies):
    """Test getting a location by ID."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test with valid ID
        response = await client.get("/api/v1/locations/loc_001")
        assert response.status_code == 200
        
        location = response.json()
        assert location["id"] == "loc_001"
        assert location["name"] == TEST_LOCATIONS[0].name
        
        # Test with invalid ID
        response = await client.get("/api/v1/locations/nonexistent_id")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_location_stats(override_dependencies):
    """Test getting location statistics."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/locations/stats")
        assert response.status_code == 200
        
        stats = response.json()
        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["inactive"] == 1


@pytest.mark.asyncio
async def test_typeform_webhook(override_dependencies):
    """Test the Typeform webhook endpoint."""
    typeform_payload = {
        "event_id": "test_event_123",
        "event_type": "form_response",
        "form_response": {
            "form_id": "test_form",
            "token": "test_token",
            "submitted_at": "2025-06-16T10:30:00Z",
            "answers": [
                {
                    "field": {"id": "address", "type": "text"},
                    "text": TEST_ADDRESS
                },
                {
                    "field": {"id": "email", "type": "email"},
                    "email": TEST_EMAIL
                },
                {
                    "field": {"id": "name", "type": "text"},
                    "text": "Test User"
                }
            ]
        }
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/webhooks/typeform", json=typeform_payload)
        assert response.status_code == 200
        
        result = response.json()
        assert result["status"] == "success"
        assert result["event_id"] == "test_event_123"
        assert result["matched_location"] == TEST_LOCATIONS[0].name


@pytest.mark.asyncio
async def test_generic_webhook(override_dependencies):
    """Test the generic webhook endpoint."""
    webhook_payload = {
        "address": TEST_ADDRESS,
        "email": TEST_EMAIL,
        "name": "Test User",
        "phone": "555-123-4567",
        "metadata": {
            "source": "test_source"
        }
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/webhooks/generic", json=webhook_payload)
        assert response.status_code == 200
        
        result = response.json()
        assert result["status"] == "success"
        assert result["matched_location"] == TEST_LOCATIONS[0].name


@pytest.mark.asyncio
async def test_generic_webhook_missing_fields():
    """Test generic webhook with missing required fields."""
    invalid_payload = {
        "address": TEST_ADDRESS
        # Missing email
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/webhooks/generic", json=invalid_payload)
        assert response.status_code == 400
        assert "Missing required field" in response.json()["detail"]


@pytest.mark.asyncio
async def test_location_service_error(override_dependencies, mock_location_service):
    """Test handling of location service errors."""
    mock_location_service.find_nearest_location.side_effect = LocationServiceError("No locations loaded")
    
    address_input = {
        "address": TEST_ADDRESS,
        "email": TEST_EMAIL
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/match", json=address_input)
        assert response.status_code == 500
        assert "Location service error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_notification_background_task(override_dependencies, mock_notification_service):
    """Test that notifications are sent in the background."""
    address_input = {
        "address": TEST_ADDRESS,
        "email": TEST_EMAIL
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        # With notifications enabled (default)
        response = await client.post("/api/v1/match", json=address_input)
        assert response.status_code == 200
        
        # With notifications disabled
        response = await client.post("/api/v1/match?send_notification=false", json=address_input)
        assert response.status_code == 200
        
    # Check that send_notification was called only once (for the first request)
    assert mock_notification_service.send_notification.call_count == 1
