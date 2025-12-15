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
            response = requests.get(get_url, headers=HEADERS, timeout=30)
            
            record_id = None
            if response.status_code == 200:
                response_json = response.json()
                if response_json.get('list'):
                    record_list = response_json['list']
                    if record_list:
                        record_id = record_list[0]['Id']
            
            if record_id:
                update_url = f"{NOCODB_API_BASE}/{table_name}/{record_id}"
                res = requests.patch(update_url, headers=HEADERS, data=json.dumps(record), timeout=30)
                action = "UPDATED"
            else:
                create_url = f"{NOCODB_API_BASE}/{table_name}"
                res = requests.post(create_url, headers=HEADERS, data=json.dumps(record), timeout=30)
                action = "CREATED"

            if not res.ok:
                log_container.error(f"Failed to {action} record: {res.text} (Status: {res.status_code})")
                return False
            else:
                return True

        except Exception as e:
            log_container.error(f"Exception during sync: {str(e)}")
            return False

    def process_and_sync(df, year_flag, admission_year, log_container, progress_bar):
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
        long_df_cleaned = long_df.dropna(subset=['SUBJECT_NAME', 'SUBJECT_CODE'], how='all').copy()
        
        # Debug: Show sample data
        if len(long_df_cleaned) > 0:
            cols_to_show = ['REGN_NO', 'SUBJECT_NAME', 'SUBJECT_CODE']
            cols_available = [c for c in cols_to_show if c in long_df_cleaned.columns]
            sample = long_df_cleaned[cols_available].head(3)
            log_container.info(f"Sample data (first 3 rows):")
            log_container.dataframe(sample)
        
        # Add YEAR_FLAG, ADMISSION_YEAR, and YEAR
        long_df_cleaned["YEAR_FLAG"] = int(year_flag)
        long_df_cleaned["ADMISSION_YEAR"] = int(admission_year)
        long_df_cleaned["YEAR"] = int(admission_year)

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

    # UI - Year Flag and Admission Year first, then CSV upload
    col1, col2 = st.columns(2)
    with col1:
        year_flag_options = [1, 2, 3, 4]
        year_flag_input = st.selectbox("Enter YEAR_FLAG", options=year_flag_options, index=0, help="The Year Flag to assign to these records (e.g., 1, 2, 3, 4)")
    with col2:
        admission_year_input = st.number_input("Enter Admission Year", min_value=2000, max_value=2100, value=2021, step=1, help="The Admission Year to assign to these records (e.g., 2021)")
    
    uploaded_file = st.file_uploader("Upload Student CSV", type=['csv'])
    
    # Initialize variables before conditional block
    data_exists = False
    
    # Show preview and validation if file is uploaded
    if uploaded_file is not None:
        df_preview = pd.read_csv(uploaded_file)
        st.write("### Preview of Uploaded Data")
        st.dataframe(df_preview.head())
        
        # Check if ADMISSION_YEAR column exists in CSV and validate
        if 'ADMISSION_YEAR' in df_preview.columns:
            csv_admission_years = df_preview['ADMISSION_YEAR'].dropna().unique()
            mismatched_years = [y for y in csv_admission_years if int(y) != admission_year_input]
            if mismatched_years:
                st.warning(f"⚠️ **Warning:** The ADMISSION_YEAR in the uploaded file contains values {list(csv_admission_years)} which may not match the input Admission Year ({admission_year_input}). The input value will be used for syncing.")
        
        # Check if YEAR_FLAG and YEAR (Admission Year) combination already exists in NocoDB
        def check_existing_data_in_nocodb(year_flag, admission_year):
            """Check if data with this YEAR_FLAG and YEAR combination exists in student_course_details table."""
            try:
                from db.index import STUDENT_COURSES_DETAILS_TABLE
                filter_segment = f'(YEAR_FLAG,eq,{year_flag})~and(YEAR,eq,{admission_year})'
                encoded_filter = quote(filter_segment)
                check_url = f"{NOCODB_API_BASE}/{STUDENT_COURSES_DETAILS_TABLE}?where={encoded_filter}&limit=1"
                
                response = requests.get(check_url, headers=HEADERS, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('list') and len(data['list']) > 0:
                        total_rows = data.get('pageInfo', {}).get('totalRows', 1)
                        return True, total_rows
                return False, 0
            except Exception as e:
                st.error(f"Error checking NocoDB: {e}")
                return False, 0
        
        # Check for existing data
        data_exists, record_count = check_existing_data_in_nocodb(year_flag_input, admission_year_input)
        
        if data_exists:
            st.warning(f"⚠️ **Warning:** Student data for Admission Year **{admission_year_input}** and YEAR_FLAG **{year_flag_input}** already exists in NocoDB. Syncing may create duplicates.")
            
            # Use session state to track if user clicked "Proceed Anyway"
            proceed_key = f"proceed_anyway_{year_flag_input}_{admission_year_input}"
            if proceed_key not in st.session_state:
                st.session_state[proceed_key] = False
            
            if st.button("Proceed Anyway", key="proceed_anyway_btn"):
                st.session_state[proceed_key] = True
                st.rerun()
            
            can_proceed = st.session_state[proceed_key]
        else:
            can_proceed = True
        
        # Reset file pointer for processing
        uploaded_file.seek(0)
    else:
        can_proceed = False

    if st.button("Start Processing & Sync", disabled=not can_proceed if uploaded_file is not None and data_exists else False):
        if uploaded_file is None:
            st.error("Please upload a CSV file first.")
        elif data_exists and not can_proceed:
            st.error("Please click 'Proceed Anyway' button to confirm syncing with existing data.")
        else:
            log_container = st.container()
            progress_bar = st.progress(0)
            
            with st.spinner("Processing data..."):
                try:
                    uploaded_file.seek(0)  # Reset file pointer
                    df = pd.read_csv(uploaded_file)
                    process_and_sync(df, year_flag_input, admission_year_input, log_container, progress_bar)
                except Exception as e:
                    st.error(f"An error occurred reading the file: {e}")

# Student Details Page
elif page == "Student Details":
    import pandas as pd
    import requests
    import json
    from urllib.parse import quote
    from db.index import NOCODB_API_BASE, NOCODB_API_TOKEN, NOCODB_HEADERS, STUDENT_DETAILS_TABLE
    
    st.title(":bust_in_silhouette: Student Details")
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
            response = requests.get(get_url, headers=HEADERS, timeout=30)
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
            res = requests.patch(update_url, headers=HEADERS, data=json.dumps(record), timeout=30)
        else:
            create_url = f"{NOCODB_API_BASE}/{table_name}"
            log_container.info(f"Creating new record...")
            res = requests.post(create_url, headers=HEADERS, data=json.dumps(record), timeout=30)
        
        if not res.ok:
            log_container.error(f"Error syncing record. Status: {res.status_code}. Response: {res.text}")
    
    def process_student_details_sync(df, year_flag, consolidated_grade_card_flag, admission_year=None):
        """Common sync logic for both tabs."""
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
        
        # Assign ADMISSION_YEAR if provided
        if admission_year is not None:
            df["ADMISSION_YEAR"] = int(admission_year)
        
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
    
    # Create two tabs: Consolidated and Annual
    tab_consolidated, tab_annual = st.tabs(["📋 Consolidated", "📅 Annual"])
    
    # Consolidated Tab - consolidated_grade_card_flag is always 1, YEAR_FLAG is always 0
    with tab_consolidated:
        st.subheader("Consolidated Grade Card Upload")
        st.info("This tab is for uploading consolidated grade cards. The `consolidated_grade_card_flag` is automatically set to **1** and `YEAR_FLAG` is set to **0**.")
        
        # Input: Admission Year for Consolidated
        admission_year_consolidated = st.number_input(
            "Enter Admission Year",
            min_value=2000,
            max_value=2100,
            value=2021,
            step=1,
            help="Admission Year for these records (e.g., 2021, 2022)",
            key="consolidated_admission_year"
        )
        
        # Input: CSV File for Consolidated
        uploaded_file_consolidated = st.file_uploader("Choose a CSV file", type="csv", key="consolidated_csv")
        
        if uploaded_file_consolidated is not None:
            try:
                df_consolidated = pd.read_csv(uploaded_file_consolidated)
                st.write("### Preview of Uploaded Data")
                st.dataframe(df_consolidated.head())
                
                # Check if ADMISSION_YEAR column exists in CSV and validate
                if 'ADMISSION_YEAR' in df_consolidated.columns:
                    csv_admission_years = df_consolidated['ADMISSION_YEAR'].dropna().unique()
                    mismatched_years = [y for y in csv_admission_years if int(y) != admission_year_consolidated]
                    if mismatched_years:
                        st.warning(f"⚠️ **Warning:** The ADMISSION_YEAR in the uploaded file contains values {list(csv_admission_years)} which may not match the input Admission Year ({admission_year_consolidated}). The input value will be used for syncing.")
                
                # Check if consolidated_grade_card_flag=1 and ADMISSION_YEAR combination already exists in NocoDB
                def check_existing_consolidated_data(admission_year):
                    """Check if data with consolidated_grade_card_flag=1 and ADMISSION_YEAR exists in student_details table."""
                    try:
                        filter_segment = f'(consolidated_grade_card_flag,eq,1)~and(ADMISSION_YEAR,eq,{admission_year})'
                        encoded_filter = quote(filter_segment)
                        check_url = f"{NOCODB_API_BASE}/{STUDENT_DETAILS_TABLE}?where={encoded_filter}&limit=1"
                        
                        response = requests.get(check_url, headers=HEADERS, timeout=30)
                        if response.status_code == 200:
                            data = response.json()
                            if data.get('list') and len(data['list']) > 0:
                                total_rows = data.get('pageInfo', {}).get('totalRows', 1)
                                return True, total_rows
                        return False, 0
                    except Exception as e:
                        st.error(f"Error checking NocoDB: {e}")
                        return False, 0
                
                # Check for existing data
                consolidated_data_exists, consolidated_record_count = check_existing_consolidated_data(admission_year_consolidated)
                
                if consolidated_data_exists:
                    st.warning(f"⚠️ **Warning:** Student data with Admission Year **{admission_year_consolidated}** (consolidated credits and CGPA) already exists in NocoDB. Syncing may create duplicates.")
                    
                    # Use session state to track if user clicked "Proceed Anyway"
                    proceed_key_consolidated = f"proceed_anyway_consolidated_{admission_year_consolidated}"
                    if proceed_key_consolidated not in st.session_state:
                        st.session_state[proceed_key_consolidated] = False
                    
                    if st.button("Proceed Anyway", key="proceed_anyway_consolidated_btn"):
                        st.session_state[proceed_key_consolidated] = True
                        st.rerun()
                    
                    can_proceed_consolidated = st.session_state[proceed_key_consolidated]
                else:
                    can_proceed_consolidated = True
                
                # Reset file pointer
                uploaded_file_consolidated.seek(0)
                
                if st.button("Start Sync", key="consolidated_sync_btn", disabled=consolidated_data_exists and not can_proceed_consolidated):
                    uploaded_file_consolidated.seek(0)
                    df_consolidated = pd.read_csv(uploaded_file_consolidated)
                    # YEAR_FLAG is hardcoded to 0 for consolidated
                    process_student_details_sync(df_consolidated, year_flag=0, consolidated_grade_card_flag=1, admission_year=admission_year_consolidated)
            
            except Exception as e:
                st.error(f"Error reading CSV: {e}")
    
    # Annual Tab - consolidated_grade_card_flag is always 0
    with tab_annual:
        st.subheader("Annual Grade Card Upload")
        st.info("This tab is for uploading annual/regular grade cards. The `consolidated_grade_card_flag` is automatically set to **0**.")
        
        # Input: YEAR_FLAG and ADMISSION_YEAR
        col1, col2 = st.columns(2)
        with col1:
            year_flag_options = [1, 2, 3, 4]
            year_flag_annual = st.selectbox(
                "Enter YEAR_FLAG", 
                options=year_flag_options,
                index=0,
                help="YEAR_FLAG for annual records.",
                key="annual_year_flag"
            )
        with col2:
            admission_year_annual = st.number_input(
                "Enter Admission Year",
                min_value=2000,
                max_value=2100,
                value=2021,
                step=1,
                help="Admission Year for these records (e.g., 2021, 2022)",
                key="annual_admission_year"
            )
        
        # Input: CSV File for Annual
        uploaded_file_annual = st.file_uploader("Choose a CSV file", type="csv", key="annual_csv")
        
        if uploaded_file_annual is not None:
            try:
                df_annual = pd.read_csv(uploaded_file_annual)
                st.write("### Preview of Uploaded Data")
                st.dataframe(df_annual.head())
                
                # Check if ADMISSION_YEAR column exists in CSV and validate
                if 'ADMISSION_YEAR' in df_annual.columns:
                    csv_admission_years = df_annual['ADMISSION_YEAR'].dropna().unique()
                    mismatched_years = [y for y in csv_admission_years if int(y) != admission_year_annual]
                    if mismatched_years:
                        st.warning(f"⚠️ **Warning:** The ADMISSION_YEAR in the uploaded file contains values {list(csv_admission_years)} which may not match the input Admission Year ({admission_year_annual}). The input value will be used for syncing.")
                
                # Check if YEAR_FLAG and ADMISSION_YEAR combination already exists in NocoDB
                def check_existing_student_details(year_flag, admission_year):
                    """Check if data with this YEAR_FLAG and ADMISSION_YEAR combination exists in student_details table."""
                    try:
                        filter_segment = f'(YEAR_FLAG,eq,{year_flag})~and(ADMISSION_YEAR,eq,{admission_year})'
                        encoded_filter = quote(filter_segment)
                        check_url = f"{NOCODB_API_BASE}/{STUDENT_DETAILS_TABLE}?where={encoded_filter}&limit=1"
                        
                        response = requests.get(check_url, headers=HEADERS, timeout=30)
                        if response.status_code == 200:
                            data = response.json()
                            if data.get('list') and len(data['list']) > 0:
                                total_rows = data.get('pageInfo', {}).get('totalRows', 1)
                                return True, total_rows
                        return False, 0
                    except Exception as e:
                        st.error(f"Error checking NocoDB: {e}")
                        return False, 0
                
                # Check for existing data
                annual_data_exists, annual_record_count = check_existing_student_details(year_flag_annual, admission_year_annual)
                
                if annual_data_exists:
                    st.warning(f"⚠️ **Warning:** Student data for Admission Year **{admission_year_annual}** and YEAR_FLAG **{year_flag_annual}** already exists in NocoDB. Syncing may create duplicates.")
                    
                    # Use session state to track if user clicked "Proceed Anyway"
                    proceed_key_annual = f"proceed_anyway_annual_{year_flag_annual}_{admission_year_annual}"
                    if proceed_key_annual not in st.session_state:
                        st.session_state[proceed_key_annual] = False
                    
                    if st.button("Proceed Anyway", key="proceed_anyway_annual_btn"):
                        st.session_state[proceed_key_annual] = True
                        st.rerun()
                    
                    can_proceed_annual = st.session_state[proceed_key_annual]
                else:
                    can_proceed_annual = True
                
                # Reset file pointer
                uploaded_file_annual.seek(0)
                
                if st.button("Start Sync", key="annual_sync_btn", disabled=annual_data_exists and not can_proceed_annual):
                    uploaded_file_annual.seek(0)
                    df_annual = pd.read_csv(uploaded_file_annual)
                    process_student_details_sync(df_annual, year_flag_annual, consolidated_grade_card_flag=0, admission_year=admission_year_annual)
            
            except Exception as e:
                st.error(f"Error reading CSV: {e}")

# Grade Card Generator Page
elif page == "Grade Card Generator":
    from grade_card_generator import GradeCardGenerator
    from db.index import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT
    from r2 import generate_batch_timestamp, upload_grade_card, get_presigned_url, list_grade_cards, get_latest_batch_folder, download_batch_as_zip
    import traceback
    
    st.title(":card_index: Grade Card Generator")
    st.markdown("Generate PDF Grade Cards from PostgreSQL data and upload to R2 storage.")
    
    # Set default values for directories
    base_dir = os.getcwd()
    output_dir_name = "gradecards"
    assets_dir_name = "assets"
    
    # Main Area - Generation Parameters (Column-based layout)
    st.subheader("Generation Parameters")
    
    st.markdown("**Required Filters:**")
    col1, col2 = st.columns(2)
    with col1:
        year_flag_options = [1, 2, 3, 4]
        year_flag = st.selectbox("Year Flag", options=year_flag_options, index=1, help="Filter by YEAR_FLAG in database (Required)")
    with col2:
        admission_year = st.number_input("Admission Year", value=2021, step=1, help="Filter by ADMISSION_YEAR in database (Required)")
    
    st.markdown("**Optional Filters:**")
    col3, col4 = st.columns(2)
    with col3:
        regn_no = st.text_input("Registration Number (REGN_NO)", value="", help="Filter by specific student REGN_NO (Optional - e.g., AU21UG-001)")
    with col4:
        course_options = ["All", "FOU", "BDes", "LS", "ES", "eMob", "IT", "DT", "BBA"]
        academic_course_id = st.selectbox(
            "Academic Course ID", 
            options=course_options,
            index=0,
            help="Filter by ACADEMIC_COURSE_ID (Optional - select 'All' for no filter)"
        )
    
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
                
                # Fetch Data with optional filters
                data = generator.fetch_all_gradecard_data(
                    year_flag=int(year_flag), 
                    admission_year=int(admission_year),
                    regn_no=regn_no if regn_no.strip() else None,
                    academic_course_id=academic_course_id if academic_course_id != "All" else None
                )
                
                if not data:
                    st.warning("No student data found for the given parameters.")
                    progress_bar.empty()
                    status_text.text("No data found.")
                else:
                    total_students = len(data)
                    st.info(f"Found {total_students} students. Starting generation...")
                    
                    # Generate batch timestamp for R2 folder
                    batch_timestamp = generate_batch_timestamp()
                    
                    generated_count = 0
                    r2_uploaded_count = 0
                    r2_keys = []
                    
                    for i, item in enumerate(data):
                        student_name = item['student_info'].get('name', 'Unknown')
                        reg_no = item['student_info'].get('reg_no', 'N/A')
                        
                        status_text.text(f"Generating {i + 1}/{total_students}: {student_name} ({reg_no})")
                        
                        # Generate grade card and get the output path
                        output_path = generator.generate_certificate(
                            student_info=item['student_info'],
                            student_marks=item['student_marks']
                        )
                        
                        if output_path:
                            generated_count += 1
                            
                            # Upload to R2
                            status_text.text(f"Uploading to R2 {i + 1}/{total_students}: {student_name} ({reg_no})")
                            success, r2_key = upload_grade_card(
                                file_path=output_path,
                                batch_timestamp=batch_timestamp,
                                regn_no=reg_no,
                                student_name=student_name
                            )
                            
                            if success and r2_key:
                                r2_uploaded_count += 1
                                r2_keys.append(r2_key)
                        
                        progress_bar.progress((i + 1) / total_students)
                    
                    status_text.text("Generation Complete!")
                    st.balloons()
                    st.success(f"Successfully generated {generated_count} grade cards.")
                    
                    if r2_uploaded_count > 0:
                        st.success(f"✅ Uploaded {r2_uploaded_count} grade cards to R2 (Folder: `{batch_timestamp}`)")
                    
                    # Show uploaded files with download links
                    if r2_keys:
                        with st.expander("📁 View Uploaded Files & Download Links"):
                            st.write(f"**R2 Folder:** `gradecards/{batch_timestamp}/`")
                            st.write(f"**Total Files:** {len(r2_keys)}")
                            st.markdown("---")
                            for r2_key in r2_keys:
                                filename = r2_key.split('/')[-1]
                                download_url = get_presigned_url(r2_key)
                                if download_url:
                                    st.markdown(f"📄 [{filename}]({download_url})")
                                else:
                                    st.text(f"📄 {filename} (URL unavailable)")
                    
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.code(traceback.format_exc())
    
    st.markdown("---")
    
    # Download Section - At Bottom
    st.subheader("📥 Download Grade Cards")
    st.markdown("Download all grade cards from the latest batch folder in R2 storage.")
    
    col_download, col_info = st.columns([1, 2])
    with col_download:
        if st.button("Download Latest Batch", key="download_gradecards_btn"):
            with st.spinner("Preparing download..."):
                zip_data, batch_ts, file_count = download_batch_as_zip('gradecards')
                if zip_data and file_count > 0:
                    st.session_state['gradecard_zip_data'] = zip_data
                    st.session_state['gradecard_batch_ts'] = batch_ts
                    st.session_state['gradecard_file_count'] = file_count
                    st.success(f"✅ Ready! Found {file_count} files in batch `{batch_ts}`")
                elif batch_ts:
                    st.warning(f"No files found in batch `{batch_ts}`")
                else:
                    st.warning("No batch folders found in R2 storage.")
    
    with col_info:
        # Show latest batch info
        latest_batch = get_latest_batch_folder('gradecards')
        if latest_batch:
            st.info(f"📁 Latest batch folder: `{latest_batch}`")
        else:
            st.info("📁 No batch folders found yet.")
    
    # Show download link if data is ready
    if 'gradecard_zip_data' in st.session_state and st.session_state['gradecard_zip_data']:
        st.download_button(
            label=f"⬇️ Download ZIP ({st.session_state['gradecard_file_count']} files)",
            data=st.session_state['gradecard_zip_data'],
            file_name=f"gradecards_{st.session_state['gradecard_batch_ts']}.zip",
            mime="application/zip",
            key="download_gradecard_zip"
        )
    
    st.markdown("---")
    st.caption("Grade Card Generator Tool")


# Transcript Generator Page
elif page == "Transcript Generator":
    import time
    import traceback
    from generate_transcript import (
        get_db_connection,
        fetch_all_students_details,
        process_single_student_transcript,
        create_enhanced_template,
        create_enhanced_styles,
        OUTPUT_DIR
    )
    from r2 import generate_batch_timestamp, upload_transcript, get_presigned_url, get_latest_batch_folder, download_batch_as_zip
    
    st.title(":scroll: Atria University Transcript Generator")
    st.markdown("Generate official transcripts for students and upload to R2 storage.")
    
    # Ensure dependencies exist
    if 'setup_done' not in st.session_state:
        create_enhanced_template()
        create_enhanced_styles()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        st.session_state['setup_done'] = True
    
    # Filter Fields
    st.subheader("Generation Parameters")
    
    # Required field
    st.markdown("**Required:**")
    transcript_year_of_completion = st.text_input(
        "Year of Completion *", 
        value="", 
        help="Filter by YEAR_OF_COMPLETION (e.g., 2024-2025) - REQUIRED",
        key="transcript_year_of_completion"
    )
    
    # Optional fields
    st.markdown("**Optional Filters:**")
    col1, col2 = st.columns(2)
    with col1:
        transcript_regn_no = st.text_input(
            "Registration Number (REGN_NO)", 
            value="", 
            help="Filter by specific student REGN_NO (e.g., AU21UG-001)",
            key="transcript_regn_no"
        )
    with col2:
        transcript_course_options = ["All", "FOU", "BDes", "LS", "ES", "eMob", "IT", "DT", "BBA"]
        transcript_academic_course_id = st.selectbox(
            "Academic Course ID", 
            options=transcript_course_options,
            index=0,
            help="Filter by ACADEMIC_COURSE_ID (select 'All' for no filter)",
            key="transcript_course_id"
        )
    
    if st.button("Generate Transcripts", type="primary"):
        # Validate required field
        if not transcript_year_of_completion.strip():
            st.error("Please enter the Year of Completion. This field is required.")
        else:
            with st.spinner("Fetching student details..."):
                conn = get_db_connection()
                if conn:
                    try:
                        # Fetch students with filters
                        students = fetch_all_students_details(
                            conn,
                            specific_regn_no=transcript_regn_no if transcript_regn_no.strip() else None,
                            year_of_completion=transcript_year_of_completion.strip(),
                            academic_course_id=transcript_academic_course_id if transcript_academic_course_id != "All" else None
                        )
                        
                        if not students:
                            st.warning("No students found matching the given filters.")
                        else:
                            total_students = len(students)
                            st.info(f"Found {total_students} student(s). Starting transcript generation...")
                            
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            # Generate batch timestamp for R2 folder
                            batch_timestamp = generate_batch_timestamp()
                            
                            generated_count = 0
                            failed_count = 0
                            r2_uploaded_count = 0
                            r2_keys = []
                            
                            for i, student_record in enumerate(students):
                                student_name = student_record.get('name', 'Unknown')
                                reg_no = student_record.get('regn_no', 'N/A')
                                
                                status_text.text(f"Generating {i + 1}/{total_students}: {student_name} ({reg_no})")
                                
                                try:
                                    pdf_path = process_single_student_transcript(conn, student_record)
                                    if pdf_path and os.path.exists(pdf_path):
                                        generated_count += 1
                                        
                                        # Upload to R2
                                        status_text.text(f"Uploading to R2 {i + 1}/{total_students}: {student_name} ({reg_no})")
                                        success, r2_key = upload_transcript(
                                            file_path=pdf_path,
                                            batch_timestamp=batch_timestamp,
                                            regn_no=reg_no,
                                            student_name=student_name
                                        )
                                        
                                        if success and r2_key:
                                            r2_uploaded_count += 1
                                            r2_keys.append(r2_key)
                                    else:
                                        failed_count += 1
                                except Exception as e:
                                    print(f"Error generating transcript for {reg_no}: {e}")
                                    failed_count += 1
                                
                                progress_bar.progress((i + 1) / total_students)
                            
                            status_text.text("Generation Complete!")
                            
                            if generated_count > 0:
                                st.balloons()
                                st.success(f"Successfully generated {generated_count} transcript(s).")
                            
                            if r2_uploaded_count > 0:
                                st.success(f"✅ Uploaded {r2_uploaded_count} transcripts to R2 (Folder: `{batch_timestamp}`)")
                            
                            if failed_count > 0:
                                st.warning(f"{failed_count} transcript(s) failed to generate. Check logs for details.")
                            
                            # Show uploaded files with download links
                            if r2_keys:
                                with st.expander("📁 View Uploaded Files & Download Links"):
                                    st.write(f"**R2 Folder:** `transcripts/{batch_timestamp}/`")
                                    st.write(f"**Total Files:** {len(r2_keys)}")
                                    st.markdown("---")
                                    for r2_key in r2_keys:
                                        filename = r2_key.split('/')[-1]
                                        download_url = get_presigned_url(r2_key)
                                        if download_url:
                                            st.markdown(f"📄 [{filename}]({download_url})")
                                        else:
                                            st.text(f"📄 {filename} (URL unavailable)")
                            
                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")
                        st.code(traceback.format_exc())
                    finally:
                        conn.close()
                else:
                    st.error(":x: Database connection failed.")
    
    st.markdown("---")
    
    # Download Section - At Bottom
    st.subheader("📥 Download Transcripts")
    st.markdown("Download all transcripts from the latest batch folder in R2 storage.")
    
    col_download_t, col_info_t = st.columns([1, 2])
    with col_download_t:
        if st.button("Download Latest Batch", key="download_transcripts_btn"):
            with st.spinner("Preparing download..."):
                zip_data, batch_ts, file_count = download_batch_as_zip('transcripts')
                if zip_data and file_count > 0:
                    st.session_state['transcript_zip_data'] = zip_data
                    st.session_state['transcript_batch_ts'] = batch_ts
                    st.session_state['transcript_file_count'] = file_count
                    st.success(f"✅ Ready! Found {file_count} files in batch `{batch_ts}`")
                elif batch_ts:
                    st.warning(f"No files found in batch `{batch_ts}`")
                else:
                    st.warning("No batch folders found in R2 storage.")
    
    with col_info_t:
        # Show latest batch info
        latest_batch_t = get_latest_batch_folder('transcripts')
        if latest_batch_t:
            st.info(f"📁 Latest batch folder: `{latest_batch_t}`")
        else:
            st.info("📁 No batch folders found yet.")
    
    # Show download link if data is ready
    if 'transcript_zip_data' in st.session_state and st.session_state['transcript_zip_data']:
        st.download_button(
            label=f"⬇️ Download ZIP ({st.session_state['transcript_file_count']} files)",
            data=st.session_state['transcript_zip_data'],
            file_name=f"transcripts_{st.session_state['transcript_batch_ts']}.zip",
            mime="application/zip",
            key="download_transcript_zip"
        )
    
    st.markdown("---")
    st.caption("Transcript Generator Tool")
