"""
R2 Helper Functions for Grade Cards and Transcripts

This module provides helper functions for uploading and managing
grade cards and transcripts in Cloudflare R2 storage.

Folder Structure:
- gradecards/{batch_timestamp}/{filename}.pdf
- transcripts/{batch_timestamp}/{filename}.pdf
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from .client import get_r2_client, R2Client


def generate_batch_timestamp() -> str:
    """
    Generate a timestamp string to be used as a folder name for batch uploads.
    Format: YYYYMMDD_HHMMSS
    
    Returns:
        Timestamp string (e.g., '20231215_143052')
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def generate_file_key(
    base_folder: str,
    batch_timestamp: str,
    regn_no: str,
    student_name: str
) -> str:
    """
    Generate the R2 object key for a file.
    
    Args:
        base_folder: Base folder name ('gradecards' or 'transcripts')
        batch_timestamp: Timestamp folder for this batch
        regn_no: Student registration number
        student_name: Student name
    
    Returns:
        R2 object key (e.g., 'gradecards/20231215_143052/AU21UG-001_John_Doe.pdf')
    """
    # Sanitize student name for filename
    safe_name = student_name.replace(' ', '_').replace('.', '').replace('/', '_')
    safe_regn_no = regn_no.replace('/', '_')
    
    filename = f"{safe_regn_no}_{safe_name}.pdf"
    return f"{base_folder}/{batch_timestamp}/{filename}"


def upload_grade_card(
    file_path: str,
    batch_timestamp: str,
    regn_no: str,
    student_name: str
) -> Tuple[bool, Optional[str]]:
    """
    Upload a grade card PDF to R2.
    
    Args:
        file_path: Local path to the PDF file
        batch_timestamp: Timestamp folder for this batch
        regn_no: Student registration number
        student_name: Student name
    
    Returns:
        Tuple of (success: bool, r2_key: Optional[str])
    """
    try:
        client = get_r2_client()
        r2_key = generate_file_key('gradecards', batch_timestamp, regn_no, student_name)
        
        success = client.upload_file(file_path, r2_key)
        
        if success:
            return True, r2_key
        return False, None
    except Exception as e:
        print(f"✗ Error uploading grade card to R2: {e}")
        return False, None


def upload_transcript(
    file_path: str,
    batch_timestamp: str,
    regn_no: str,
    student_name: str
) -> Tuple[bool, Optional[str]]:
    """
    Upload a transcript PDF to R2.
    
    Args:
        file_path: Local path to the PDF file
        batch_timestamp: Timestamp folder for this batch
        regn_no: Student registration number
        student_name: Student name
    
    Returns:
        Tuple of (success: bool, r2_key: Optional[str])
    """
    try:
        client = get_r2_client()
        r2_key = generate_file_key('transcripts', batch_timestamp, regn_no, student_name)
        
        success = client.upload_file(file_path, r2_key)
        
        if success:
            return True, r2_key
        return False, None
    except Exception as e:
        print(f"✗ Error uploading transcript to R2: {e}")
        return False, None


def get_presigned_url(r2_key: str, expiration: int = 3600) -> Optional[str]:
    """
    Get a presigned URL for downloading a file from R2.
    
    Args:
        r2_key: R2 object key
        expiration: URL expiration time in seconds (default: 1 hour)
    
    Returns:
        Presigned URL string, or None if error
    """
    try:
        client = get_r2_client()
        return client.get_file_url(r2_key, expiration)
    except Exception as e:
        print(f"✗ Error getting presigned URL: {e}")
        return None


