"""
Pytest configuration file for Driver-Hub Matching Service tests.

This file contains fixtures and configuration for pytest tests,
allowing for consistent test setup across multiple test modules.
"""

import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.core.config import Settings, get_settings
from app.models.location import Location, Coordinates, AddressInput, MatchResult
from app.services.geocoding_service import GeocodingService, GeocodingError
from app.services.location_service import LocationService, LocationServiceError
from app.services.notification_service import NotificationService, NotificationError


# Test data fixtures
@pytest.fixture
def test_address():
    """Return a test address string."""
    return "123 Test St, Chicago, IL 60601"


@pytest.fixture
def test_email():
    """Return a test email address."""
    return "test@example.com"


@pytest.fixture
def test_coordinates():
    """Return test coordinates."""
    return Coordinates(latitude=41.8781, longitude=-87.6298)


@pytest.fixture
def test_formatted_address():
    """Return a formatted address string."""
    return "123 Test Street, Chicago, Illinois, 60601, United States"


@pytest.fixture
def test_locations():
    """Return a list of test location objects."""
    return [
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


@pytest.fixture
def test_address_input(test_address, test_email):
    """Return a test AddressInput object."""
    return AddressInput(
        address=test_address,
        email=test_email,
        name="Test User",
        phone="555-123-4567",
        application_id="test_app_123",
        metadata={"source": "test"}
    )


@pytest.fixture
def test_match_result(test_address, test_formatted_address, test_coordinates, test_locations):
    """Return a test MatchResult object."""
    return MatchResult(
        input_address=test_address,
        geocoded_address=test_formatted_address,
        geocoded_coordinates=test_coordinates,
        matched_location=test_locations[0],
        distance_km=2.5,
        distance_miles=1.55,
        processing_time_ms=156.32,
        timestamp=datetime.utcnow()
    )


# Mock service fixtures
@pytest.fixture
def mock_geocoding_service(test_coordinates, test_formatted_address):
    """Create a mock for the geocoding service."""
    mock_service = AsyncMock(spec=GeocodingService)
    mock_service.geocode_address.return_value = (test_coordinates, test_formatted_address)
    mock_service.validate_api_key.return_value = True
    mock_service.clear_cache.return_value = None
    return mock_service


@pytest.fixture
def mock_location_service(test_locations):
    """Create a mock for the location service."""
    mock_service = MagicMock(spec=LocationService)
    mock_service.locations = test_locations
    mock_service.find_nearest_location.return_value = (test_locations[0], 2.5)  # 2.5 km distance
    mock_service.find_nearest_n_locations.return_value = [(test_locations[0], 2.5), (test_locations[1], 3.8)]
    mock_service.get_location_by_id.side_effect = lambda id: next((loc for loc in test_locations if loc.id == id), None)
    mock_service.get_locations_by_region.side_effect = lambda region: [loc for loc in test_locations if loc.region == region]
    mock_service.get_locations_count.return_value = {"total": 3, "active": 2, "inactive": 1}
    mock_service.load_locations = AsyncMock(return_value=test_locations)
    mock_service.reload_locations = AsyncMock(return_value=test_locations)
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


# Test settings fixture
@pytest.fixture
def test_settings():
    """Create test settings with mock values."""
    return Settings(
        APP_NAME="Test Driver-Hub Matching Service",
        DEBUG=True,
        HOST="127.0.0.1",
        PORT=8000,
        HERE_API_KEY="test_here_api_key",
        DATA_SOURCE_TYPE="csv",
        CSV_FILE_PATH="tests/data/test_locations.csv",
        NOTIFICATION_METHOD="email",
        EMAIL_FROM="test@example.com",
        EMAIL_ADMIN="admin@example.com",
        CACHE_GEOCODING_RESULTS=True
    )


# Override settings for tests
@pytest.fixture
def override_settings(test_settings):
    """Override settings for tests."""
    original_get_settings = get_settings
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield
    app.dependency_overrides[get_settings] = original_get_settings


# FastAPI test client
@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def async_client():
    """Create an async test client for the FastAPI app."""
    return AsyncClient(app=app, base_url="http://test")


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


# Environment setup and teardown
@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up the test environment with required environment variables."""
    # Save original environment variables
    original_env = os.environ.copy()
    
    # Set test environment variables
    os.environ["HERE_API_KEY"] = "test_here_api_key"
    os.environ["DATA_SOURCE_TYPE"] = "csv"
    os.environ["CSV_FILE_PATH"] = "tests/data/test_locations.csv"
    os.environ["NOTIFICATION_METHOD"] = "email"
    os.environ["EMAIL_FROM"] = "test@example.com"
    os.environ["EMAIL_ADMIN"] = "admin@example.com"
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
