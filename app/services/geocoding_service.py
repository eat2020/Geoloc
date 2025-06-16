"""
Geocoding Service Module

This module provides geocoding functionality using the HERE API.
It converts addresses to geographic coordinates (latitude/longitude).

The service includes:
- Address geocoding
- Response parsing
- Error handling
- Optional result caching
"""

import logging
import httpx
import json
from typing import Dict, Any, Optional, Tuple
from functools import lru_cache
from datetime import datetime
import time

from app.core.config import settings
from app.models.location import Coordinates

# Configure logger
logger = logging.getLogger(__name__)


class GeocodingError(Exception):
    """Exception raised for errors in the geocoding process."""
    pass


class GeocodingService:
    """
    Service for geocoding addresses using the HERE API.
    
    This service converts street addresses to geographic coordinates
    using the HERE Geocoding API.
    """
    
    def __init__(self):
        """Initialize the geocoding service with API credentials."""
        self.api_key = settings.HERE_API_KEY.get_secret_value()
        self.base_url = settings.HERE_API_BASE_URL
        self.cache_enabled = settings.CACHE_GEOCODING_RESULTS
        self.geocode_endpoint = f"{self.base_url}/geocode"
        self._http_client = httpx.AsyncClient(timeout=10.0)
        
        logger.info("Geocoding service initialized with HERE API")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with client cleanup."""
        await self._http_client.aclose()
    
    async def geocode_address(self, address: str) -> Tuple[Coordinates, str]:
        """
        Geocode an address to coordinates using HERE API.
        
        Args:
            address: The address string to geocode
            
        Returns:
            Tuple containing:
                - Coordinates object with latitude and longitude
                - Formatted address string from the geocoding result
                
        Raises:
            GeocodingError: If geocoding fails or no results are found
        """
        if self.cache_enabled:
            # Try to get from cache first
            cached_result = self._get_cached_geocode(address)
            if cached_result:
                logger.debug(f"Cache hit for address: {address}")
                return cached_result
        
        start_time = time.time()
        logger.info(f"Geocoding address: {address}")
        
        # Prepare request parameters
        params = {
            "q": address,
            "apiKey": self.api_key,
            "limit": 1
        }
        
        try:
            # Make API request
            response = await self._http_client.get(self.geocode_endpoint, params=params)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            
            # Log response time
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"Geocoding completed in {elapsed:.2f}ms")
            
            # Process results
            if not data.get("items") or len(data["items"]) == 0:
                raise GeocodingError(f"No geocoding results found for address: {address}")
            
            # Extract the best match
            best_match = data["items"][0]
            
            # Extract coordinates
            position = best_match.get("position", {})
            coordinates = Coordinates(
                latitude=position.get("lat"),
                longitude=position.get("lng")
            )
            
            # Get formatted address
            formatted_address = best_match.get("title", address)
            
            # Cache the result if enabled
            if self.cache_enabled:
                self._cache_geocode_result(address, (coordinates, formatted_address))
            
            return coordinates, formatted_address
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during geocoding: {e.response.status_code} - {e.response.text}")
            raise GeocodingError(f"HERE API error: {e.response.status_code}")
            
        except httpx.RequestError as e:
            logger.error(f"Request error during geocoding: {str(e)}")
            raise GeocodingError(f"Request failed: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected error during geocoding: {str(e)}")
            raise GeocodingError(f"Geocoding failed: {str(e)}")
    
    @lru_cache(maxsize=1000)
    def _get_cached_geocode(self, address: str) -> Optional[Tuple[Coordinates, str]]:
        """
        Get geocoding result from cache if available.
        
        Args:
            address: The address to look up
            
        Returns:
            Cached result tuple or None if not in cache
        """
        # This is a placeholder for the actual implementation
        # The @lru_cache decorator handles the caching logic
        return None
    
    def _cache_geocode_result(self, address: str, result: Tuple[Coordinates, str]) -> None:
        """
        Cache a geocoding result.
        
        Args:
            address: The address used for geocoding
            result: The result tuple to cache
        """
        # Call the cached function to store the result
        self._get_cached_geocode(address)
        
    async def validate_api_key(self) -> bool:
        """
        Validate that the HERE API key is working.
        
        Returns:
            bool: True if the API key is valid, False otherwise
        """
        test_address = "1600 Pennsylvania Avenue, Washington DC"
        try:
            await self.geocode_address(test_address)
            return True
        except GeocodingError:
            logger.error("HERE API key validation failed")
            return False
    
    def clear_cache(self) -> None:
        """Clear the geocoding cache."""
        if hasattr(self._get_cached_geocode, 'cache_clear'):
            self._get_cached_geocode.cache_clear()
            logger.info("Geocoding cache cleared")
