"""
AWS Lambda Handler for Driver-Hub Matching Service

This module provides an AWS Lambda handler that wraps the FastAPI application
using Mangum, allowing the service to be deployed as a Lambda function behind
API Gateway.

Usage:
    - Deploy this file along with the rest of the application to AWS Lambda
    - Configure API Gateway to use this handler as the Lambda proxy

Example:
    In AWS Lambda configuration:
    - Handler: lambda_handler.handler
"""

import logging
from mangum import Mangum
from app.main import app

# Configure logging for AWS Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create Mangum handler
handler = Mangum(app, lifespan="off")

# Log startup
logger.info("Driver-Hub Matching Service Lambda handler initialized")
