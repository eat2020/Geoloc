"""
Location Service Module

This module provides functionality to load, manage, and query delivery hub locations.
It supports loading location data from different sources (CSV, Google Sheets, database)
and finding the nearest location to a given point using the Haversine formula.

The service includes:
- Loading locations from different data sources
- Finding the nearest location to a given point
- Calculating distances using the Haversine formula
- Caching location data for performance
"""

import logging
import csv
import json
import os
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import pandas as pd
import asyncio
from haversine import haversine, Unit
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import sqlalchemy
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.models.location import Location, Coordinates

# Configure logger
logger = logging.getLogger(__name__)


class LocationServiceError(Exception):
    """Exception raised for errors in the location service."""
    pass


class LocationService:
    """
    Service for managing delivery hub locations and finding the nearest location.
    
    This service loads location data from various sources (CSV, Google Sheets, database)
    and provides methods to find the nearest location to a given point.
    """
    
    def __init__(self):
        """Initialize the location service."""
        self.locations: List[Location] = []
        self.last_loaded: Optional[datetime] = None
        self.data_source_type = settings.DATA_SOURCE_TYPE
        logger.info(f"Location service initialized with {self.data_source_type} data source")
    
    async def load_locations(self) -> List[Location]:
        """
        Load locations from the configured data source.
        
        Returns:
            List[Location]: List of loaded location objects
            
        Raises:
            LocationServiceError: If loading locations fails
        """
        start_time = time.time()
        logger.info(f"Loading locations from {self.data_source_type}")
        
        try:
            if self.data_source_type == "csv":
                await self._load_from_csv()
            elif self.data_source_type == "google_sheets":
                await self._load_from_google_sheets()
            elif self.data_source_type == "postgres":
                await self._load_from_database()
            else:
                raise LocationServiceError(f"Unsupported data source type: {self.data_source_type}")
            
            # Update last loaded timestamp
            self.last_loaded = datetime.utcnow()
            
            # Log loading time and count
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"Loaded {len(self.locations)} locations in {elapsed:.2f}ms")
            
            return self.locations
            
        except Exception as e:
            logger.error(f"Failed to load locations: {str(e)}")
            raise LocationServiceError(f"Failed to load locations: {str(e)}")
    
    async def _load_from_csv(self) -> None:
        """
        Load locations from a CSV file.
        
        Raises:
            LocationServiceError: If loading from CSV fails
        """
        file_path = settings.CSV_FILE_PATH
        logger.info(f"Loading locations from CSV: {file_path}")
        
        if not os.path.exists(file_path):
            raise LocationServiceError(f"CSV file not found: {file_path}")
        
        try:
            # Use pandas for efficient CSV reading
            df = pd.read_csv(file_path)
            
            # Clear existing locations
            self.locations = []
            
            # Process each row
            for _, row in df.iterrows():
                try:
                    # Create Location object
                    location = Location(
                        id=str(row.get("id", "")),
                        name=row["name"],
                        address=row["address"],
                        city=row.get("city"),
                        state=row.get("state"),
                        postal_code=row.get("postal_code"),
                        country=row.get("country"),
                        coordinates=Coordinates(
                            latitude=float(row["latitude"]),
                            longitude=float(row["longitude"])
                        ),
                        region=row.get("region"),
                        type=row.get("type"),
                        active=bool(row.get("active", True))
                    )
                    
                    # Add to locations list
                    self.locations.append(location)
                    
                except KeyError as e:
                    logger.warning(f"Skipping row due to missing required field: {e}")
                except ValueError as e:
                    logger.warning(f"Skipping row due to invalid data: {e}")
            
            logger.info(f"Successfully loaded {len(self.locations)} locations from CSV")
            
        except Exception as e:
            logger.error(f"Error loading from CSV: {str(e)}")
            raise LocationServiceError(f"Error loading from CSV: {str(e)}")
    
    async def _load_from_google_sheets(self) -> None:
        """
        Load locations from a Google Sheet.
        
        Raises:
            LocationServiceError: If loading from Google Sheets fails
        """
        sheet_id = settings.GOOGLE_SHEETS_ID
        sheet_range = settings.GOOGLE_SHEETS_RANGE
        credentials_path = settings.GOOGLE_CREDENTIALS_JSON
        
        if not sheet_id:
            raise LocationServiceError("Google Sheets ID not configured")
        
        if not os.path.exists(credentials_path):
            raise LocationServiceError(f"Google credentials file not found: {credentials_path}")
        
        logger.info(f"Loading locations from Google Sheets: {sheet_id}")
        
        try:
            # Set up credentials and client
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
            client = gspread.authorize(credentials)
            
            # Open the spreadsheet and get the worksheet
            sheet = client.open_by_key(sheet_id).worksheet(sheet_range.split("!")[0])
            
            # Get all values
            data = sheet.get_all_records()
            
            # Clear existing locations
            self.locations = []
            
            # Process each row
            for row in data:
                try:
                    # Create Location object
                    location = Location(
                        id=str(row.get("id", "")),
                        name=row["name"],
                        address=row["address"],
                        city=row.get("city"),
                        state=row.get("state"),
                        postal_code=row.get("postal_code"),
                        country=row.get("country"),
                        coordinates=Coordinates(
                            latitude=float(row["latitude"]),
                            longitude=float(row["longitude"])
                        ),
                        region=row.get("region"),
                        type=row.get("type"),
                        active=bool(row.get("active", True))
                    )
                    
                    # Add to locations list
                    self.locations.append(location)
                    
                except KeyError as e:
                    logger.warning(f"Skipping row due to missing required field: {e}")
                except ValueError as e:
                    logger.warning(f"Skipping row due to invalid data: {e}")
            
            logger.info(f"Successfully loaded {len(self.locations)} locations from Google Sheets")
            
        except Exception as e:
            logger.error(f"Error loading from Google Sheets: {str(e)}")
            raise LocationServiceError(f"Error loading from Google Sheets: {str(e)}")
    
    async def _load_from_database(self) -> None:
        """
        Load locations from a database.
        
        Raises:
            LocationServiceError: If loading from database fails
        """
        if not settings.DATABASE_URL:
            raise LocationServiceError("Database URL not configured")
        
        database_url = settings.DATABASE_URL.get_secret_value()
        table_name = settings.DATABASE_TABLE
        
        logger.info(f"Loading locations from database table: {table_name}")
        
        try:
            # Create engine
            engine = create_engine(database_url)
            
            # Execute query
            query = f"SELECT * FROM {table_name} WHERE active = TRUE"
            
            # Use pandas to read from database
            df = pd.read_sql(query, engine)
            
            # Clear existing locations
            self.locations = []
            
            # Process each row
            for _, row in df.iterrows():
                try:
                    # Create Location object
                    location = Location(
                        id=str(row.get("id", "")),
                        name=row["name"],
                        address=row["address"],
                        city=row.get("city"),
                        state=row.get("state"),
                        postal_code=row.get("postal_code"),
                        country=row.get("country"),
                        coordinates=Coordinates(
                            latitude=float(row["latitude"]),
                            longitude=float(row["longitude"])
                        ),
                        region=row.get("region"),
                        type=row.get("type"),
                        active=bool(row.get("active", True))
                    )
                    
                    # Add to locations list
                    self.locations.append(location)
                    
                except KeyError as e:
                    logger.warning(f"Skipping row due to missing required field: {e}")
                except ValueError as e:
                    logger.warning(f"Skipping row due to invalid data: {e}")
            
            logger.info(f"Successfully loaded {len(self.locations)} locations from database")
            
        except Exception as e:
            logger.error(f"Error loading from database: {str(e)}")
            raise LocationServiceError(f"Error loading from database: {str(e)}")
    
    def find_nearest_location(self, coordinates: Coordinates) -> Tuple[Location, float]:
        """
        Find the nearest location to the given coordinates.
        
        Args:
            coordinates: The coordinates to find the nearest location to
            
        Returns:
            Tuple containing:
                - The nearest Location object
                - Distance to the nearest location in kilometers
                
        Raises:
            LocationServiceError: If no locations are loaded or no active locations found
        """
        if not self.locations:
            raise LocationServiceError("No locations loaded")
        
        # Filter active locations
        active_locations = [loc for loc in self.locations if loc.active]
        
        if not active_locations:
            raise LocationServiceError("No active locations found")
        
        # Calculate distances
        distances = []
        for location in active_locations:
            point1 = (coordinates.latitude, coordinates.longitude)
            point2 = (location.coordinates.latitude, location.coordinates.longitude)
            
            # Calculate distance using haversine formula
            distance = haversine(point1, point2, unit=Unit.KILOMETERS)
            distances.append((location, distance))
        
        # Find the minimum distance
        nearest_location, min_distance = min(distances, key=lambda x: x[1])
        
        logger.debug(f"Found nearest location: {nearest_location.name} at {min_distance:.2f}km")
        return nearest_location, min_distance
    
    def find_nearest_n_locations(self, coordinates: Coordinates, n: int = 3) -> List[Tuple[Location, float]]:
        """
        Find the nearest n locations to the given coordinates.
        
        Args:
            coordinates: The coordinates to find the nearest locations to
            n: Number of nearest locations to return
            
        Returns:
            List of tuples containing:
                - Location object
                - Distance to the location in kilometers
                
        Raises:
            LocationServiceError: If no locations are loaded or no active locations found
        """
        if not self.locations:
            raise LocationServiceError("No locations loaded")
        
        # Filter active locations
        active_locations = [loc for loc in self.locations if loc.active]
        
        if not active_locations:
            raise LocationServiceError("No active locations found")
        
        # Calculate distances
        distances = []
        for location in active_locations:
            point1 = (coordinates.latitude, coordinates.longitude)
            point2 = (location.coordinates.latitude, location.coordinates.longitude)
            
            # Calculate distance using haversine formula
            distance = haversine(point1, point2, unit=Unit.KILOMETERS)
            distances.append((location, distance))
        
        # Sort by distance and take top n
        nearest_locations = sorted(distances, key=lambda x: x[1])[:n]
        
        logger.debug(f"Found {len(nearest_locations)} nearest locations")
        return nearest_locations
    
    async def reload_locations(self) -> List[Location]:
        """
        Reload locations from the data source.
        
        Returns:
            List[Location]: Updated list of locations
            
        Raises:
            LocationServiceError: If reloading locations fails
        """
        logger.info("Reloading locations")
        return await self.load_locations()
    
    def get_location_by_id(self, location_id: str) -> Optional[Location]:
        """
        Get a location by its ID.
        
        Args:
            location_id: The ID of the location to find
            
        Returns:
            Location object if found, None otherwise
        """
        for location in self.locations:
            if location.id == location_id:
                return location
        return None
    
    def get_locations_by_region(self, region: str) -> List[Location]:
        """
        Get all locations in a specific region.
        
        Args:
            region: The region to filter by
            
        Returns:
            List of Location objects in the specified region
        """
        return [loc for loc in self.locations if loc.region == region]
    
    def get_locations_count(self) -> Dict[str, int]:
        """
        Get count statistics for locations.
        
        Returns:
            Dictionary with count statistics
        """
        active_count = len([loc for loc in self.locations if loc.active])
        inactive_count = len(self.locations) - active_count
        
        return {
            "total": len(self.locations),
            "active": active_count,
            "inactive": inactive_count
        }
    
    @staticmethod
    def calculate_distance(point1: Coordinates, point2: Coordinates) -> float:
        """
        Calculate the distance between two points using the Haversine formula.
        
        Args:
            point1: First coordinates
            point2: Second coordinates
            
        Returns:
            Distance in kilometers
        """
        coord1 = (point1.latitude, point1.longitude)
        coord2 = (point2.latitude, point2.longitude)
        
        return haversine(coord1, coord2, unit=Unit.KILOMETERS)
