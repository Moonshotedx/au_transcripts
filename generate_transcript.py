import os
from datetime import datetime
import psycopg2
from psycopg2 import Error
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
from db.index import (
    DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT,
    NOCODB_SCHEMA, STUDENT_DETAILS_TABLE, STUDENT_COURSES_DETAILS_TABLE,
    get_db_connection
)

 

# --- File Paths and Directories ---
HTML_TEMPLATE_FILE = 'enhanced_transcript_template.html'
CSS_FILE = 'enhanced_transcript_styles.css'
OUTPUT_DIR = 'transcripts'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# University logo is static
UNIVERSITY_LOGO_PATH = 'file:///' + os.path.abspath(os.path.join(BASE_DIR, "assets", "AU logo.png")).replace('\\', '/')

# --- Static University-wide Parameters (Can be moved to DB if dynamic) ---
UNIVERSITY_PARAMS = {
    "university_name": "ATRIA UNIVERSITY",
    "university_address": "ASKB Campus, 1st Main Road, Anandnagar, Hebbal, Bengaluru-560024",
    "established_text": "(Established Under Karnataka Act No. 22 of 2021)",
    "university_logo_path": UNIVERSITY_LOGO_PATH,
}

def fetch_all_students_details(conn, specific_regn_no=None):
    """
    Fetches core student details from the student_details table.
    If specific_regn_no is provided, fetches only that student.
    """
    students = []
    try:
        with conn.cursor() as cur:
            query = f"""
                SELECT 
                    "REGN_NO" AS regn_no,
                    "CNAME" AS name,
                    CASE WHEN "ACADEMIC_COURSE_ID" = 'FOU' THEN 'Undergraduate Degree'
                         WHEN "ACADEMIC_COURSE_ID" = 'BDes' THEN 'BDesign'
                         WHEN "ACADEMIC_COURSE_ID" = 'LS' THEN 'Life Sciences'
                         WHEN "ACADEMIC_COURSE_ID" = 'ES' THEN 'Energy Sciences'
                         WHEN "ACADEMIC_COURSE_ID" = 'eMobility' THEN 'e-Mobility'
                         WHEN "ACADEMIC_COURSE_ID" = 'IT' THEN 'Interactive Technologies'
                         WHEN "ACADEMIC_COURSE_ID" = 'DT' THEN 'BTech Digital Transformation'
                         ELSE "ACADEMIC_COURSE_ID" 
                    END AS program_of_study,
                    "ADMISSION_YEAR" AS year_of_admission,
                    "YEAR_OF_COMPLETION" AS year_of_completion,
                    concat('AU/',substring("REGN_NO" FROM 3 FOR 2),'/UG/',RIGHT("REGN_NO",3)) AS transcript_number,
                    4 AS duration_of_program,
                    'English' AS medium_of_instruction,
                    "CGPA" as cgpa,
                    "TOT_CREDIT" as total_credits
                FROM "{NOCODB_SCHEMA}"."{STUDENT_DETAILS_TABLE}"
                where "consolidated_grade_card_flag" = 1
            """
            
            if specific_regn_no:
                query += f" AND \"REGN_NO\" = '{specific_regn_no}'"
            
            # query += " AND \"REGN_NO\" = 'AU21UG-006'" # Previous hardcoded test
            
            cur.execute(query)
            student_records = cur.fetchall()
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                for record in student_records:
                    students.append(dict(zip(columns, record)))
        print(f"Fetched {len(students)} student records.")
    except Error as e:
        print(f"Error fetching student details: {e}")
    return students

