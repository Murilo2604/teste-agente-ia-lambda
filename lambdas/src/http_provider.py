"""HTTP Provider for sending extraction results to backend endpoints."""

import requests
import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())

class HTTPProvider:
    """
    A provider class for sending HTTP requests to backend endpoints.
    """

    def __init__(self):
        pass

    def send_extraction_results(
        self,
        api_url: str,
        api_key: str,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Send extraction results to backend endpoint.

        Args:
            api_url: Base URL of the backend API
            api_key: API key for authentication
            payload: Dictionary containing the payload data
                - contract_id: UUID of the contract
                - output_path: S3 path prefix where results are stored
                - status: "success" or "error"
                - error_message: Optional error message if status is "error"
                - error_type: Optional error type if status is "error"

        Returns:
            True if the request was successful (2xx status code), False otherwise.
        """
        try:
            # Construct endpoint URL
            if api_url.endswith('/'):
                base_url = api_url.rstrip('/')
            else:
                base_url = api_url

            # If api_url already includes /api/v1, use it as-is, otherwise append it
            if "/api/v1" in base_url:
                endpoint = f"{base_url}/contract-to-extract/receive-extraction-results"
            else:
                endpoint = f"{base_url}/api/v1/contract-to-extract/receive-extraction-results"

            headers = {
                'x-api-key': api_key,
                'Content-Type': 'application/json'
            }

            logger.info(f"📤 Sending extraction results to: {endpoint}")
            logger.debug(f"Payload: {json.dumps(payload)}")

            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=30  # 30 seconds timeout
            )
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            logger.info(f"✓ Successfully sent results. Status: {response.status_code}")
            return True

        except requests.exceptions.Timeout:
            logger.error(f"❌ Request to {endpoint} timed out after 30 seconds.")
            return False
        except requests.exceptions.RequestException as e:
            status = e.response.status_code if e.response is not None else None
            # Treat 409 (results already received) as a success acknowledgment to avoid retries
            if status == 409:
                logger.info("⚠️ Backend responded 409 (results already received). Treating as success.")
                return True
            logger.error(f"❌ Failed to send results to {endpoint}: {e}")
            if e.response is not None:
                logger.error(f"Response status: {status}, body: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ An unexpected error occurred while sending results: {e}")
            return False

