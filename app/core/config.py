"""
Configuration module for the Driver-Hub Matching Service

This module uses Pydantic's BaseSettings to manage application configuration
from environment variables with sensible defaults.

Environment variables take precedence over default values.
"""

import os
from typing import Optional, Dict, Any, List
from pydantic import BaseSettings, Field, validator, SecretStr
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables with defaults."""
    
    # Application settings
    APP_NAME: str = "Driver-Hub Matching Service"
    DEBUG: bool = Field(default=False, env="DEBUG")
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    
    # HERE API settings
    HERE_API_KEY: SecretStr = Field(..., env="HERE_API_KEY")
    HERE_API_BASE_URL: str = Field(
        default="https://geocode.search.hereapi.com/v1", 
        env="HERE_API_BASE_URL"
    )
    
    # Data source settings
    DATA_SOURCE_TYPE: str = Field(
        default="csv", 
        env="DATA_SOURCE_TYPE"
    )  # Options: "csv", "google_sheets", "postgres"
    
    # CSV settings
    CSV_FILE_PATH: Optional[str] = Field(default="data/locations.csv", env="CSV_FILE_PATH")
    
    # Google Sheets settings
    GOOGLE_SHEETS_ID: Optional[str] = Field(default=None, env="GOOGLE_SHEETS_ID")
    GOOGLE_SHEETS_RANGE: Optional[str] = Field(default="Locations!A1:F", env="GOOGLE_SHEETS_RANGE")
    GOOGLE_CREDENTIALS_JSON: Optional[str] = Field(default="credentials.json", env="GOOGLE_CREDENTIALS_JSON")
    
    # Database settings
    DATABASE_URL: Optional[SecretStr] = Field(default=None, env="DATABASE_URL")
    DATABASE_TABLE: Optional[str] = Field(default="delivery_locations", env="DATABASE_TABLE")
    
    # Notification settings
    NOTIFICATION_METHOD: str = Field(
        default="email", 
        env="NOTIFICATION_METHOD"
    )  # Options: "email", "webhook", "both"
    
    # Email settings (SendGrid)
    SENDGRID_API_KEY: Optional[SecretStr] = Field(default=None, env="SENDGRID_API_KEY")
    EMAIL_FROM: Optional[str] = Field(default="noreply@example.com", env="EMAIL_FROM")
    EMAIL_ADMIN: Optional[str] = Field(default="admin@example.com", env="EMAIL_ADMIN")
    EMAIL_SUBJECT_TEMPLATE: Optional[str] = Field(
        default="Your Nearest Delivery Hub: {hub_name}",
        env="EMAIL_SUBJECT_TEMPLATE"
    )
    
    # Mailgun settings
    MAILGUN_API_KEY: Optional[SecretStr] = Field(default=None, env="MAILGUN_API_KEY")
    MAILGUN_DOMAIN: Optional[str] = Field(default=None, env="MAILGUN_DOMAIN")
    
    # Webhook settings
    WEBHOOK_URL: Optional[str] = Field(default=None, env="WEBHOOK_URL")
    WEBHOOK_SECRET: Optional[SecretStr] = Field(default=None, env="WEBHOOK_SECRET")
    
    # Cache settings
    CACHE_GEOCODING_RESULTS: bool = Field(default=True, env="CACHE_GEOCODING_RESULTS")
    CACHE_TTL_SECONDS: int = Field(default=86400, env="CACHE_TTL_SECONDS")  # 24 hours
    
    # Typeform webhook settings
    TYPEFORM_WEBHOOK_SECRET: Optional[SecretStr] = Field(default=None, env="TYPEFORM_WEBHOOK_SECRET")
    
    @validator("DATA_SOURCE_TYPE")
    def validate_data_source_type(cls, v):
        """Validate that the data source type is one of the supported options."""
        if v not in ["csv", "google_sheets", "postgres"]:
            raise ValueError("DATA_SOURCE_TYPE must be one of: csv, google_sheets, postgres")
        return v
    
    @validator("NOTIFICATION_METHOD")
    def validate_notification_method(cls, v):
        """Validate that the notification method is one of the supported options."""
        if v not in ["email", "webhook", "both"]:
            raise ValueError("NOTIFICATION_METHOD must be one of: email, webhook, both")
        return v
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Create and cache a Settings instance.
    
    Returns:
        Settings: Application settings
    """
    return Settings()


# Create a settings instance for importing
settings = get_settings()
