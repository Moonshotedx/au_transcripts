# grade_card_generator.py

import os
import csv
from pathlib import Path
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageEnhance
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter
import psycopg2
from psycopg2 import Error
from db.index import (
    DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT,
    NOCODB_SCHEMA, STUDENT_DETAILS_TABLE, STUDENT_COURSES_DETAILS_TABLE,
    get_db_connection, fetch_student_photo_url
)


class GradeCardGenerator:
    def __init__(self, template_path="Grade Card Template.pdf", output_dir="gradecards", assets_dir="assets", photo_dir="assets/student_photos"):
        self.template_path = Path(template_path)
        self.output_dir = Path(output_dir)
        self.assets_dir = Path(assets_dir)
        self.photo_dir = Path(photo_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.photo_dir.mkdir(exist_ok=True, parents=True) # Ensure photo directory exists
        self.setup_fonts()

        # Coordinates ruler to adjust positions
        self.coordinates = {
            "name": (167.5, 702.5),
            "reg_no": (96, 683.5),
            "program": (152, 665),
            "date_of_issue": (460, 665),
            "gc_no": (460, 702.5),
            "year": (460, 683.5), # This will be Year of Completion
            "credits": (475, 246), # Semester Credits
            "total_credits": (475, 212), # Total Program Credits (from student_details)
            "cgpa": (475, 178), # Cumulative CGPA (from student_details)
            "photo": {"x": 485, "y": 732, "width": 63, "height": 78},
            "table_start": (80, 590),
        }

    def setup_fonts(self):
        medium = self.assets_dir / "Montserrat-Medium.ttf"
        semibold = self.assets_dir / "Montserrat-SemiBold.ttf"
        regular = self.assets_dir / "Montserrat-Regular.ttf"

        if medium.exists():
            pdfmetrics.registerFont(TTFont("MontserratMedium", str(medium)))
        else:
            print(f"Font file not found: {medium}. Using default Helvetica.")

        if semibold.exists():
            pdfmetrics.registerFont(TTFont("MontserratSemiBold", str(semibold)))
        else:
            print(f"Font file not found: {semibold}. Using default Helvetica-Bold.")

        if regular.exists():
            pdfmetrics.registerFont(TTFont("MontserratRegular", str(regular)))
        else:
            print(f"Font file not found: {regular}. Using default Helvetica.")

    def process_photo(self, filename, width, height, photo_url=None):
        """
        Process a student photo for the grade card.
        Priority: 1. photo_url (from NocoDB), 2. Local file, 3. Returns None (placeholder will be used)
        """
        import requests
        from io import BytesIO
        
        img = None
        
        # First, try to fetch from URL (NocoDB)
        if photo_url:
            try:
                response = requests.get(photo_url, timeout=10)
                if response.status_code == 200:
                    img = Image.open(BytesIO(response.content))
                    print(f"  Photo loaded from NocoDB URL for {filename}")
            except Exception as e:
                print(f"Warning: Could not fetch photo from URL for {filename}: {e}")
        
        # Fall back to local file if URL fetch failed or not provided
        if img is None:
            photo_path = self.photo_dir / filename
            if photo_path.exists():
                try:
                    img = Image.open(photo_path)
                    print(f"  Photo loaded from local file: {photo_path}")
                except Exception as e:
                    print(f"Error opening local photo {photo_path}: {e}")
            else:
                print(f"Warning: Student photo not found at {photo_path}. Using placeholder.")
        
        if img is None:
            return None  # Indicate no photo found, create_overlay will handle placeholder
        
        try:
            # Ensure image is in RGB mode for JPEG saving
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize and create background
            img_copy = img.copy()
            img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (width, height), "white")
            offset = ((width - img_copy.width) // 2, (height - img_copy.height) // 2)
            bg.paste(img_copy, offset)
            
            enhancer = ImageEnhance.Sharpness(bg)
            bg = enhancer.enhance(1.2)

            # Save the processed image to a BytesIO object (in-memory)
            img_byte_arr = BytesIO()
            bg.save(img_byte_arr, format='JPEG')
            img_byte_arr.seek(0)
            
            return img_byte_arr
            
        except Exception as e:
            print(f"Error processing photo {filename}: {e}. Using placeholder.")
            return None

    def create_placeholder_photo(self, width=68, height=85):
        # Create a BytesIO object for the placeholder as well for consistency
        img_byte_arr = BytesIO()
        img = Image.new('RGB', (width, height), '#cccccc') # Grey placeholder
        img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        return img_byte_arr # Return the BytesIO object

    def create_overlay(self, student_info, student_marks):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)

        # Fonts
        name_font = "MontserratSemiBold" if "MontserratSemiBold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
        regular_font = "MontserratMedium" if "MontserratMedium" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
        base_font = "MontserratRegular" if "MontserratRegular" in pdfmetrics.getRegisteredFontNames() else "Helvetica"

        # Student Info - using .get() for safety and providing defaults
        c.setFont(name_font, 10)
        c.drawString(*self.coordinates["name"], student_info.get("name", "N/A").upper())

        c.setFont(regular_font, 10)
        c.drawString(*self.coordinates["reg_no"], student_info.get("reg_no", "N/A"))
        c.drawString(*self.coordinates["program"], student_info.get("program", "N/A"))
        c.drawString(*self.coordinates["date_of_issue"], student_info.get("date_of_issue", "N/A"))
        c.drawString(*self.coordinates["gc_no"], student_info.get("gc_no", "N/A"))
        c.drawString(*self.coordinates["year"], student_info.get("year", "N/A"))
        
        # Ensure credits/cgpa are displayed as strings, with defaults
        c.drawString(*self.coordinates["credits"], str(student_info.get("credits", "0")))
        c.drawString(*self.coordinates["total_credits"], str(student_info.get("total_credits", "0")))
        c.drawString(*self.coordinates["cgpa"], str(student_info.get("cgpa", "0.00")))

        # Photo - fetch from NocoDB first, then fall back to local file
        photo_filename = student_info.get("photo_filename")
        reg_no = student_info.get("reg_no")
        
        # Fetch photo URL from NocoDB
        photo_url = fetch_student_photo_url(reg_no) if reg_no else None
        
        # process_photo now returns a BytesIO object or None
        processed_photo_data = self.process_photo(photo_filename, 68, 85, photo_url=photo_url) 
        
        cfg = self.coordinates["photo"] # Define cfg once

        if processed_photo_data: # If process_photo returned a BytesIO object
            # print(f"processed photo data is running for {photo_filename}") # Debug print
            c.drawImage(
                ImageReader(processed_photo_data), # Use the BytesIO object directly
                cfg["x"],
                cfg["y"],
                cfg["width"],
                cfg["height"],
                mask="auto",
            )
        else:
            # If photo processing failed or photo_filename was None/not found, use placeholder
            # print(f"placeholder is running for {photo_filename}") # Debug print
            placeholder_data = self.create_placeholder_photo(cfg["width"], cfg["height"])
            c.drawImage(
                ImageReader(placeholder_data), # Use the BytesIO object directly
                cfg["x"],
                cfg["y"],
                cfg["width"],
                cfg["height"],
                mask="auto",
            )

        # Table Rows only (no headers)
        x, y = self.coordinates["table_start"]

        # Define fixed positions for each column (relative to x)
        column_offsets = [-18, 25, 90, 385, 440]

        c.setFont(base_font, 8.6) # Using regular font for table content # default 8.6
        y -= 20 # Initial space before first row 20 is original value

        for row in student_marks:
            values = [
                str(row.get("Sl.no", "N/A")),
                str(row.get("Course_Code", "N/A")),
                str(row.get("Course_Title", "N/A")),
                str(row.get("Credits", "N/A")),
                str(row.get("Grade", "N/A")),
            ]
            for i, text in enumerate(values):
                c.drawString(x + column_offsets[i], y, text)
            y -= 16.5  # vertical spacing between rows 18.5 is original

        c.save()
        buffer.seek(0)
        return buffer

    def merge_pdf(self, overlay, output_path):
        try:
            template = PdfReader(str(self.template_path))
            overlay_pdf = PdfReader(overlay)
            # Use relative path for Grade Point Table PDF
            grade_point_table_path = Path(os.getcwd()) / "Grade Point Table.pdf"
            grade_point_table_pdf = PdfReader(str(grade_point_table_path))
            writer = PdfWriter()

            if not template.pages:
                raise ValueError(f"PDF template '{self.template_path}' has no pages.")
        
            base = template.pages[0]
            base.merge_page(overlay_pdf.pages[0])
            writer.add_page(base)

            if grade_point_table_pdf.pages:
                writer.add_page(grade_point_table_pdf.pages[0])
            else:
                print("Warning: Grade Point Table PDF has no pages!")

            with open(output_path, "wb") as f:
             writer.write(f)

        except Exception as e:
            print(f"Error merging PDFs to {output_path}: {e}")
            raise


    def generate_certificate(self, student_info, student_marks, output_filename=None):
        """
        Generate a grade card PDF for a student.
        
        Args:
            student_info: Dictionary with student information
            student_marks: List of course marks
            output_filename: Optional custom filename
        
        Returns:
            str: Path to the generated PDF file, or None if generation failed
        """
        try:
            overlay = self.create_overlay(student_info, student_marks)
            if not output_filename:
                safe_name = student_info.get("name", "Unknown").replace(' ', '_').replace('.', '')
                reg_no = student_info.get("reg_no", "N_A")
                output_filename = f"{reg_no}_{safe_name}_GradeCard.pdf"
            output_path = self.output_dir / output_filename
            self.merge_pdf(overlay, output_path)
            print(f"Generated grade card for {student_info.get('name', 'Unknown')} ({student_info.get('reg_no', 'N/A')}) → {output_path}")
            return str(output_path)
        except Exception as e:
            print(f"Failed to generate grade card for {student_info.get('name', 'Unknown')} ({student_info.get('reg_no', 'N/A')}): {e}")
            return None

    # --- Method to establish DB connection ---
    def get_db_connection(self):
        """Establishes and returns a PostgreSQL database connection."""
        return get_db_connection()

    # --- Method to fetch all data from DB ---
    def fetch_all_gradecard_data(self, year_flag=2, admission_year=2021, regn_no=None, academic_course_id=None):
        """
        Fetches all student details and their corresponding course marks from PostgreSQL
        and prepares them for grade card generation.
        
        Args:
            year_flag: Required - Year flag filter
            admission_year: Required - Admission year filter
            regn_no: Optional - Filter by specific student registration number
            academic_course_id: Optional - Filter by academic course ID (e.g., 'FOU', 'BDes')
        """
        all_students_grade_data = []
        conn = None
        try:
            conn = self.get_db_connection()
            if not conn:
                print("Could not establish database connection for fetching data.")
                return []

            with conn.cursor() as cur:
                # Build dynamic WHERE clause
                where_conditions = ['"YEAR_FLAG"=%s', '"ADMISSION_YEAR"=%s']
                params = [year_flag, admission_year]
                
                # Add optional filters
                if regn_no and regn_no.strip():
                    where_conditions.append('"REGN_NO"=%s')
                    params.append(regn_no.strip())
                
                if academic_course_id and academic_course_id.strip():
                    where_conditions.append('"ACADEMIC_COURSE_ID"=%s')
                    params.append(academic_course_id.strip())
                
                where_clause = ' AND '.join(where_conditions)
                
                # 1. Fetch all main student details
                query = f"""
                    SELECT
                        "REGN_NO",
                        "CNAME",
                        "ACADEMIC_COURSE_ID", -- To derive program name
                        "ADMISSION_YEAR",
                        "YEAR_OF_COMPLETION",
                        "TOT_CREDIT", -- Total program credits from student_details
                        "CGPA" ,-- Overall CGPA from student_details
                        concat('AU/',substring("REGN_NO" FROM 3 FOR 2),'/UG/',RIGHT("REGN_NO",3)) AS transcript_number,
                       -- CONCAT('AU/21/UG/',RIGHT("REGN_NO",3)) AS transcript_number,
                        "CUMULATIVE_CREDITS"
                    FROM "{NOCODB_SCHEMA}"."{STUDENT_DETAILS_TABLE}"
                    WHERE {where_clause};
                """
                cur.execute(query, tuple(params))
                student_records = cur.fetchall()
                student_cols = [desc[0] for desc in cur.description]
                
                gc_counter = 1001 # For Grade Card Number

                for s_record in student_records:
                    student_db_info = dict(zip(student_cols, s_record))
                    regn_no = student_db_info.get("REGN_NO")
                    
                    if not regn_no:
                        print(f"Skipping student record due to missing REGN_NO: {student_db_info}")
                        continue

                    # DEBUG print for RegNo from DB - keep this for future debugging if needed
                    # print(f"DEBUG: RegNo from DB: '{regn_no}'")

                    # 2. Fetch specific student's course marks
                    # Ensure all columns needed for the table rows are selected
                    cur.execute(f"""
                        SELECT
                            "SUBJECT_CODE",
                            "SUBJECT_NAME",
                            "CREDIT",
                            "Grade"
                            -- Add other columns from student_courses_details if needed for calculation or display
                        FROM "{NOCODB_SCHEMA}"."{STUDENT_COURSES_DETAILS_TABLE}"
                        WHERE "REGN_NO" = %s and "YEAR_FLAG"=%s
                        ORDER BY "SUBJECT_CODE"; -- Order for consistent display
                    """, (regn_no, year_flag))
                    course_records = cur.fetchall()
                    course_cols = [desc[0] for desc in cur.description]
                    
                    student_marks_list = []
                    sl_no_counter = 1
                    current_semester_credits = 0 # Placeholder for a specific semester's credits if needed

                    for c_record in course_records:
                        course_info = dict(zip(course_cols, c_record))
                        student_marks_list.append({
                            "Sl.no": str(sl_no_counter),
                            "Course_Code": course_info.get("SUBJECT_CODE", "N/A"),
                            "Course_Title": course_info.get("SUBJECT_NAME", "N/A"),
                            "Credits": str(course_info.get("CREDIT", "0")),
                            "Grade": course_info.get("Grade", "N/A")
                        })
                        try:
                            current_semester_credits += float(course_info.get("CREDIT", 0))
                        except (ValueError, TypeError):
                            pass
                        sl_no_counter += 1

                    # Derive program name from ACADEMIC_COURSE_ID
                    academic_course_id = student_db_info.get("ACADEMIC_COURSE_ID")
                    program_name = "N/A"
                    if academic_course_id == 'FOU': program_name = 'Foundation Year'
                    elif academic_course_id == 'BDes': program_name = 'B-Design'
                    elif academic_course_id == 'LS': program_name = 'Life Sciences'
                    elif academic_course_id == 'ES': program_name = 'Energy Sciences'
                    elif academic_course_id == 'eMob': program_name = 'e-Mobility'
                    elif academic_course_id == 'IT': program_name = 'Interactive Technologies'
                    elif academic_course_id == 'DT': program_name = 'Digital Transformation'
                    elif academic_course_id == 'BBA': program_name = 'BBA'
                    else: program_name = student_db_info.get("COURSE_NAME", "N/A") # Fallback to COURSE_NAME if available


                    # Prepare student_info dictionary
                    student_info_for_card = {
                        "name": student_db_info.get("CNAME", "N/A"),
                        "reg_no": regn_no,
                        "program": program_name,
                        "date_of_issue": datetime.now().strftime("%d %B %Y"),
                        "gc_no": student_db_info.get("transcript_number", "N/A"), # Generate sequential GC number
                        "year": str(student_db_info.get("YEAR_OF_COMPLETION", "N/A")), # Use year of completion
                        "credits": str(int(current_semester_credits)), # Credits for this specific report (e.g., current semester)
                        "total_credits": str(student_db_info.get("CUMULATIVE_CREDITS", "0")), # Total program credits
                    #    "total_credits": str(student_db_info.get("TOT_CREDIT", "0")), # Total program credits
                        "cgpa": f"{float(student_db_info.get('CGPA', 0)):.2f}", # Overall CGPA
                        # "cgpa": '',
                         #f"{float(student_db_info.get('CGPA', 0)):.2f}", # Overall CGPA
                        "photo_filename": f"{regn_no}.png" # Assumes photo is REGN_NO.jpg
                    }
                    gc_counter += 1

                    all_students_grade_data.append({
                        'student_info': student_info_for_card,
                        'student_marks': student_marks_list
                    })

            print(f"Fetched {len(all_students_grade_data)} student grade card data records from DB.")
        except Error as e:
            print(f"Error fetching grade card data from PostgreSQL: {e}")
        finally:
            if conn:
                conn.close()
                print("Database connection for fetch closed.")
        return all_students_grade_data