import streamlit as st
import os
from pathlib import Path

# Set page configuration
st.set_page_config(
    page_title="Atria University - Academic Management System",
    page_icon=":school:",
    layout="wide"
)

# Sidebar navigation
st.sidebar.image("https://apps.atriauniversity.in/Atria_logo.svg", use_container_width=True)
st.sidebar.markdown("---")

# Navigation menu
page = st.sidebar.radio(
    "Select Module",
    ["Course Details", "Student Details", "Grade Card Generator", "Transcript Generator"]
)



# Course Details Page
if page == "Course Details":
    import pandas as pd
    import requests
    import json
    from urllib.parse import quote
    from db.index import NOCODB_API_BASE, NOCODB_API_TOKEN, NOCODB_HEADERS
    
    st.title(":books: Course Details Manager")
    st.markdown("Upload a student details CSV and specify the Year Flag to sync data to NocoDB.")
    
    # Configuration
    HEADERS = NOCODB_HEADERS
    
    COMPOSITE_UNIQUE_KEYS = ["REGN_NO", "YEAR_FLAG", "SUBJECT_CODE"]
    
    def update_or_create(table_name, record, unique_keys, log_container):
        """
        Creates a new record or updates an existing one in NocoDB based on a composite unique key.
        """
        filter_parts = []
        for key in unique_keys:
            value = record.get(key)
            if value is None:
                log_container.warning(f"Skipping record due to missing unique key '{key}': {record}")
                return False

            if key == "REGN_NO" or key == "SUBJECT_CODE":
                value = str(value)

            filter_parts.append(f'`{key}`,eq,{value}')

        raw_filter_segment = ',AND,'.join(filter_parts)
        encoded_filter_segment = quote(raw_filter_segment)

        get_url = f"{NOCODB_API_BASE}/{table_name}?filter={encoded_filter_segment}"

        try:
            response = requests.get(get_url, headers=HEADERS)
            
            record_id = None
            if response.status_code == 200:
                response_json = response.json()
                if response_json.get('list'):
                    record_list = response_json['list']
                    if record_list:
                        record_id = record_list[0]['Id']
            
            if record_id:
                update_url = f"{NOCODB_API_BASE}/{table_name}/{record_id}"
                res = requests.patch(update_url, headers=HEADERS, data=json.dumps(record))
                action = "UPDATED"
            else:
                create_url = f"{NOCODB_API_BASE}/{table_name}"
                res = requests.post(create_url, headers=HEADERS, data=json.dumps(record))
                action = "CREATED"

            if not res.ok:
                log_container.error(f"Failed to {action} record: {res.text} (Status: {res.status_code})")
                return False
            else:
                return True

        except Exception as e:
            log_container.error(f"Exception during sync: {str(e)}")
            return False

    def process_and_sync(df, year_flag, log_container, progress_bar):
        # Debug: Show original columns
        log_container.info(f"Original CSV columns: {list(df.columns)}")
        
        # Debug: Show sample of original data for SUB columns
        sub_cols = [c for c in df.columns if c.startswith('SUB')]
        if sub_cols:
            log_container.info(f"SUB columns found: {sub_cols}")
            log_container.info("Sample values from first row:")
            for col in sub_cols[:5]:  # Show first 5 SUB columns
                log_container.info(f"  {col}: {df[col].iloc[0] if len(df) > 0 else 'N/A'}")
        
        # --- Step 1: Pre-process column names ---
        new_columns = {}
        for col in df.columns:
            if col.startswith('SUB') and '_' in col:
                parts = col.split('_')
                subject_num_str = parts[0][3:]
                metric_name = '_'.join(parts[1:])
                new_columns[col] = f"{metric_name}_{subject_num_str}"
            elif col.startswith('SUB') and len(col) > 3 and col[3:].isdigit() and col not in new_columns:
                subject_num_str = col[3:]
                new_columns[col] = f"SUBJECT_ACTUAL_CODE_{subject_num_str}"
            elif col.startswith('SUB') and col.endswith('NM') and len(col) > 3 and col[3].isdigit() and col not in new_columns:
                subject_num_str = col[3:-2]
                new_columns[col] = f"SUBJECT_NAME_{subject_num_str}"
            else:
                new_columns[col] = col

        df_renamed = df.rename(columns=new_columns)
        
        # Debug: Show column renaming for SUB columns
        log_container.info("Column renaming (SUB columns only):")
        for orig, new in new_columns.items():
            if orig.startswith('SUB'):
                log_container.info(f"  {orig} → {new}")

        # --- Step 2: Identify id_vars ---
        id_vars = [col for col in df_renamed.columns if not pd.Series(col).str.contains(r'_\d+$').any()]
        if 'REGN_NO' not in id_vars:
            id_vars.insert(0, 'REGN_NO')

        # --- Step 3: Define stubnames ---
        stubnames = [
            'SUBJECT_NAME', 'TH_MRKS', 'CE_MRKS', 'TOT', 'GRADE',
            'GRADE_POINTS', 'CREDIT', 'CREDIT_POINTS', 'TYPE', 'RESULT',
            'SUBJECT_ACTUAL_CODE', 'MONTH_YEAR_COMPLETION','YEAR_COMPLETION','MONTH_COMPLETION_IN_NUMBER'
        ]

        # --- Step 4: Temporarily rename conflicting id_vars ---
        temp_rename_mapping_final = {}
        for col in list(id_vars):
            if col in stubnames:
                temp_rename_mapping_final[col] = f"{col}_GLOBAL"
                id_vars[id_vars.index(col)] = f"{col}_GLOBAL"
        
        df_final = df_renamed.rename(columns=temp_rename_mapping_final)

        try:
            # --- Step 5: wide_to_long ---
            long_df = pd.wide_to_long(
                df_final,
                stubnames=stubnames,
                i=id_vars,
                j='Subject_Number',
                sep='_',
                suffix='\\d+'
            )
        except Exception as e:
            log_container.error(f"Error during data transformation (wide_to_long): {e}")
            return

        # --- Step 6: Post-processing ---
        long_df = long_df.reset_index()
        
        # Debug: Show columns after wide_to_long
        log_container.info(f"Columns after wide_to_long: {list(long_df.columns)}")
        
        # SUBJECT_ACTUAL_CODE contains actual codes like "DES201", this should become SUBJECT_CODE
        # Subject_Number (1, 2, 3...) is just the position reference
        long_df = long_df.drop(columns=['Subject_Number'])

        # Rename columns - SUBJECT_ACTUAL_CODE becomes SUBJECT_CODE (for NocoDB unique key)
        # Keep SUBJECT_NAME as is (NocoDB expects SUBJECT_NAME column)
        long_df = long_df.rename(columns={
            'TOT': 'Marks',
            'GRADE': 'Grade',
            'SUBJECT_ACTUAL_CODE': 'SUBJECT_CODE',
            'MONTH_YEAR_COMPLETION' : 'Month_Year_Completion',
            'YEAR_COMPLETION' : 'Academic_Year',
            'MONTH_COMPLETION_IN_NUMBER' : 'Academic_Month'
        })

        reverse_temp_rename_mapping = {v: k for k, v in temp_rename_mapping_final.items()}
        long_df = long_df.rename(columns=reverse_temp_rename_mapping)

        # Clean up rows where subject data is missing
        long_df_cleaned = long_df.dropna(subset=['SUBJECT_NAME', 'SUBJECT_CODE'], how='all')
        
        # Debug: Show sample data
        if len(long_df_cleaned) > 0:
            cols_to_show = ['REGN_NO', 'SUBJECT_NAME', 'SUBJECT_CODE']
            cols_available = [c for c in cols_to_show if c in long_df_cleaned.columns]
            sample = long_df_cleaned[cols_available].head(3)
            log_container.info(f"Sample data (first 3 rows):")
            log_container.dataframe(sample)
        
        # Add YEAR_FLAG
        long_df_cleaned["YEAR_FLAG"] = int(year_flag)

        total_records = len(long_df_cleaned)
        if total_records == 0:
            log_container.warning("No records to process after data transformation. Check if CSV format matches expected structure.")
            return
            
        log_container.info(f"Total records to process: {total_records}")
        
        success_count = 0
        failure_count = 0

        for i, (index, row) in enumerate(long_df_cleaned.iterrows()):
            student_record = row.dropna().to_dict()

            if 'REGN_NO' in student_record:
                student_record['REGN_NO'] = str(student_record['REGN_NO'])
            if 'SUBJECT_CODE' in student_record:
                student_record['SUBJECT_CODE'] = str(student_record['SUBJECT_CODE'])
            
            # Ensure YEAR_FLAG is int
            if 'YEAR_FLAG' in student_record:
                 student_record['YEAR_FLAG'] = int(student_record['YEAR_FLAG'])

            if update_or_create("student_courses_details", student_record, COMPOSITE_UNIQUE_KEYS, log_container):
                success_count += 1
            else:
                failure_count += 1
            
            # Update progress bar using enumerate index for correct calculation
            progress_val = min((i + 1) / total_records, 1.0)
            progress_bar.progress(progress_val)
        
        log_container.success(f"Sync Complete. Success: {success_count}, Failed: {failure_count}")

    # UI - Column-based layout
    uploaded_file = st.file_uploader("Upload Student CSV", type=['csv'])
    
    year_flag_input = st.number_input("Enter YEAR_FLAG", min_value=1, value=1, step=1, help="The Year Flag to assign to these records (e.g., 1, 2, 3)")

    if st.button("Start Processing & Sync"):
        if uploaded_file is None:
            st.error("Please upload a CSV file first.")
        else:
            log_container = st.container()
            progress_bar = st.progress(0)
            
            with st.spinner("Processing data..."):
                try:
                    df = pd.read_csv(uploaded_file)
                    process_and_sync(df, year_flag_input, log_container, progress_bar)
                except Exception as e:
                    st.error(f"An error occurred reading the file: {e}")

