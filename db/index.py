"""
Centralized Database Configuration Module

This module provides centralized database configuration and connection utilities
for both PostgreSQL and NocoDB API access across the application.
Configuration is loaded from environment variables using python-dotenv.
"""

import os
import psycopg2
from psycopg2 import Error
from dotenv import load_dotenv

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
        "student_courses_details_table": STUDENT_COURSES_DETAILS_TABLE
    }