def fetch_student_courses_and_marks(conn,regn_no):
    """
    Fetches specific student's course details and marks by joining student_details and student_courses_details tables.
    """
    courses = []
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT distinct 
                    sm."SUBJECT_CODE" AS course_code,
                    sm."SUBJECT_NAME" AS course_title,
                    sm."CREDIT" AS credits,
                    sm."Grade" AS grade,
                    sm."Month_Year_Completion" AS month_year_completion,
                    sm."Academic_Year" as acad_year,
                    sm."Academic_Month" as acad_month
                FROM
                    "{NOCODB_SCHEMA}"."{STUDENT_COURSES_DETAILS_TABLE}" AS sm
                JOIN
                    "{NOCODB_SCHEMA}"."{STUDENT_DETAILS_TABLE}" AS s ON sm."REGN_NO" = s."REGN_NO"
                WHERE
                    s."REGN_NO" = %s
                   --s."REGN_NO" = "AU21UG-003"
                     order by acad_year,acad_month;
            """, (regn_no,))
            course_records = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            for record in course_records:
                courses.append(dict(zip(columns, record)))
        print(f"Fetched {len(courses)} courses for student {regn_no}.")
    except Error as e:
        print(f"Error fetching course marks for {regn_no}: {e}")
    return courses

def calculate_gpa_stats(courses):
    """Calculate GPA statistics"""
    grade_points = {
        'O': 10, 'A+': 9, 'A': 8, 'B+': 7, 'B': 6,
        'C+': 5, 'C': 4, 'D': 3, 'F': 0, 'S': 10, 'AP': 8
    }

    total_credits = 0
    total_points = 0

    for course in courses:
        try:
            credits = float(course.get('Credits', 0))
            grade = course.get('Grades', course.get('Grade', '')).strip()

            if grade in grade_points:
                total_credits += credits
                total_points += credits * grade_points[grade]
        except (ValueError, TypeError):
            continue

    cgpa = round(total_points / total_credits, 2) if total_credits > 0 else 0
    return cgpa, total_credits

def prepare_double_column_courses(courses):
    """Split courses into two equal columns for double-column layout"""
    for i, course in enumerate(courses):
        course['sl_no'] = i + 1

    total_courses = len(courses)
    split_index = (total_courses + 1) // 2

    left_column = courses[:split_index]
    right_column = courses[split_index:]

    return left_column, right_column

def generate_transcript(student_params, course_data, output_filename, html_template, css_file, output_dir):
    """Generate PDF transcript with double column layout"""

   # calculated_cgpa, calculated_credits = calculate_gpa_stats(course_data)

   # student_params['cgpa'] = str(calculated_cgpa)
   # student_params['total_credits'] = str(int(calculated_credits)) 

    left_courses, right_courses = prepare_double_column_courses(course_data)
    student_params['left_courses'] = left_courses
    student_params['right_courses'] = right_courses

    env = Environment(loader=FileSystemLoader(BASE_DIR))
    try:
        template = env.get_template(html_template)
        rendered_html = template.render(student=student_params)
    except Exception as e:
        print(f"Error rendering template: {e}")
        return False

    output_path = os.path.join(output_dir, output_filename)
    try:
        HTML(string=rendered_html, base_url=os.path.abspath('.')).write_pdf(
            output_path,
            stylesheets=[CSS(filename=css_file)]
        )
        print(f" Generated enhanced transcript: {output_path}")
        return True
    except Exception as e:
        print(f"Failed to generate PDF: {e}")
        return False

def create_enhanced_template():
    """Create the enhanced HTML template with double column and integrated photo"""
    template_content = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Official Transcript - {{ student.name }}</title>
    <link rel="stylesheet" href="enhanced_transcript_styles.css">
</head>
<body>
    <div class="transcript-container">
        <div class="header-section">
            <div class="university-info">
                <img src="{{ student.university_logo_path }}" alt="University Logo" class="logo">
                <p class="established-text">{{ student.established_text }}</p>
                <p class="university-address">{{ student.university_address }}</p>
            </div>
        </div>

        <div class="divider-line"></div>

        <div class="transcript-title">
            <h2>CONSOLIDATED GRADE CARD</h2>
        </div>

        <div class="student-info-section">
            <table class="info-table">
                <tr>
                    <td class="info-label">Name</td>
                    <td class="info-value">{{ student.name | upper }}</td>
                    <td class="info-label">Duration of the Program</td>
                    <td class="info-value">{{ student.duration_of_program }}</td>
                    <td class="photo-cell" rowspan="5">
                        <div class="photo-container">
                            <img src="{{ student.photo_path }}" alt="Student Photo" class="student-photo">
                        </div>
                    </td>
                </tr>
                <tr>
                    <td class="info-label">Reg No.</td>
                    <td class="info-value">{{ student.srn }}</td>
                    <td class="info-label">Medium of Instruction</td>
                    <td class="info-value">{{ student.medium_of_instruction }}</td>
                </tr>
                <tr>
                    <td class="info-label">Transcript No.</td>
                    <td class="info-value">{{ student.transcript_number }}</td>
                    <td class="info-label">Date of Issue</td>
                    <td class="info-value">{{ student.date_of_issue }}</td>
                </tr>
                <tr>
                    <td class="info-label">Year of Admission</td>
                    <td class="info-value">{{ student.year_of_admission }}</td>
                    <td class="info-label">Year of Completion</td>
                    <td class="info-value">{{ student.year_of_completion }}</td>
                </tr>
                <tr>
                    <td class="info-label">Program of Study</td>
                    <td class="info-value" colspan="3">{{ student.program_of_study }}</td>
                </tr>
            </table>
        </div>

        <div class="courses-section">
            <table class="courses-table-double">
                <thead>
                    <tr>
                        <th class="sl-col">Sl No.</th>
                        <th class="code-col">Course Code</th>
                        <th class="title-col">Course Title</th>
                        <th class="credits-col">Credits</th>
                        <th class="grade-col">Grade</th>
                        <th class="completion-col">Month & Year of Completion</th>

                        <th class="spacer-col"></th> <th class="sl-col">Sl No.</th>
                        <th class="code-col">Course Code</th>
                        <th class="title-col">Course Title</th>
                        <th class="credits-col">Credits</th>
                        <th class="grade-col">Grade</th>
                        <th class="completion-col">Month & Year of Completion</th>
                    </tr>
                </thead>
                <tbody>
                    {% set max_rows = [student.left_courses|length, student.right_courses|length]|max %}
                    {% for i in range(max_rows) %}
                    <tr>
                        {% if i < student.left_courses|length %}
                            {% set course = student.left_courses[i] %}
                            <td class="text-center">{{ course.sl_no }}</td>
                            <td class="text-center">{{ course['course_code'] }}</td>
                            <td class="text-left">{{ course['course_title'] }}</td>
                            <td class="text-center">{{ course['credits'] }}</td>
                            <td class="text-center">{{ course.get('grade', course.get('grade', '')) }}</td>
                            <td class="text-center">{{ course['month_year_completion'] }}</td>
                            <td class="spacer-col"></td> {% else %}
                            <td></td><td></td><td></td><td></td><td></td><td></td>
                        {% endif %}
                        
                        {% if i < student.right_courses|length %}
                            {% set course = student.right_courses[i] %}
                            <td class="text-center">{{ course.sl_no }}</td>
                            <td class="text-center">{{ course['course_code'] }}</td>
                            <td class="text-left">{{ course['course_title'] }}</td>
                            <td class="text-center">{{ course['credits'] }}</td>
                            <td class="text-center">{{ course.get('grade', course.get('grade', '')) }}</td>
                            <td class="text-center">{{ course['month_year_completion'] }}</td>
                        {% else %}
                            <td></td><td></td><td></td><td></td><td></td><td></td>
                        {% endif %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="summary-section">
            <table class="summary-table">
                <tr>
                    <td class="summary-label">Credits</td>
                    <td class="summary-value">{{ student.total_credits}}</td>
                    <td class="summary-label">CGPA</td>
                    <td class="summary-value">{{ student.cgpa }}</td>
                </tr>
            </table>
        </div>

        <div class="bottom-section">
            <div class="grading-section">
                <p><strong>GRADE:</strong> O - 10(Outstanding), A+ - 9 (Excellent), A - 8 (Very Good), B+ - 7(Good), B - 6 (Above average), C+ - 5 (Average), C - 4 (Pass), F - 0 (Fail), Ab - 0 (Absent)</p>
            </div>

            <div class="footer-section">
                <div class="signature-left">
                    <div class="signature-line"></div>
                    <p>VERIFIED BY</p>
                </div>
                <div class="signature-right">
                    <div class="signature-line"></div>
                    <p>REGISTRAR</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>'''

    with open('enhanced_transcript_template.html', 'w', encoding='utf-8') as f:
        f.write(template_content)
    print("Enhanced HTML template created")

def create_enhanced_styles():
    """Create enhanced CSS styles with double column layout and integrated photo"""
    css_content = '''/* Enhanced Transcript Styles - Professional Double Column Layout */
@page {
    size: A4;
    margin: 0.5in;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Arial', sans-serif;
    font-size: 8pt;
    line-height: 1.2;
    color: #000;
    background: #fff;
}

.transcript-container {
    width: 100%;
    max-width: 210mm;
    margin: 0 auto;
    background: #fff;
    padding: 8px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

/* Header Section */
.header-section {
    margin-bottom: 8px;
}

.university-info {
    text-align: center;
    padding: 6px 0;
}

.logo {
    height: 55px;
    width: auto;
    margin-bottom: 3px;
    display: block;
    margin-left: auto;
    margin-right: auto;
}

.university-name {
    font-size: 16pt;
    font-weight: bold;
    margin-bottom: 2px;
    color: #000;
}

.established-text {
    font-size: 8pt;
    margin-bottom: 2px;
    font-style: italic;
}

.university-address {
    font-size: 8pt;
    line-height: 1.2;
}

/* Divider Line */
.divider-line {
    border-bottom: 1.5px solid #000;
    margin: 8px 0;
}

/* Title */
.transcript-title {
    text-align: center;
    margin-bottom: 10px;
}

.transcript-title h2 {
    font-size: 14pt;
    font-weight: bold;
    color: #000;
    letter-spacing: 1px;
}

/* Student Information with Integrated Photo */
.student-info-section {
    margin-bottom: 12px;
}

.info-table {
    width: 100%;
    border-collapse: collapse;
    border: 1px solid #000;
}

.info-table td {
    border: 1px solid #000;
    padding: 4px 6px;
    font-size: 9pt;
    vertical-align: middle;
}

.info-label {
    font-weight: bold;
    width: 16%;
    border-right: 1px solid #000;
}

.info-value {
    width: 24%;
    font-weight: normal;
}

/* Photo Cell - Integrated in table with border */
.photo-cell {
    width: 12%;
    text-align: center;
    vertical-align: middle;
    border-left: 1px solid #000;
    padding: 4px;
    background-color: #fff;
}

.photo-container {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 3px;
    background-color: #fff;
}

.student-photo {
    width: 75px;
    height: 90px;
    object-fit: cover;
    object-position: center;
    display: block;
}

/* Double Column Courses Section */
.courses-section {
    margin-bottom: 10px;
    flex-grow: 1;
}

.courses-table-double {
    width: 100%;
    border-collapse: collapse;
    border: 1px solid #000;
    font-size: 7pt;
    table-layout: fixed;
}

.spacer-col {
    width: 10px; /* Adjust width to control spacing */
    background: #fff;
    border: none;
}


/* Only horizontal lines in the table header */
.courses-table-double th {
    border-top: 1px solid #000;
    border-bottom: 1px solid #000;
    border-left: none;
    border-right: none;
    padding: 3px 2px;
    font-weight: bold;
    text-align: center;
    font-size: 7pt;
}

/* No borders in table body cells */
.courses-table-double td {
    border: none;
    padding: 2px 3px;
    vertical-align: top;
}



.courses-table-double th {
    font-weight: bold;
    text-align: center;
    font-size: 7pt;
    padding: 3px 2px;
}

/* Column Widths for Double Column Layout */
.sl-col { width: 4%; }
.code-col { width: 8%; }
.title-col { width: 18%; }
.credits-col { width: 4%; }
.grade-col { width: 4%; }
.completion-col { width: 12%; }

/* Vertical separator between left and right columns */
.courses-table-double th:nth-child(6),
.courses-table-double td:nth-child(6) {
    border-right: 1px solid #000;
}

.courses-table-double th:nth-child(7),
.courses-table-double td:nth-child(7) {
    border-left: 1px solid #000;
}

.text-center {
    text-align: center;
}

.text-left {
    text-align: left;
    padding-left: 3px;
}

/* Summary Section */
.summary-section {
    margin-bottom: 15px;
}

.summary-table {
    width: 35%;
    margin-left: auto;
    border-collapse: collapse;
    border: 1px solid #000;
}

.summary-table td {
    border: 1px solid #000;
    padding: 5px 10px;
    font-size: 10pt;
    text-align: center;
}

.summary-label {
    font-weight: bold;
    border-right: 1px solid #000;
}

.summary-value {
    font-weight: bold;
    font-size: 11pt;
}

/* Bottom Section */
.bottom-section {
    margin-top: auto;
    padding-top: 15px;
}

/* Grading Section */
.grading-section {
    margin-bottom: 20px;
    font-size: 8pt;
    text-align: center;
    padding: 0 15px;
    line-height: 1.3;
}

/* Footer Section */
.footer-section {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-top: 25px;
    padding-top: 15px;
}

.signature-left,
.signature-right {
    text-align: center;
    width: 130px;
}

.signature-line {
    width: 110px;
    height: 1px;
    border-bottom: 1px solid #000;
    margin: 0 auto 15px;
}

.footer-section p {
    font-size: 9pt;
    font-weight: bold;
}

/* Print Optimization */
@media print {
    .transcript-container {
        padding: 6px;
        min-height: auto;
    }
    
    .courses-table-double {
        font-size: 6pt;
    }
    
    .courses-table-double th,
    .courses-table-double td {
        padding: 1px 2px;
    }
    
    .bottom-section {
        page-break-inside: avoid;
        margin-top: auto;
    }
}

/* Ensure no page breaks */
.transcript-container {
    page-break-inside: avoid;
}

.courses-table-double {
    page-break-inside: auto;
}

.courses-table-double tr {
    page-break-inside: avoid;
    page-break-after: auto;
}

.bottom-section {
    page-break-inside: avoid;
}

/* Responsive font adjustments for fitting content */
@media print {
    .courses-table-double tbody tr {
        font-size: 6pt;
    }
    
    .courses-table-double th {
        font-size: 6pt;
        padding: 2px 1px;
    }
    
    .courses-table-double td {
        padding: 1px 2px;
        line-height: 1.1;
    }
}'''
    
    with open('enhanced_transcript_styles.css', 'w', encoding='utf-8') as f:
        f.write(css_content)
    print("Enhanced CSS styles created")


def process_single_student_transcript(conn, student_record, base_dir=BASE_DIR):
    """
    Processes a single student record to generate their transcript.
    Returns the path to the generated PDF if successful, else None.
    """
    regn_no = student_record.get('regn_no')
    if not regn_no:
        print(f"Skipping student due to missing REGN_NO in record: {student_record}")
        return None

    print(f"\n--- Generating transcript for {student_record.get('name', 'UNKNOWN')} ({regn_no}) ---")

    # Dynamically set student-specific parameters for the template
    student_params = {
        "name": student_record.get('name', 'N/A'),
        "srn": regn_no,
        "transcript_number": student_record.get('transcript_number', 'N/A'),
        "year_of_admission": student_record.get('year_of_admission', 'N/A'),
        "program_of_study": student_record.get('program_of_study', 'N/A'),
        "duration_of_program": student_record.get('duration_of_program', 'N/A'),
        "medium_of_instruction": student_record.get('medium_of_instruction', 'N/A'),
        "date_of_issue": datetime.now().strftime("%B %d, %Y"), # Current date of issue
        "year_of_completion": student_record.get('year_of_completion', 'N/A'),
        "cgpa": student_record.get('cgpa', 'N/A'),
        "total_credits":student_record.get('total_credits', 'N/A'),
        "month_year_completion" : student_record.get('month_year_completion', 'N/A'),
    }

    # Handle student photo path dynamically
    student_photo_base_name = student_record.get('regn_no')
    if student_photo_base_name:
        student_photo_filename_with_ext = f"{student_photo_base_name}.png"
        full_photo_path = os.path.abspath(os.path.join(base_dir, "assets", student_photo_filename_with_ext))

        # Check if the photo file actually exists
        if os.path.exists(full_photo_path):
            student_params['photo_path'] = 'file:///' + full_photo_path.replace('\\', '/')
            print(f"  Photo path for {regn_no}: {student_params['photo_path']}")
        else:
            print(f"  Warning: Student photo file not found at {full_photo_path} for {regn_no}. Using placeholder.")
            student_params['photo_path'] = 'https://placehold.co/75x90/aabbcc/000000?text=No+Photo' 
    else:
        print(f"  Warning: No registration number to form photo filename for student record: {student_record}. Using placeholder.")
        student_params['photo_path'] = 'https://placehold.co/75x90/aabbcc/000000?text=No+Photo' 

    # Merge university-wide parameters
    student_params.update(UNIVERSITY_PARAMS)

    # Fetch courses for the current student
    student_course_data = fetch_student_courses_and_marks(conn, regn_no)

    if student_course_data:
        output_name = f"{regn_no}_{student_params['name'].replace(' ', '_')}_Transcript.pdf"
        success = generate_transcript(
            student_params,
            student_course_data,
            output_name,
            HTML_TEMPLATE_FILE,
            CSS_FILE,
            OUTPUT_DIR
        )

        if success:
            print(f"  Transcript for {regn_no} generated successfully!")
            return os.path.join(OUTPUT_DIR, output_name)
        else:
            print(f"  Failed to generate transcript for {regn_no}.")
            return None
    else:
        print(f"  No course data found for {regn_no}. Skipping transcript generation.")
        return None


if __name__ == "__main__":
    print("Starting Enhanced Transcript Generation from PostgreSQL...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Ensure template and styles files exist
    create_enhanced_template()
    create_enhanced_styles()

    conn = get_db_connection()
    if conn:
        try:
            all_students_details = fetch_all_students_details(conn)

            if not all_students_details:
                print("No student records found in the database. Exiting.")
            else:
                for student_record in all_students_details:
                    process_single_student_transcript(conn, student_record)

        finally:
            if conn:
                conn.close()
                print("Database connection closed.")
    else:
        print("Could not establish database connection. Aborting transcript generation.")

    print("\n All Transcripts Generation Complete!")
