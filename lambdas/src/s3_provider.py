import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from io import BytesIO
from typing import Optional, Union, Dict, Any
import os
import pandas as pd
import dotenv
import logging

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

env = dotenv.load_dotenv()

class S3Provider:
    """
    A provider class for interacting with Amazon S3.
    
    This class provides methods for downloading files from S3 as buffers,
    uploading files to S3, and reading common file formats (CSV, Parquet)
    directly into pandas DataFrames.
    
    Attributes:
        s3_client: The boto3 S3 client instance used for AWS operations
    """
    
    def __init__(self, credentials: dict[str, str] = None):
        """
        Initialize the S3Provider with a boto3 S3 client.
        
        Authentication priority:
        1. Explicit credentials passed as parameter
        2. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION)
        3. Default AWS credentials chain (IAM role, instance profile, etc.)
        
        Args:
            credentials: Optional dict with keys:
                - aws_access_key_id: AWS access key ID
                - aws_secret_access_key: AWS secret access key
                - region_name: AWS region (defaults to AWS_REGION env var or us-east-1)
        """
        logger.info("🔧 Initializing S3Provider...")
        
        # Build credentials dict from parameter or environment
        if credentials is None:
            credentials = {}
            logger.info("📝 No explicit credentials dict passed to constructor")
        else:
            logger.info("📝 Explicit credentials dict provided to constructor")
        
        # Get credentials from environment if not provided explicitly
        aws_access_key_id = os.getenv('CUSTOM_AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('CUSTOM_AWS_SECRET_ACCESS_KEY')
        region_name = os.getenv('CUSTOM_AWS_DEFAULT_REGION')
        
        # Log credential detection status (with masking for security)
        logger.info("🔍 Checking environment variables:")
        logger.info(f"   - CUSTOM_AWS_ACCESS_KEY_ID: {'✓ Found' if aws_access_key_id else '✗ Not found'}")
        if aws_access_key_id:
            masked_key = f"{aws_access_key_id[:4]}...{aws_access_key_id[-4:]}" if len(aws_access_key_id) > 8 else "****"
            logger.info(f"   - Access Key ID (masked): {masked_key}")
        logger.info(f"   - CUSTOM_AWS_SECRET_ACCESS_KEY: {'✓ Found' if aws_secret_access_key else '✗ Not found'}")
        if aws_secret_access_key:
            logger.info(f"   - Secret Key (masked): ****{aws_secret_access_key[-4:]}")
        logger.info(f"   - CUSTOM_AWS_DEFAULT_REGION: {region_name if region_name else '✗ Not found'}")
        
        # Also check standard AWS environment variables
        standard_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        standard_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        standard_region = os.getenv('AWS_DEFAULT_REGION')
        aws_session_token = os.getenv('AWS_SESSION_TOKEN')
        
        logger.info("🔍 Checking standard AWS environment variables:")
        logger.info(f"   - AWS_ACCESS_KEY_ID: {'✓ Found' if standard_access_key else '✗ Not found'}")
        logger.info(f"   - AWS_SECRET_ACCESS_KEY: {'✓ Found' if standard_secret_key else '✗ Not found'}")
        logger.info(f"   - AWS_DEFAULT_REGION: {standard_region if standard_region else '✗ Not found'}")
        logger.info(f"   - AWS_SESSION_TOKEN: {'✓ Found (IAM Role/STS)' if aws_session_token else '✗ Not found'}")
        
        # Build boto3 client parameters
        client_params = {}
        
        # Only include access key and secret if both are provided
        # If not provided, boto3 will use default credential chain (IAM role, etc.)
        if aws_access_key_id and aws_secret_access_key:
            client_params['aws_access_key_id'] = aws_access_key_id
            client_params['aws_secret_access_key'] = aws_secret_access_key
            logger.info("🔑 Using explicit AWS credentials from CUSTOM_* environment variables")
        else:
            logger.info("🔐 Using default AWS credential chain (IAM role/profile/environment)")
        
        # Include region if specified
        if region_name:
            client_params['region_name'] = region_name
            logger.info(f"🌍 Using region: {region_name}")
        else:
            logger.info(f"🌍 No custom region specified, boto3 will use default (standard env: {standard_region or 'not set'})")
        
        # Localstack support (commented out, but structure preserved)
        # endpoint_url = credentials.get('endpoint_url') or os.getenv('S3_ENDPOINT')
        # if endpoint_url:
        #     client_params['endpoint_url'] = endpoint_url
        #     # Use path-style addressing for Localstack
        #     config = Config(s3={'addressing_style': 'path'})
        #     client_params['config'] = config

        try:
            # Log sanitized client params (remove sensitive data)
            sanitized_params = {}
            for key, value in client_params.items():
                if key == 'aws_access_key_id':
                    sanitized_params[key] = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "****"
                elif key == 'aws_secret_access_key':
                    sanitized_params[key] = f"****{value[-4:]}"
                else:
                    sanitized_params[key] = value
            logger.info(f"⚙️ Client params (sanitized): {sanitized_params}")
            
            self.s3_client = boto3.client('s3', **client_params)
            
            # Try to get caller identity for additional debugging
            try:
                sts_client = boto3.client('sts', **client_params)
                identity = sts_client.get_caller_identity()
                logger.info(f"✅ Successfully initialized S3 client")
                logger.info(f"   - Account: {identity.get('Account', 'N/A')}")
                logger.info(f"   - UserId: {identity.get('UserId', 'N/A')}")
                logger.info(f"   - ARN: {identity.get('Arn', 'N/A')}")
            except Exception as sts_error:
                logger.warning(f"⚠️ Could not get caller identity (STS): {sts_error}")
                logger.info("✅ S3 client initialized (caller identity check failed)")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3 client: {e}")
            raise ValueError(f"Failed to initialize S3 client: {e}")

    def get_object(self, bucket_name: str, key: str) -> Dict[str, Any]:
        """
        Get an object from S3 and return the raw response.
        
        This method returns the complete S3 object response including metadata,
        which can be useful when you need access to object properties like
        content type, size, or custom metadata.
        
        Args:
            bucket_name: The name of the S3 bucket containing the object
            key: The S3 object key (path) within the bucket
            
        Returns:
            Dict[str, Any]: The complete S3 object response
            
        Raises:
            botocore.exceptions.ClientError: If the object doesn't exist or
                access is denied
        """
        return self.s3_client.get_object(Bucket=bucket_name, Key=key)

    def put_object(self, bucket_name: str, key: str, body: bytes) -> Dict[str, Any]:
        """
        Upload bytes data to S3 as an object.
        
        This method uploads raw bytes data to S3. The data will be stored
        as-is without any encoding or compression applied by this method.
        
        Args:
            bucket_name: The name of the S3 bucket to upload to
            key: The S3 object key (path) where the data will be stored
            body: The bytes data to upload
            
        Returns:
            Dict[str, Any]: The S3 put object response containing
                metadata like ETag and version ID
            
        Raises:
            botocore.exceptions.ClientError: If the bucket doesn't exist or
                access is denied
        """
        return self.s3_client.put_object(Bucket=bucket_name, Key=key, Body=body)

    def create_bucket(self, bucket_name: str, region_name: Optional[str] = None) -> dict:
        """
        Create an S3 bucket. Handles us-east-1 special case and Localstack.

        If region is us-east-1, AWS does not require CreateBucketConfiguration.
        For any other region, CreateBucketConfiguration is required.
        """
        effective_region = (
            region_name
            or getattr(self.s3_client.meta, 'region_name', None)
            or os.getenv('AWS_DEFAULT_REGION')
            or 'us-east-1'
        )

        params: dict[str, Union[str, dict[str, str]]] = {'Bucket': bucket_name}
        if effective_region != 'us-east-1':
            params['CreateBucketConfiguration'] = {'LocationConstraint': effective_region}
        return self.s3_client.create_bucket(**params)

    def ensure_bucket(self, bucket_name: str, region_name: Optional[str] = None) -> None:
        """
        Ensure an S3 bucket exists; create it if missing.
        """
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            # In practice, head_bucket may return 404, 400/301 for region mismatch, or NoSuchBucket
            if error_code in {'404', 'NoSuchBucket'}:
                self.create_bucket(bucket_name, region_name=region_name)
            else:
                # If it's a different error, re-raise
                raise
    
    def download_file(self, bucket_name: str, key: str) -> BytesIO:
        """
        Download a file from S3 and return a BytesIO buffer.
        
        This method downloads the complete file content from S3 and returns
        it as a BytesIO buffer. The buffer is positioned at the beginning
        and ready for reading. This is useful when you need to work with
        the file content in memory without saving to disk.
        
        Args:
            bucket_name: The name of the S3 bucket containing the file
            key: The S3 object key (path) of the file to download
            
        Returns:
            BytesIO: A buffer containing the file content, positioned at
                the beginning for reading
            
        Raises:
            botocore.exceptions.ClientError: If the file doesn't exist or
                access is denied
                
        Example:
            >>> buffer = s3_provider.download_file('my-bucket', 'data/file.txt')
            >>> content = buffer.read().decode('utf-8')
            >>> buffer.seek(0)  # Reset position for another read
        """
        logger.info("📥 Starting download_file operation")
        logger.info(f"   - Bucket: {bucket_name}")
        logger.info(f"   - Key: {key}")
        
        try:
            # Get the object from S3
            logger.info("🔄 Calling s3_client.get_object()...")
            response = self.s3_client.get_object(Bucket=bucket_name, Key=key)
            
            # Log metadata from response
            content_length = response.get('ContentLength', 0)
            content_type = response.get('ContentType', 'unknown')
            last_modified = response.get('LastModified', 'unknown')
            
            logger.info(f"✅ Successfully retrieved object metadata:")
            logger.info(f"   - Content-Length: {content_length:,} bytes ({content_length / 1024 / 1024:.2f} MB)")
            logger.info(f"   - Content-Type: {content_type}")
            logger.info(f"   - Last-Modified: {last_modified}")
            logger.info(f"   - ETag: {response.get('ETag', 'unknown')}")
            
            # Read the file content
            logger.info("📖 Reading file content from response body...")
            file_content = response['Body'].read()
            actual_size = len(file_content)
            logger.info(f"✅ Successfully read {actual_size:,} bytes from response body")
            
            if actual_size != content_length:
                logger.warning(f"⚠️ Size mismatch! Expected {content_length:,} bytes, got {actual_size:,} bytes")
            
            # Create a BytesIO buffer
            logger.info("💾 Creating BytesIO buffer...")
            buffer = BytesIO(file_content)
            buffer.seek(0)  # Reset position to beginning
            logger.info(f"✅ Buffer created successfully (position: {buffer.tell()}, size: {len(buffer.getvalue()):,} bytes)")
            
            logger.info("✅ download_file operation completed successfully")
            return buffer
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"❌ ClientError during download_file:")
            logger.error(f"   - Error Code: {error_code}")
            logger.error(f"   - Error Message: {error_message}")
            logger.error(f"   - Bucket: {bucket_name}")
            logger.error(f"   - Key: {key}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during download_file:")
            logger.error(f"   - Error Type: {type(e).__name__}")
            logger.error(f"   - Error Message: {str(e)}")
            logger.error(f"   - Bucket: {bucket_name}")
            logger.error(f"   - Key: {key}")
            raise
    
    def download_file_to_path(self, bucket_name: str, key: str, local_path: str) -> str:
        """
        Download a file from S3 to a local file path.
        
        This method downloads a file from S3 and saves it to the specified
        local file path. The directory containing the file will be created
        if it doesn't exist.
        
        Args:
            bucket_name: The name of the S3 bucket containing the file
            key: The S3 object key (path) of the file to download
            local_path: The local file path where the file should be saved
            
        Returns:
            str: The local file path where the file was saved
            
        Raises:
            botocore.exceptions.ClientError: If the file doesn't exist or
                access is denied
                
        Example:
            >>> s3_provider.download_file_to_path('my-bucket', 'data/file.pdf', '/tmp/file.pdf')
            '/tmp/file.pdf'
        """
        logger.info("📥 Starting download_file_to_path operation")
        logger.info(f"   - Bucket: {bucket_name}")
        logger.info(f"   - Key: {key}")
        logger.info(f"   - Local Path: {local_path}")
        
        try:
            # Create directory if it doesn't exist
            directory = os.path.dirname(local_path) if os.path.dirname(local_path) else '.'
            logger.info(f"📁 Ensuring directory exists: {directory}")
            os.makedirs(directory, exist_ok=True)
            logger.info(f"✅ Directory ready")
            
            # Download file
            logger.info("🔄 Calling s3_client.download_file()...")
            self.s3_client.download_file(bucket_name, key, local_path)
            
            # Verify file was created and get size
            if os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                logger.info(f"✅ File downloaded successfully:")
                logger.info(f"   - Path: {local_path}")
                logger.info(f"   - Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
            else:
                logger.error("❌ File not found after download operation")
            
            logger.info("✅ download_file_to_path operation completed successfully")
            return local_path
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"❌ ClientError during download_file_to_path:")
            logger.error(f"   - Error Code: {error_code}")
            logger.error(f"   - Error Message: {error_message}")
            logger.error(f"   - Bucket: {bucket_name}")
            logger.error(f"   - Key: {key}")
            logger.error(f"   - Local Path: {local_path}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during download_file_to_path:")
            logger.error(f"   - Error Type: {type(e).__name__}")
            logger.error(f"   - Error Message: {str(e)}")
            logger.error(f"   - Bucket: {bucket_name}")
            logger.error(f"   - Key: {key}")
            logger.error(f"   - Local Path: {local_path}")
            raise
    
    def upload_file_from_path(self, local_path: str, bucket_name: str, key: str, extra_args: Optional[dict] = None) -> str:
        """
        Upload a local file to S3.
        
        This method uploads a file from the local filesystem to S3.
        
        Args:
            local_path: The local file path to upload
            bucket_name: The name of the S3 bucket to upload to
            key: The S3 object key (path) where the file will be stored
            extra_args: Optional extra arguments for upload (e.g., ContentType, Metadata)
            
        Returns:
            str: The S3 URI of the uploaded file (s3://bucket/key)
            
        Raises:
            FileNotFoundError: If the local file doesn't exist
            botocore.exceptions.ClientError: If the bucket doesn't exist or
                access is denied
                
        Example:
            >>> s3_provider.upload_file_from_path('/tmp/file.pdf', 'my-bucket', 'data/file.pdf')
            's3://my-bucket/data/file.pdf'
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        # Upload file
        self.s3_client.upload_file(local_path, bucket_name, key, ExtraArgs=extra_args)
        
        return f"s3://{bucket_name}/{key}"
    
    def upload_bytes(self, data: bytes, bucket_name: str, key: str, content_type: Optional[str] = None) -> str:
        """
        Upload bytes data to S3.
        
        This method uploads raw bytes data to S3 with optional content type.
        
        Args:
            data: The bytes data to upload
            bucket_name: The name of the S3 bucket to upload to
            key: The S3 object key (path) where the data will be stored
            content_type: Optional content type (e.g., 'image/png', 'application/json')
            
        Returns:
            str: The S3 URI of the uploaded object (s3://bucket/key)
            
        Raises:
            botocore.exceptions.ClientError: If the bucket doesn't exist or
                access is denied
                
        Example:
            >>> s3_provider.upload_bytes(b'...', 'my-bucket', 'data/file.bin', 'application/octet-stream')
            's3://my-bucket/data/file.bin'
        """
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        
        self.s3_client.put_object(Bucket=bucket_name, Key=key, Body=data, **extra_args)
        
        return f"s3://{bucket_name}/{key}"
    
    def get_file_as_bytes(self, bucket_name: str, key: str) -> bytes:
        """
        Get file content as raw bytes directly from S3.
        
        This method is a convenience function that downloads the file content
        and returns it as raw bytes. Unlike download_file(), this method
        doesn't create a BytesIO buffer, making it more memory efficient
        when you only need the bytes data.
        
        Args:
            bucket_name: The name of the S3 bucket containing the file
            key: The S3 object key (path) of the file to download
            
        Returns:
            bytes: The raw file content as bytes
            
        Raises:
            botocore.exceptions.ClientError: If the file doesn't exist or
                access is denied
                
        Example:
            >>> file_bytes = s3_provider.get_file_as_bytes('my-bucket', 'data/file.bin')
            >>> # Process bytes directly
        """
        logger.info("📥 Starting get_file_as_bytes operation")
        logger.info(f"   - Bucket: {bucket_name}")
        logger.info(f"   - Key: {key}")
        
        try:
            logger.info("🔄 Calling s3_client.get_object()...")
            response = self.s3_client.get_object(Bucket=bucket_name, Key=key)
            
            # Log metadata
            content_length = response.get('ContentLength', 0)
            logger.info(f"✅ Object retrieved, expected size: {content_length:,} bytes ({content_length / 1024 / 1024:.2f} MB)")
            
            logger.info("📖 Reading bytes from response body...")
            file_bytes = response['Body'].read()
            actual_size = len(file_bytes)
            
            logger.info(f"✅ Successfully read {actual_size:,} bytes")
            if actual_size != content_length:
                logger.warning(f"⚠️ Size mismatch! Expected {content_length:,} bytes, got {actual_size:,} bytes")
            
            logger.info("✅ get_file_as_bytes operation completed successfully")
            return file_bytes
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"❌ ClientError during get_file_as_bytes:")
            logger.error(f"   - Error Code: {error_code}")
            logger.error(f"   - Error Message: {error_message}")
            logger.error(f"   - Bucket: {bucket_name}")
            logger.error(f"   - Key: {key}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during get_file_as_bytes:")
            logger.error(f"   - Error Type: {type(e).__name__}")
            logger.error(f"   - Error Message: {str(e)}")
            logger.error(f"   - Bucket: {bucket_name}")
            logger.error(f"   - Key: {key}")
            raise
    
    def read_parquet_to_df(self, bucket_name: str, key: str, **kwargs) -> pd.DataFrame:
        """
        Download a Parquet file from S3 and return it as a pandas DataFrame.
        
        This method downloads a Parquet file from S3 and reads it directly into
        a pandas DataFrame. It performs a file extension check to ensure
        the file is actually a Parquet file before attempting to read it.
        
        Args:
            bucket_name: The name of the S3 bucket containing the Parquet file
            key: The S3 object key (path) of the Parquet file (must end with .parquet)
            **kwargs: Additional arguments to pass to pd.read_parquet(), such as:
                - columns: List of column names to read
                - engine: Parquet engine to use ('pyarrow' or 'fastparquet')
                - dtype: Data types for columns
                
        Returns:
            pd.DataFrame: A pandas DataFrame containing the Parquet data
            
        Raises:
            ValueError: If the file key doesn't end with .parquet
            botocore.exceptions.ClientError: If the file doesn't exist or
                access is denied
            pyarrow.lib.ArrowInvalid: If the Parquet file is corrupted or
                cannot be read
                
        Example:
            >>> df = s3_provider.read_parquet_to_df('my-bucket', 'data/sales.parquet')
            >>> df = s3_provider.read_parquet_to_df('my-bucket', 'data/sales.parquet',
            ...                                     columns=['date', 'amount', 'category'])
        """
        if not key.lower().endswith('.parquet'):
            raise ValueError(f"File key '{key}' does not have a .parquet extension")
        
        buffer = self.download_file(bucket_name, key)
        return pd.read_parquet(buffer, **kwargs)