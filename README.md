# Atria University Academic Management System

A unified Streamlit application for managing academic operations at Atria University.

## Features

This application combines three essential modules:

### 1. Grade Card Generator
- Generate PDF grade cards from PostgreSQL database
- Batch process multiple students
- Include student photos and course details
- Filter by year flag and admission year

### 2. Student Details Sync
- Sync student details to NocoDB from CSV files
- Automatic create/update operations
- Support for consolidated grade cards
- Real-time progress tracking

### 3. Transcript Generator
- Generate official transcripts by USN
- Professional PDF output
- Include student photos and complete course history
- Downloadable transcripts

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure you have the following files in the root directory:
   - `Grade Card Template.pdf`
   - `Grade Point Table.pdf`
   - `assets/` folder with student photos and university logo

## Usage

Run the application:
```bash
streamlit run app.py
```

Navigate using the sidebar to access different modules.

## Directory Structure

```
/home/ash/Documents/grade/
├── app.py                              # Main unified application
├── GradeCardGenerator.py               # Grade card generation logic
├── generate_transcript.py              # Transcript generation logic
├── requirements.txt                    # Python dependencies
├── Grade Card Template.pdf             # Template for grade cards
├── Grade Point Table.pdf               # Grade point reference table
├── enhanced_transcript_template.html   # HTML template for transcripts
├── enhanced_transcript_styles.css      # CSS styles for transcripts
├── assets/                             # Assets folder
│   ├── AU logo.png                     # University logo
│   └── *.png                           # Student photos (named by USN)
├── gradecards/                         # Output folder for grade cards
└── transcripts/                        # Output folder for transcripts
```

## Configuration

### Database Configuration
- Default host: 33.0.0.103
- Default database: root_db
- Default user: postgres
- Default port: 5432

You can modify these settings in the sidebar of each module.

### NocoDB Configuration
- API Base: http://33.0.0.103:8080/api/v1/db/data/v1/Atria_University
- Composite unique keys: REGN_NO, YEAR_FLAG

## Requirements

- Python 3.8+
- PostgreSQL database access
- NocoDB instance (for Student Details Sync)
- Student photos in PNG format (named by registration number)

## Notes

- Student photos should be named according to their registration number (e.g., `AU21UG-006.png`)
- The assets folder must contain the university logo (`AU logo.png`)
- Generated PDFs are saved in respective output directories (`gradecards/`, `transcripts/`)

## Support

For issues or questions, contact the IT department at Atria University.
