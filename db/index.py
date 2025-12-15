"""
Centralized Database Configuration Module

This module provides centralized database configuration and connection utilities
for both PostgreSQL and NocoDB API access across the application.
Configuration is loaded from environment variables using python-dotenv.
"""

import os
import psycopg2
import requests
from psycopg2 import Error
from dotenv import load_dotenv
from urllib.parse import quote, urlparse

# Load environment variables from .env file
load_dotenv()

# --- PostgreSQL Database Configuration ---
DB_HOST = os.getenv("DB_HOST", "33.0.0.103")
DB_NAME = os.getenv("DB_NAME", "root_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_PORT = os.getenv("DB_PORT", "5432")

# --- NocoDB API Configuration ---
NOCODB_API_BASE = os.getenv("NOCODB_API_BASE", "http://33.0.0.103:8080/api/v1/db/data/v1/Atria_University")
NOCODB_API_TOKEN = os.getenv("NOCODB_API_TOKEN", "q_t3MWJ75zVKkektCDRYIr_f1L2Fy1aK8hw44kKk")

NOCODB_HEADERS = {
    "xc-token": NOCODB_API_TOKEN,
    "Content-Type": "application/json"
}

# --- NocoDB Schema/Table Constants ---
NOCODB_SCHEMA = os.getenv("NOCODB_SCHEMA", "p7s9v2dsl9limhd")
STUDENT_DETAILS_TABLE = "student_details"
STUDENT_COURSES_DETAILS_TABLE = "student_courses_details"
STUDENTS_PHOTOS_TABLE = "students_photos"


def get_db_connection():
    """
    Establishes and returns a PostgreSQL database connection.
    
    Returns:
        psycopg2.connection: Database connection object if successful, None otherwise
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        return conn
    except Error as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        return None


def get_nocodb_config():
    """
    Returns NocoDB configuration as a dictionary.
    
    Returns:
        dict: Configuration dictionary with API base URL, token, and headers
    """
    return {
        "api_base": NOCODB_API_BASE,
        "api_token": NOCODB_API_TOKEN,
        "headers": NOCODB_HEADERS,
        "schema": NOCODB_SCHEMA,
        "student_details_table": STUDENT_DETAILS_TABLE,
        "student_courses_details_table": STUDENT_COURSES_DETAILS_TABLE,
        "students_photos_table": STUDENTS_PHOTOS_TABLE
    }


def fetch_student_photo_url(regn_no):
    """
    Fetches student photo URL from NocoDB students_photos table.
    
    Args:
        regn_no: Student registration number (REG_NO in the table)
    
    Returns:
        str: The STUDENT_IMAGE URL if found, None otherwise
    """
    if not regn_no:
        return None
    
    # Extract base URL from NOCODB_API_BASE (e.g., http://33.0.0.103:8080)
    parsed_url = urlparse(NOCODB_API_BASE)
    nocodb_base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    # Build filter for REG_NO using NocoDB where syntax
    filter_segment = f'(REG_NO,eq,{regn_no})'
    encoded_filter = quote(filter_segment)
    
    get_url = f"{NOCODB_API_BASE}/{STUDENTS_PHOTOS_TABLE}?where={encoded_filter}"
    
    try:
        response = requests.get(get_url, headers=NOCODB_HEADERS, timeout=30)
        
        if response.status_code == 200:
            response_json = response.json()
            if response_json.get('list') and len(response_json['list']) > 0:
                record = response_json['list'][0]
                student_image = record.get('STUDENT_IMAGE')
                
                # Handle NocoDB attachment format (array of objects)
                if isinstance(student_image, list) and len(student_image) > 0:
                    attachment = student_image[0]
                    
                    # Try different URL fields in order of preference
                    # 1. Full URL (url or signedUrl)
                    if attachment.get('url'):
                        return attachment['url']
                    if attachment.get('signedUrl'):
                        return attachment['signedUrl']
                    
                    # 2. Relative path - construct full URL
                    if attachment.get('path'):
                        full_url = f"{nocodb_base_url}/{attachment['path']}"
                        print(f"  Constructed photo URL for {regn_no}: {full_url[:60]}...")
                        return full_url
                    
                    # 3. Signed path from thumbnails
                    if attachment.get('signedPath'):
                        return f"{nocodb_base_url}/{attachment['signedPath']}"
                        
                elif isinstance(student_image, str) and student_image:
                    # Direct URL string
                    return student_image
                    
        return None
    except Exception as e:
        print(f"Error fetching student photo from NocoDB for {regn_no}: {e}")
        return None