# Student Details Page
elif page == "Student Details":
    import pandas as pd
    import requests
    import json
    from urllib.parse import quote
    from db.index import NOCODB_API_BASE, NOCODB_API_TOKEN, NOCODB_HEADERS
    
    st.title(":bust_in_silhouette: NocoDB Student Details")
    st.markdown("Upload a CSV file and specify the YEAR_FLAG to sync student details to NocoDB.")
    
    # Configs
    HEADERS = NOCODB_HEADERS
    
    COMPOSITE_UNIQUE_KEYS = ["REGN_NO", "YEAR_FLAG"]
    
    def update_or_create(table_name, record, unique_keys, log_container):
        """
        Creates a new record or updates an existing one in NocoDB based on a composite unique key.
        """
        # Construct the raw filter segment for the composite unique key
        filter_parts = []
        for key in unique_keys:
            value = record.get(key)
            if value is None:
                log_container.error(f"Error: Unique key '{key}' is missing or None in record: {record}")
                return
            
            if key == "REGN_NO":
                value = str(value)
            
            filter_parts.append(f'`{key}`,eq,{value}')
        
        raw_filter_segment = ',AND,'.join(filter_parts)
        encoded_filter_segment = quote(raw_filter_segment)
        
        get_url = f"{NOCODB_API_BASE}/{table_name}?filter={encoded_filter_segment}"
        
        try:
            response = requests.get(get_url, headers=HEADERS)
        except Exception as e:
            log_container.error(f"Request failed: {e}")
            return
        
        record_id = None
        if response.status_code == 200:
            try:
                response_json = response.json()
                if response_json.get('list'):
                    record_list = response_json['list']
                    if record_list:
                        record_id = record_list[0]['Id']
            except json.JSONDecodeError:
                log_container.warning(f"Warning: GET response is not valid JSON. Body: {response.text[:200]}...")
        
        if record_id:
            update_url = f"{NOCODB_API_BASE}/{table_name}/{record_id}"
            log_container.info(f"Updating record {record_id}...")
            res = requests.patch(update_url, headers=HEADERS, data=json.dumps(record))
        else:
            create_url = f"{NOCODB_API_BASE}/{table_name}"
            log_container.info(f"Creating new record...")
            res = requests.post(create_url, headers=HEADERS, data=json.dumps(record))
        
        if not res.ok:
            log_container.error(f"Error syncing record. Status: {res.status_code}. Response: {res.text}")
    
    # Input: consolidated_grade_card_flag
    consolidated_grade_card_flag = st.number_input(
        "Enter consolidated_grade_card_flag", 
        min_value=0, 
        max_value=1, 
        value=0, 
        step=1, 
        help="0 for regular, 1 for consolidated. If 1, YEAR_FLAG can be 0, and CSV must have 'consolidated_grade_card_flag' column with value 1."
    )
    
    # Input: YEAR_FLAG
    min_year_flag = 0 if consolidated_grade_card_flag == 1 else 1
    year_flag = st.number_input(
        "Enter YEAR_FLAG", 
        min_value=min_year_flag, 
        value=1 if min_year_flag == 1 else 0,
        step=1, 
        help=f"Minimum value is {min_year_flag}. This value will be assigned to the 'YEAR_FLAG' column."
    )
    
    # Input: CSV File
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            st.write("### Preview of Uploaded Data")
            st.dataframe(df.head())
            
            if st.button("Start Sync"):
                # Validation Logic for consolidated_grade_card_flag
                if consolidated_grade_card_flag == 1:
                    if "consolidated_grade_card_flag" not in df.columns:
                        st.error("Error: 'consolidated_grade_card_flag' is set to 1, but the uploaded CSV is missing the column 'consolidated_grade_card_flag'.")
                        st.stop()
                    
                    if not (df["consolidated_grade_card_flag"] == 1).all():
                        st.error("Error: 'consolidated_grade_card_flag' is set to 1, but not all values in the CSV column 'consolidated_grade_card_flag' are 1.")
                        st.stop()
                
                # Preprocessing
                st.write("### Processing...")
                progress_bar = st.progress(0)
                status_text = st.empty()
                log_container = st.container()
                
                # Assign YEAR_FLAG
                df["YEAR_FLAG"] = year_flag
                
                # Column renaming transformations
                if 'SESSION' in df.columns:
                    df = df.rename(columns={'SESSION': 'YEAR_OF_COMPLETION'})
                if 'Cumulative credits' in df.columns:
                    df = df.rename(columns={'Cumulative credits': 'CUMULATIVE_CREDITS'})
                
                # Drop rows where keys are NaN
                df.dropna(subset=COMPOSITE_UNIQUE_KEYS, inplace=True)
                
                total_rows = len(df)
                st.info(f"Total rows to process: {total_rows}")
                
                for index, row in df.iterrows():
                    # Update progress
                    progress = (index + 1) / total_rows if total_rows > 0 else 1
                    progress_bar.progress(progress)
                    status_text.text(f"Processing row {index + 1} of {total_rows}")
                    
                    # Convert row to dict
                    student_record = row.dropna().to_dict()
                    
                    # Data type conversions
                    if 'REGN_NO' in student_record:
                        student_record['REGN_NO'] = str(int(student_record['REGN_NO']) if isinstance(student_record['REGN_NO'], float) else student_record['REGN_NO'])
                    
                    if 'YEAR_FLAG' in student_record:
                        student_record['YEAR_FLAG'] = int(student_record['YEAR_FLAG'])
                    
                    # Sync
                    update_or_create("student_details", student_record, COMPOSITE_UNIQUE_KEYS, log_container)
                
                status_text.text("Sync Complete!")
                st.success("Sync Process Finished.")
        
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

