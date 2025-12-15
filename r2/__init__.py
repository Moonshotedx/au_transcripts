"""
R2 Storage Module

This module provides Cloudflare R2 storage integration for
uploading and managing grade cards and transcripts.
"""

from .client import R2Client, get_r2_client
from .helper import (
    generate_batch_timestamp,
    generate_file_key,
    upload_grade_card,
    upload_transcript,
    get_presigned_url,
    download_file_from_r2,
    list_grade_cards,
    list_transcripts,
    list_batch_folders,
    get_file_content,
    get_latest_batch_folder,
    download_batch_as_zip
)

__all__ = [
    'R2Client',
    'get_r2_client',
    'generate_batch_timestamp',
    'generate_file_key',
    'upload_grade_card',
    'upload_transcript',
    'get_presigned_url',
    'download_file_from_r2',
    'list_grade_cards',
    'list_transcripts',
    'list_batch_folders',
    'get_file_content',
    'get_latest_batch_folder',
    'download_batch_as_zip'
]