def download_file_from_r2(r2_key: str, local_path: str) -> bool:
    """
    Download a file from R2 to local path.
    
    Args:
        r2_key: R2 object key
        local_path: Local path to save the file
    
    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_r2_client()
        return client.download_file(r2_key, local_path)
    except Exception as e:
        print(f"✗ Error downloading file from R2: {e}")
        return False


def list_grade_cards(batch_timestamp: Optional[str] = None) -> List[Dict[str, any]]:
    """
    List grade cards in R2.
    
    Args:
        batch_timestamp: Optional - filter by specific batch timestamp
    
    Returns:
        List of file information dictionaries
    """
    try:
        client = get_r2_client()
        prefix = f"gradecards/{batch_timestamp}/" if batch_timestamp else "gradecards/"
        return client.list_files(prefix)
    except Exception as e:
        print(f"✗ Error listing grade cards: {e}")
        return []


def list_transcripts(batch_timestamp: Optional[str] = None) -> List[Dict[str, any]]:
    """
    List transcripts in R2.
    
    Args:
        batch_timestamp: Optional - filter by specific batch timestamp
    
    Returns:
        List of file information dictionaries
    """
    try:
        client = get_r2_client()
        prefix = f"transcripts/{batch_timestamp}/" if batch_timestamp else "transcripts/"
        return client.list_files(prefix)
    except Exception as e:
        print(f"✗ Error listing transcripts: {e}")
        return []


def list_batch_folders(folder_type: str = 'gradecards') -> List[str]:
    """
    List all batch timestamp folders for a given type.
    
    Args:
        folder_type: 'gradecards' or 'transcripts'
    
    Returns:
        List of batch timestamp folder names
    """
    try:
        client = get_r2_client()
        files = client.list_files(f"{folder_type}/")
        
        # Extract unique folder names (batch timestamps)
        folders = set()
        for f in files:
            parts = f['key'].split('/')
            if len(parts) >= 2:
                folders.add(parts[1])
        
        return sorted(list(folders), reverse=True)  # Most recent first
    except Exception as e:
        print(f"✗ Error listing batch folders: {e}")
        return []


def get_file_content(r2_key: str) -> Optional[bytes]:
    """
    Get file content as bytes from R2.
    
    Args:
        r2_key: R2 object key
    
    Returns:
        File content as bytes, or None if error
    """
    try:
        client = get_r2_client()
        return client.get_file_content(r2_key)
    except Exception as e:
        print(f"✗ Error getting file content: {e}")
        return None


def get_latest_batch_folder(folder_type: str = 'gradecards') -> Optional[str]:
    """
    Get the latest (most recent) batch timestamp folder.
    
    Args:
        folder_type: 'gradecards' or 'transcripts'
    
    Returns:
        Latest batch timestamp folder name, or None if no folders exist
    """
    folders = list_batch_folders(folder_type)
    if folders:
        return folders[0]  # Already sorted in reverse order (most recent first)
    return None


def download_batch_as_zip(folder_type: str, batch_timestamp: Optional[str] = None) -> Tuple[Optional[bytes], str, int]:
    """
    Download all files from a batch folder and return as a ZIP archive.
    
    Args:
        folder_type: 'gradecards' or 'transcripts'
        batch_timestamp: Optional - specific batch timestamp. If None, uses latest.
    
    Returns:
        Tuple of (zip_bytes: Optional[bytes], batch_timestamp: str, file_count: int)
    """
    import io
    import zipfile
    
    try:
        # Get the batch timestamp to use
        if batch_timestamp is None:
            batch_timestamp = get_latest_batch_folder(folder_type)
        
        if not batch_timestamp:
            print(f"✗ No batch folders found for {folder_type}")
            return None, "", 0
        
        # List all files in the batch folder
        client = get_r2_client()
        prefix = f"{folder_type}/{batch_timestamp}/"
        files = client.list_files(prefix)
        
        if not files:
            print(f"✗ No files found in {prefix}")
            return None, batch_timestamp, 0
        
        # Create a ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_info in files:
                r2_key = file_info['key']
                filename = r2_key.split('/')[-1]
                
                # Get file content from R2
                content = client.get_file_content(r2_key)
                if content:
                    zip_file.writestr(filename, content)
        
        zip_buffer.seek(0)
        print(f"✓ Created ZIP with {len(files)} files from {prefix}")
        return zip_buffer.getvalue(), batch_timestamp, len(files)
    
    except Exception as e:
        print(f"✗ Error creating ZIP from batch: {e}")
        return None, batch_timestamp if batch_timestamp else "", 0