# Grade Card Generator Page
elif page == "Grade Card Generator":
    from grade_card_generator import GradeCardGenerator
    from db.index import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT
    import traceback
    
    st.title(":card_index: Grade Card Generator")
    st.markdown("Generate PDF Grade Cards from PostgreSQL data.")
    
    # Set default values for directories
    base_dir = os.getcwd()
    output_dir_name = "gradecards"
    assets_dir_name = "assets"
    
    # Main Area - Generation Parameters (Column-based layout)
    st.subheader("Generation Parameters")
    
    year_flag = st.number_input("Year Flag", value=2, step=1, help="Filter by YEAR_FLAG in database")
    
    admission_year = st.number_input("Admission Year", value=2021, step=1, help="Filter by ADMISSION_YEAR in database")
    
    if st.button("Generate Grade Cards", type="primary"):
        # Validate Directories
        base_path = Path(base_dir)
        assets_path = base_path / assets_dir_name
        template_path = base_path / "Grade Card Template.pdf"
        
        if not assets_path.exists():
            st.error(f"Assets directory not found at: {assets_path}")
        elif not template_path.exists():
            st.error(f"Template PDF not found at: {template_path}")
        else:
            status_container = st.container()
            progress_bar = status_container.progress(0)
            status_text = status_container.empty()
            
            try:
                status_text.text("Connecting to database and fetching data...")
                
                # Initialize Generator
                photo_dir = assets_path / "student_photos"
                
                generator = GradeCardGenerator(
                    template_path=str(template_path),
                    output_dir=str(base_path / output_dir_name),
                    assets_dir=str(assets_path),
                    photo_dir=str(photo_dir)
                )
                
                # Database credentials are now loaded from environment variables via db.index
                # No need to override as GradeCardGenerator uses centralized config
                
                # Fetch Data
                data = generator.fetch_all_gradecard_data(year_flag=int(year_flag), admission_year=int(admission_year))
                
                if not data:
                    st.warning("No student data found for the given parameters.")
                    progress_bar.empty()
                    status_text.text("No data found.")
                else:
                    total_students = len(data)
                    st.info(f"Found {total_students} students. Starting generation...")
                    
                    generated_count = 0
                    for i, item in enumerate(data):
                        student_name = item['student_info'].get('name', 'Unknown')
                        reg_no = item['student_info'].get('reg_no', 'N/A')
                        
                        status_text.text(f"Generating {generated_count + 1}/{total_students}: {student_name} ({reg_no})")
                        
                        generator.generate_certificate(
                            student_info=item['student_info'],
                            student_marks=item['student_marks']
                        )
                        
                        generated_count += 1
                        progress_bar.progress(generated_count / total_students)
                    
                    status_text.text("Generation Complete!")
                    st.balloons()
                    st.success(f"Successfully generated {generated_count} grade cards in '{output_dir_name}' directory.")
                    
                    # Optional: Show list of generated files
                    with st.expander("View Generated Files Log"):
                        st.write(f"Generated {generated_count} files.")
                    
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.code(traceback.format_exc())
    
    st.markdown("---")
    st.caption("Grade Card Generator Tool")


