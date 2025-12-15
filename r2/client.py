"""
Cloudflare R2 Client for Python
A simple client for interacting with Cloudflare R2 storage using boto3.
"""

import os
import boto3
from botocore.exceptions import ClientError
from typing import Optional, List, Dict
from dotenv import load_dotenv


class R2Client:
    """Client for interacting with Cloudflare R2 storage."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern to reuse client across the application."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None
    ):
        """
        Initialize R2 client.
        
        Args:
            account_id: Cloudflare account ID (optional, reads from env if not provided)
            access_key_id: R2 access key ID (optional, reads from env if not provided)
            secret_access_key: R2 secret access key (optional, reads from env if not provided)
            bucket_name: R2 bucket name (optional, reads from env if not provided)
            endpoint_url: R2 endpoint URL (optional, reads from env if not provided)
        """
        if self._initialized:
            return
            
        # Load environment variables
        load_dotenv()
        
        # Get credentials from parameters or environment
        self.account_id = account_id or os.getenv('R2_ACCOUNT_ID')
        self.access_key_id = access_key_id or os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = secret_access_key or os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket_name = bucket_name or os.getenv('R2_BUCKET_NAME')
        self.endpoint_url = endpoint_url or os.getenv('R2_ENDPOINT_URL')
        
        # Validate required credentials
        if not all([self.access_key_id, self.secret_access_key, self.bucket_name, self.endpoint_url]):
            raise ValueError(
                "Missing required R2 credentials. Please provide them as parameters "
                "or set them in environment variables (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, "
                "R2_BUCKET_NAME, R2_ENDPOINT_URL)"
            )
        
        # Initialize S3 client configured for R2
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name='auto'  # R2 uses 'auto' for region
        )
        
        self._initialized = True
    
    def upload_file(self, file_path: str, object_name: Optional[str] = None) -> bool:
        """
        Upload a file to R2 bucket.
        
        Args:
            file_path: Path to the file to upload
            object_name: S3 object name (optional, uses file basename if not provided)
        
        Returns:
            True if file was uploaded successfully, False otherwise
        """
        if object_name is None:
            object_name = os.path.basename(file_path)
        
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_name)
            print(f"✓ Successfully uploaded {file_path} to {object_name}")
            return True
        except FileNotFoundError:
            print(f"✗ Error: File {file_path} not found")
            return False
        except ClientError as e:
            print(f"✗ Error uploading file: {e}")
            return False
    
    def upload_data(self, data: bytes, object_name: str) -> bool:
        """
        Upload bytes data to R2 bucket.
        
        Args:
            data: Bytes data to upload
            object_name: S3 object name
        
        Returns:
            True if data was uploaded successfully, False otherwise
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_name,
                Body=data
            )
            print(f"✓ Successfully uploaded data to {object_name}")
            return True
        except ClientError as e:
            print(f"✗ Error uploading data: {e}")
            return False
    
    def download_file(self, object_name: str, file_path: str) -> bool:
        """
        Download a file from R2 bucket.
        
        Args:
            object_name: S3 object name to download
            file_path: Local path where file will be saved
        
        Returns:
            True if file was downloaded successfully, False otherwise
        """
        try:
            self.s3_client.download_file(self.bucket_name, object_name, file_path)
            print(f"✓ Successfully downloaded {object_name} to {file_path}")
            return True
        except ClientError as e:
            print(f"✗ Error downloading file: {e}")
            return False
    
    def get_file_content(self, object_name: str) -> Optional[bytes]:
        """
        Get file content as bytes from R2 bucket.
        
        Args:
            object_name: S3 object name
        
        Returns:
            File content as bytes, or None if error occurred
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=object_name
            )
            content = response['Body'].read()
            print(f"✓ Successfully retrieved content from {object_name}")
            return content
        except ClientError as e:
            print(f"✗ Error getting file content: {e}")
            return None
    
    def list_files(self, prefix: str = '') -> List[Dict[str, any]]:
        """
        List files in R2 bucket.
        
        Args:
            prefix: Filter results to keys that begin with the prefix (optional)
        
        Returns:
            List of dictionaries containing file information
        """
        try:
            files = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get('Contents', []):
                    files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified']
                    })
            
            if not files:
                print(f"No files found with prefix '{prefix}'")
            else:
                print(f"✓ Found {len(files)} file(s)")
            return files
        except ClientError as e:
            print(f"✗ Error listing files: {e}")
            return []
    
    def delete_file(self, object_name: str) -> bool:
        """
        Delete a file from R2 bucket.
        
        Args:
            object_name: S3 object name to delete
        
        Returns:
            True if file was deleted successfully, False otherwise
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_name
            )
            print(f"✓ Successfully deleted {object_name}")
            return True
        except ClientError as e:
            print(f"✗ Error deleting file: {e}")
            return False
    
    def file_exists(self, object_name: str) -> bool:
        """
        Check if a file exists in R2 bucket.
        
        Args:
            object_name: S3 object name to check
        
        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=object_name
            )
            return True
        except ClientError:
            return False
    
    def get_file_url(self, object_name: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for a file in R2 bucket.
        
        Args:
            object_name: S3 object name
            expiration: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            Presigned URL string, or None if error occurred
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_name
                },
                ExpiresIn=expiration
            )
            print(f"✓ Generated presigned URL for {object_name} (expires in {expiration}s)")
            return url
        except ClientError as e:
            print(f"✗ Error generating presigned URL: {e}")
            return None


def get_r2_client() -> R2Client:
    """
    Get or create the singleton R2 client instance.
    
    Returns:
        R2Client instance
    """
    return R2Client()