# Transcript Generator Page
elif page == "Transcript Generator":
    import time
    from generate_transcript import (
        get_db_connection,
        fetch_all_students_details,
        process_single_student_transcript,
        create_enhanced_template,
        create_enhanced_styles,
        OUTPUT_DIR
    )
    
    st.title(":scroll: Atria University Transcript Generator")
    st.markdown("Generate official transcripts for students by entering their University Seat Number (USN).")
    
    # Ensure dependencies exist
    if 'setup_done' not in st.session_state:
        create_enhanced_template()
        create_enhanced_styles()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        st.session_state['setup_done'] = True
    
    # Input Form
    with st.form("transcript_form"):
        usn_input = st.text_input("Enter Student USN (Reg No)", placeholder="e.g., AU21UG-006").strip()
        submitted = st.form_submit_button("Generate Transcript")
    
    if submitted:
        if not usn_input:
            st.error("Please enter a valid USN.")
        else:
            with st.spinner(f"Fetching details for {usn_input}..."):
                conn = get_db_connection()
                if conn:
                    try:
                        # Fetch student details
                        students = fetch_all_students_details(conn, specific_regn_no=usn_input)
                        
                        if not students:
                            st.error(f":x: Student with USN '{usn_input}' not found in the database.")
                        else:
                            student_record = students[0]
                            st.success(f":white_check_mark: Student found: **{student_record.get('name', 'Unknown')}**")
                            
                            # Generate Transcript
                            with st.spinner("Generating PDF Transcript..."):
                                pdf_path = process_single_student_transcript(conn, student_record)
                            
                            if pdf_path and os.path.exists(pdf_path):
                                st.success(":tada: Transcript generated successfully!")
                                
                                # Read file for download
                                with open(pdf_path, "rb") as pdf_file:
                                    pdf_bytes = pdf_file.read()
                                    
                                file_name = os.path.basename(pdf_path)
                                
                                st.download_button(
                                    label=":arrow_down: Download Transcript PDF",
                                    data=pdf_bytes,
                                    file_name=file_name,
                                    mime="application/pdf"
                                )
                            else:
                                st.error(":x: Failed to generate transcript PDF. Please check logs.")
                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")
                    finally:
                        conn.close()
                else:
                    st.error(":x: Database connection failed.")
