import streamlit as st
import pandas as pd
from config import db # Assuming db is your Firebase Realtime Database reference from config.py
import datetime # Added for type hinting and date operations
from auth_utils import require_auth

@require_auth
def get_last_updated(table_name, user_email=None):
    """
    Fetch the last_updated timestamp for a given table from Firebase metadata.
    
    Args:
        table_name (str): The name of the data section ('attendance', 'students', 'modules', etc.)
    
    Returns:
        str or None: The last_updated ISO timestamp, or None if not found.
    """
    if user_email:
        user_email = user_email.replace('.', ',')
        ref = db.child("metadata").child(table_name).child(user_email)
        snapshot = ref.get(token=st.session_state.user_token)
        if snapshot.val() is not None:
            metadata = snapshot.val()
        else:
            return None
    else:
        metadata = db.child("metadata").child(table_name).get(token=st.session_state.user_token).val()
    if metadata and 'last_updated' in metadata:
        return metadata['last_updated']
    else:
        return None
        
def set_last_updated(table_name, user_email=None):
    """
    Update the last_updated timestamp for a given table in Firebase metadata to current UTC time.
    
    Args:
        table_name (str): The name of the data section ('attendance', 'students', 'modules', etc.)
    
    Returns:
        str: The new last_updated ISO timestamp.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if user_email:
        user_email = user_email.replace('.', ',')
        db.child("metadata").child(table_name).child(user_email).update({
            'last_updated': now_iso
        }, token=st.session_state.user_token)
    else:
        db.child("metadata").child(table_name).update({
            'last_updated': now_iso
        }, token=st.session_state.user_token)
    return now_iso
    
@st.cache_data
def load_students(students_last_updated):
    """
    Load students data from Firebase and ensure all required fields are present.
    
    Returns:
        tuple: (DataFrame with student data, filename) or (None, None) if error or no data
    """
    try:
        user_email = st.session_state.email.replace('.', ',')
        if 'call_count' not in st.session_state:
            st.session_state.call_count = 0
        data = db.child("students").child(user_email).get(token=st.session_state.user_token).val()
        st.session_state.call_count += 1
        print(f"\n{st.session_state.call_count} ---data from firebase----\n", data)

        if not data or 'data' not in data:
            return None, None
            
        # Create DataFrame from records
        df = pd.DataFrame(data['data'])
        
        # Normalize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Ensure required columns exist
        if 'nombre' not in df.columns:
            st.error("Error: El archivo debe contener una columna 'nombre'")
            return None, None
            
        # Clean and standardize data
        df['nombre'] = df['nombre'].astype(str).str.strip()
        
        # Initialize optional fields if they don't exist
        optional_fields = {
            'email': '',
            'canvas_id': '',
            'telefono': '',
            'modulo': '',
            'ciclo': '',
            'fecha_inicio': None
        }
        
        for field, default_value in optional_fields.items():
            if field not in df.columns:
                df[field] = default_value
            else:
                # Clean up the data
                if field == 'fecha_inicio' and pd.api.types.is_datetime64_any_dtype(df[field]):
                    # Convert datetime to string for consistency
                    df[field] = pd.to_datetime(df[field]).dt.strftime('%Y-%m-%d')
                else:
                    df[field] = df[field].fillna(default_value if default_value is not None else '').astype(str).str.strip()
        
        # Reorder columns for consistency
        column_order = ['nombre', 'email', 'canvas_id', 'telefono', 'modulo', 'fecha_inicio', 'ciclo']
        df = df[[col for col in column_order if col in df.columns] + 
                [col for col in df.columns if col not in column_order]]
        
        return df, data.get('filename', 'students.xlsx')
        
    except Exception as e:
        st.error(f"Error loading students: {str(e)}")
        return None, None

def save_students(students_df):
    """
    Save students data to Firebase with proper handling of all fields.
    
    Args:
        students_df (DataFrame): DataFrame containing student records
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        if students_df is None or students_df.empty:
            st.warning("No student data to save.")
            return False
            
        user_email = st.session_state.email.replace('.', ',')
        
        # Create a working copy to avoid modifying the original
        df = students_df.copy()
        
        # Ensure required columns exist
        if 'nombre' not in df.columns:
            st.error("Error: Student data must contain a 'nombre' column")
            return False
            
        # Initialize optional fields if they don't exist
        optional_fields = {
            'email': '',
            'canvas_id': '',
            'telefono': '',
            'modulo': '',
            'ciclo': '',
            'fecha_inicio': None
        }
        
        for field, default_value in optional_fields.items():
            if field not in df.columns:
                df[field] = default_value
        
        # Clean and standardize data
        df['nombre'] = df['nombre'].astype(str).str.strip()
        
        # Convert data types and ensure JSON serialization
        for col in df.columns:
            # Handle numeric types
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].astype('object').where(df[col].notna(), None)
            # Handle datetime types
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d')
            # Handle string types
            else:
                df[col] = df[col].fillna('').astype(str).str.strip()
        
        # Convert to records and ensure all values are JSON-serializable
        records = []
        for _, row in df.iterrows():
            record = {}
            for key, value in row.items():
                if pd.isna(value) or value is None or value == '':
                    record[key] = None
                else:
                    record[key] = str(value) if not isinstance(value, (int, float, bool, str)) else value
            records.append(record)
        
        # Prepare data for Firebase
        data = {
            'filename': 'students.xlsx',
            'data': records,
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
            'metadata': {
                'version': '1.0',
                'fields': list(df.columns),
                'record_count': len(df)
            }
        }
        
        # Save to Firebase with error handling
        try:
            db.child("students").child(user_email).set(data, token=st.session_state.user_token)
            st.success(f"Successfully saved {len(df)} student records.")
            set_last_updated('students')
            return True
        except Exception as firebase_error:
            st.error(f"Firebase error: {str(firebase_error)}")
            return False
            
    except Exception as e:
        st.error(f"Error saving students: {str(e)}")
        if 'df' in locals():
            st.error(f"Columns in DataFrame: {', '.join(df.columns)}")
        return False

# --- Functions moved from 2_Attendance.py ---
def save_attendance(date: datetime.date, attendance_data: dict):
    """Save attendance data to Firebase for a specific date."""
    try:
        user_email = st.session_state.email.replace('.', ',')
        date_str = date.strftime('%Y-%m-%d')
        # Ensure student names (keys in attendance_data) are safe for Firebase paths if necessary
        # For now, assuming they are simple strings.
        db.child("attendance").child(user_email).child(date_str).set(attendance_data)
        set_last_updated('attendance')
        return True
    except Exception as e:
        st.error(f"Error saving attendance for {date_str}: {str(e)}")
        return False

@st.cache_data
def load_attendance(date: datetime.date, attendance_last_updated: str) -> dict:
    """Load attendance data from Firebase for a specific date."""
    try:
        user_email = st.session_state.email.replace('.', ',')
        date_str = date.strftime('%Y-%m-%d')
        raw_data = db.child("attendance").child(user_email).child(date_str).get(token=st.session_state.user_token).val()

        if 'call_count' not in st.session_state:
            st.session_state.call_count = 0
        st.session_state.call_count += 1
        print(f"\n{st.session_state.call_count} ---load attendance data from firebase----\n", raw_data)
        
        if isinstance(raw_data, list):
            # Convert list of records to a dictionary keyed by student name
            processed_data = {}
            for record in raw_data:
                if isinstance(record, dict) and 'Nombre' in record:
                    # Ensure we don't overwrite if names aren't unique, though they should be per day
                    processed_data[record['Nombre']] = record 
                # else: st.warning(f"Skipping invalid record in list for {date_str}: {record}") # Optional: log bad records
            return processed_data
        elif isinstance(raw_data, dict):
            # If it's already a dict (e.g., older data or different save format), return as is
            return raw_data
        else:
            # No data or unexpected type
            return {}
            
    except Exception as e:
        st.error(f"Error loading attendance for {date_str}: {str(e)}")
        return {}

# --- Module Management Functions ---

@st.cache_data(ttl=3600)
def load_modules_from_db(user_email: str) -> pd.DataFrame:
    """Load modules data from Firebase with caching."""
    print("\n\nload_modules_from_db")
    try:
        user_email_sanitized = user_email.replace('.', ',')
        modules_data = db.child("modules").child(user_email_sanitized).get(token=st.session_state.user_token).val()
        print("\n\nmodules_data", modules_data)
        
        if not modules_data:
            return pd.DataFrame(columns=['Nombre', 'Duración (semanas)'])

        # Convert dict of dicts to list of dicts
        modules_list = []
        for key, value in modules_data.items():
            if isinstance(value, dict):
                value['firebase_key'] = key  # optional: store Firebase key
                modules_list.append(value)

        df = pd.DataFrame(modules_list)
        return df
        
    except Exception as e:
        st.error(f"Error al cargar los módulos: {str(e)}")
        return pd.DataFrame(columns=['Nombre', 'Duración (semanas)'])

def load_modules(user_email: str) -> pd.DataFrame:
    if 'modules_df' not in st.session_state or st.session_state.modules_df is None:
        modules = load_modules_from_db(user_email)
        st.session_state.modules_df = modules if modules is not None else pd.DataFrame()
    return st.session_state.modules_df

def update_modules_in_session(updated_df: pd.DataFrame):
    """Update modules in session state."""
    st.session_state.modules = updated_df

def save_modules_to_db(user_email: str, modules_df: pd.DataFrame) -> bool:
    """Save modules to Firebase and update session."""
    try:
        user_email_sanitized = user_email.replace('.', ',')
        db.child("modules").child(user_email_sanitized).set(modules_df.to_dict('records'), token=st.session_state.user_token)
        update_modules_in_session(modules_df)
        return True
    except Exception as e:
        st.error(f"Error saving modules: {str(e)}")
        return False

@st.cache_data
def get_module_name_by_id(user_email: str, module_id: str) -> str:
    """Get the module name by its ID."""
    print("calling get_module_name_by_id with module_id -", module_id)
    try:
        user_email_sanitized = user_email.replace('.', ',')
        modules_data = db.child("modules").child(user_email_sanitized).child(module_id).get(token=st.session_state.user_token).val()
        print("\n-----modules_data from get_module_name_by_id database ---", modules_data)
        if modules_data:
            return modules_data.get('name')
        else:
            print(f"Module with firebase_key '{module_id}' not found for user '{user_email}'.")
            return None
    except Exception as e:
        print(f"Error getting module name by firebase_key: {e}")
        return None

def delete_student(student_nombre_to_delete: str) -> bool:
    """Delete a student from the Firebase list by their 'nombre'."""
    try:
        students_last_updated = get_last_updated('students')
        current_students_df, _ = load_students(students_last_updated) # We don't need the filename here
        if current_students_df is None:
            st.error("No students found to delete from.")
            return False
            
        # Normalize the name to delete for comparison
        normalized_name_to_delete = str(student_nombre_to_delete).lower().strip()

        # Create a boolean series for rows to keep
        if 'nombre' not in current_students_df.columns:
            st.error("Student data is missing 'nombre' column. Cannot delete.")
            return False
        
        # Filter out the student to delete (case-insensitive comparison)
        students_to_keep_df = current_students_df[
            current_students_df['nombre'].astype(str).str.lower().str.strip() != normalized_name_to_delete
        ]

        if len(students_to_keep_df) == len(current_students_df):
            st.warning(f"Student '{student_nombre_to_delete}' not found in the list.")
            return False

        # Save the modified DataFrame (which overwrites the old list)
        if save_students(students_to_keep_df):
            # Note: save_students already calls set_last_updated('students')
            st.success(f"Student '{student_nombre_to_delete}' deleted successfully.")
            return True
        else:
            # save_students would have shown an error
            return False
            
    except Exception as e:
        st.error(f"Error deleting student: {str(e)}")
        return False

def save_attendance(date: datetime.date, attendance_data: list):
    """Save attendance data to Firebase for a specific date."""
    try:
        user_email = st.session_state.email.replace('.', ',')
        date_str = date.strftime('%Y-%m-%d')
        # Ensure student names (keys in attendance_data) are safe for Firebase paths if necessary
        # For now, assuming they are simple strings.
        db.child("attendance").child(user_email).child(date_str).set(attendance_data, token=st.session_state.user_token)
        set_last_updated('attendance', user_email)
        return True
    except Exception as e:
        st.error(f"Error saving attendance for {date_str}: {str(e)}")
        return False

@st.cache_data
def get_attendance_dates(attendance_last_updated: str):
    """
    Get a list of all dates with saved attendance records.
    Returns a sorted list of date strings in 'YYYY-MM-DD' format.
    """
    try:
        user_email = st.session_state.email.replace('.', ',')
        docs = db.child("attendance").child(user_email).get(token=st.session_state.user_token).val()

        if 'call_count' not in st.session_state:
            st.session_state.call_count = 0
        st.session_state.call_count += 1
        print(f"\n{st.session_state.call_count} ---get_attendance_dates-data from firebase----\n{str(docs)[:100]}...")

        if not docs:
            return []
            
        # Extract dates and filter out any None or invalid dates
        dates = []
        for doc in docs:
            try:
                # Validate date format                    
                datetime.datetime.strptime(doc, '%Y-%m-%d')
                dates.append(doc)
            except (ValueError, TypeError):
                continue
        # Sort dates chronologically
        return sorted(dates)
    except Exception as e:
        st.error(f"Error loading attendance dates: {str(e)}")
        return []

def delete_attendance_dates(dates_to_delete=None, delete_all=False):
    """
    Delete attendance records for the specified dates or all records if delete_all=True.
    
    Args:
        dates_to_delete (list, optional): List of date strings in 'YYYY-MM-DD' format.
        delete_all (bool, optional): If True, deletes all attendance records for the user.
        
    Returns:
        bool: True if at least one deletion was successful, False otherwise.
    """
    print(f"Intentando eliminar fechas: {dates_to_delete}, delete_all={delete_all} DESDE utils")
    success = False

    try:
        user_email_key = st.session_state.email.replace('.', ',')
        user_base_attendance_path = f"attendance/{user_email_key}"

        if delete_all:
            # This case is for explicitly deleting ALL records for the user
            all_user_records_ref = db.child(user_base_attendance_path)
            print(f"WARNING: Attempting to delete ALL attendance records at path: {all_user_records_ref.path}")
            
            if not all_user_records_ref.path or all_user_records_ref.path == '/' or not all_user_records_ref.path.startswith('attendance/'):
                st.error(f"CRITICAL SAFETY HALT: Unsafe path for full deletion: '{all_user_records_ref.path}'. Aborting.")
                print(f"CRITICAL SAFETY HALT: Unsafe full deletion path: {all_user_records_ref.path}")
                return False

            try:
                all_user_records_ref.remove(token=st.session_state.user_token)
                print(f"SUCCESS: All attendance records removed at path: {all_user_records_ref.path}")
                print(f"SUCCESS: Attendance records last updated at: {get_last_updated('attendance')}")
                set_last_updated('attendance')
                print(f"SUCCESS: Attendance records last updated at: {get_last_updated('attendance')}")
                return True
            except Exception as e:
                print(f"ERROR: Failed to remove all records: {str(e)}")
                st.error(f"Error al eliminar todos los registros: {str(e)}")
                return False

        # If no dates provided, we don’t do anything
        if not dates_to_delete:
            st.warning("No dates provided for deletion.")
            print("INFO: No dates provided, skipping deletion.")
            return False

        # Validate and clean dates
        valid_dates = []
        for date_str in dates_to_delete:
            try:
                date_str = datetime.datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
                valid_dates.append(date_str.strip())
            except ValueError:
                st.warning(f"Formato de fecha inválido: {date_str}. Se omitirá.")
                print(f"WARNING: Invalid date format '{date_str}' ignored.")

        if not valid_dates:
            st.error("No hay fechas válidas para eliminar después de la validación.")
            print("ERROR: No valid dates to process after validation.")
            return False

        # Delete each valid date
        for date_str in valid_dates:
            full_path = f"{user_base_attendance_path}/{date_str}"
            ref_for_get = db.child(full_path)
            data_snapshot = ref_for_get.get(token=st.session_state.user_token)

            if data_snapshot.val() is not None:
                print(f"INFO: Removing data at path: {full_path}")
                try:
                    db.child(full_path).remove(token=st.session_state.user_token)
                    set_last_updated('attendance')
                    success = True
                except Exception as e:
                    print(f"ERROR: Failed to remove date {date_str}: {str(e)}")
                    st.error(f"Error al eliminar la fecha {date_str}: {str(e)}")
            else:
                print(f"INFO: No data found for date {date_str}, skipping.")

        return success

    except Exception as e:
        st.error(f"Error deleting attendance records: {str(e)}")
        print(f"EXCEPTION: {str(e)}")
        return False

def format_date_for_display(date_value):
    """
    Convert date to MM/DD/YYYY format for display.
    Handles various input formats and edge cases.
    """
    if not date_value or pd.isna(date_value):
        return 'No especificada'
    
    try:
        # Handle different input types
        if isinstance(date_value, str):
            if date_value.strip().lower() in ['', 'no especificada', 'none']:
                return 'No especificada'
            # Try common date formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    date_obj = datetime.datetime.strptime(str(date_value).strip(), fmt)
                    return date_obj.strftime('%m/%d/%Y')
                except ValueError:
                    continue
        elif hasattr(date_value, 'strftime'):
            # Already a datetime object
            return date_value.strftime('%m/%d/%Y')
        else:
            # Try converting to string first
            return format_date_for_display(str(date_value))
    except (ValueError, TypeError, AttributeError):
        pass
    
    return 'No especificada'

def get_student_start_date(all_students_df, student_name):
    """
    Get start date for a specific student.
    Returns formatted date string or 'No especificada'.
    """
    if all_students_df.empty:
        return 'No especificada'
    
    # Find student record (case-insensitive matching)
    student_mask = all_students_df['nombre'].str.strip().str.lower() == student_name.strip().lower()
    matching_students = all_students_df[student_mask]
    
    if matching_students.empty:
        return 'No especificada'
    
    student_data = matching_students.iloc[0]
    start_date = student_data.get('fecha_inicio', 'No especificada')
    
    return format_date_for_display(start_date)

def get_student_phone(all_students_df, student_name):
    """
    Get phone number for a specific student.
    Returns formatted phone number or 'No especificada'.
    """
    if all_students_df.empty:
        return 'No especificada'
    
    # Find student record (case-insensitive matching)
    student_mask = all_students_df['nombre'].str.strip().str.lower() == student_name.strip().lower()
    matching_students = all_students_df[student_mask]
    
    if matching_students.empty:
        return 'No especificada'
    
    student_data = matching_students.iloc[0]
    phone = student_data.get('telefono', 'No especificada')
    
    return phone

def get_student_email(all_students_df, student_name):
    """
    Get email for a specific student.
    Returns formatted email or 'No especificada'.
    """
    if all_students_df.empty:
        return 'No especificada'
    
    # Find student record (case-insensitive matching)
    student_mask = all_students_df['nombre'].str.strip().str.lower() == student_name.strip().lower()
    matching_students = all_students_df[student_mask]
    
    if matching_students.empty:
        return 'No especificada'
    
    student_data = matching_students.iloc[0]
    email = student_data.get('email', 'No especificada')
    
    return email

def create_filename_date_range(start_date, end_date):
    """
    Create a date range string for filename from start and end dates.
    Returns formatted string or None if dates are invalid.
    """
    try:
        # Handle different input types
        if hasattr(start_date, 'strftime'):
            start_str = start_date.strftime('%Y%m%d')
        else:
            start_obj = datetime.datetime.strptime(str(start_date), '%m/%d/%Y')
            start_str = start_obj.strftime('%Y%m%d')
        
        if hasattr(end_date, 'strftime'):
            end_str = end_date.strftime('%Y%m%d')
        else:
            end_obj = datetime.datetime.strptime(str(end_date), '%m/%d/%Y')
            end_str = end_obj.strftime('%Y%m%d')
        
        return f"_{start_str}_a_{end_str}"
    except (ValueError, AttributeError, TypeError):
        return ""

def date_format(date_value, from_format, to_format='%m/%d/%Y'):
    """
    Convert date from one format to another.
    
    Args:
        date_value (str/datetime): The date to convert
        from_format (str): The format of the input date (e.g., '%Y/%m/%d')
        to_format (str): The desired output format (default: '%m/%d/%Y')
    
    Returns:
        str: Formatted date string or 'No especificada' if conversion fails
    
    Examples:
        date_format("2025/10/31", "%Y/%m/%d") -> "10/31/2025"
        date_format("31-10-2025", "%d-%m-%Y") -> "10/31/2025"
        date_format("2025-10-31", "%Y-%m-%d", "%d/%m/%Y") -> "31/10/2025"
    """
    if not date_value or pd.isna(date_value):
        return 'No especificada'
    
    try:
        # Handle datetime objects
        if hasattr(date_value, 'strftime'):
            return date_value.strftime(to_format)
        
        # Handle string dates
        if isinstance(date_value, str):
            date_str = str(date_value).strip()
            if date_str.lower() in ['', 'no especificada', 'none']:
                return 'No especificada'
            
            # Parse with the specified format
            date_obj = datetime.datetime.strptime(date_str, from_format)
            return date_obj.strftime(to_format)
        
        # Try converting other types to string first
        date_str = str(date_value).strip()
        date_obj = datetime.datetime.strptime(date_str, from_format)
        return date_obj.strftime(to_format)
        
    except (ValueError, TypeError, AttributeError):
        return 'No especificada'

@st.cache_data
def get_highest_module_credit(user_email: str, modules_last_updated: str) -> int:
    """
    Get the highest module credit/order number from all modules.
    
    Args:
        user_email: The user's email (with . replaced with ,)
        
    Returns:
        int: The highest credit value found, or 0 if no modules exist
    """
    try:
        # Create a fresh Firebase reference for this operation
        modules_ref = db.child("modules").child(user_email).get(token=st.session_state.user_token)

        if 'call_count' not in st.session_state:
            st.session_state.call_count = 0
        st.session_state.call_count += 1
        print(f"\n{st.session_state.call_count} ---get_highest_module_credit-data from firebase----\n", modules_ref.val())
        if not modules_ref.val():
            return 0
            
        max_credit = 0
        for module_id, module_data in modules_ref.val().items():
            if not module_data or not isinstance(module_data, dict):
                continue
                
            credit = module_data.get('credits')
            try:
                credit = int(credit) if credit is not None else 0
                max_credit = max(max_credit, credit)
            except (ValueError, TypeError):
                continue
                
        return max_credit
        
    except Exception as e:
        st.error(f"Error al obtener el crédito máximo del módulo: {str(e)}")
        return 0

@st.cache_data
def get_module_on_date(user_email: str, target_date: datetime.date = None) -> dict:
    """
    Finds the module active on a given date for the user.
    
    Args:
        user_email: The user's email (with . replaced with ,)
        target_date: The date to check (defaults to today)

    Returns:
        dict: Module information if found, None otherwise
    """
    print("\n\ntarget_date\n", target_date)
    print("\n\nuser_email\n", user_email)

    if target_date is None:
        target_date = datetime.date.today()

    try:
        modules_ref = db.child("modules").child(user_email).get(token=st.session_state.user_token)

        if 'call_count' not in st.session_state:
            st.session_state.call_count = 0
        st.session_state.call_count += 1
        print(f"\n{st.session_state.call_count} ---get_module_on_date-data from firebase----\n", modules_ref.val())

        modules_data = modules_ref.val()
        if not modules_data:
            return None

        target_datetime = datetime.datetime.combine(target_date, datetime.time())

        for module_key, module_data in modules_data.items():
            if not module_data:
                continue

            # Parse start and end dates
            start_str = module_data.get("fecha_inicio_1")
            end_str = module_data.get("fecha_fin_1")

            try:
                if not start_str or not end_str:
                    continue

                start_date = datetime.datetime.fromisoformat(start_str)
                end_date = datetime.datetime.fromisoformat(end_str)

                if start_date <= target_datetime <= end_date:
                    return {
                        'firebase_key': module_key,
                        'module_id': module_data.get('module_id', module_key),
                        'module_name': module_data.get('name', 'Módulo sin nombre'),
                        'ciclo': module_data.get('ciclo', 1),
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat(),
                        'credits': module_data.get('credits', 0)
                    }

            except (ValueError, TypeError) as e:
                print(f"Error processing module {module_key}: {e}")
                continue

        return None

    except Exception as e:
        st.error(f"Error al buscar módulo para la fecha: {str(e)}")
        return None



@st.cache_data
def get_available_modules(user_email: str, modules_last_updated: str) -> list:
    """
    Retrieve and process available modules for a user.
    
    Args:
        user_email: The user's email (with . replaced with ,)
        
    Returns:
        list: List of module options with their details, sorted by proximity to current date
    """
    try:
        # Create a fresh Firebase reference for this operation
        modules_ref = db.child("modules").child(user_email).get(token=st.session_state.user_token)

        if 'call_count' not in st.session_state:
            st.session_state.call_count = 0
        st.session_state.call_count += 1
        print(f"\n{st.session_state.call_count} ---get_available_modules-data from firebase----\n", modules_ref.val())
        
        if not modules_ref.val():
            return []
            
        module_options = []
        today = datetime.datetime.today()
        cutoff_date = today - datetime.timedelta(days=180)
        
        # Process each module
        for module_id, module_data in modules_ref.val().items():
            if not module_data:
                continue
                
            module_name = module_data.get('name', 'Módulo sin nombre')
            
            # Process ciclo 1 if it exists (using new field names)
            if 'fecha_inicio_1' in module_data and module_data['fecha_inicio_1']:
                start_date = module_data['fecha_inicio_1']
                if isinstance(start_date, str):
                    try:
                        start_date_dt = datetime.datetime.fromisoformat(start_date)
                        if start_date_dt >= cutoff_date:
                            module_options.append({
                                'label': f"Inicio: {start_date_dt.strftime('%m/%d/%Y')} - {module_name}",
                                'module_id': module_id,
                                'ciclo': 1,
                                'start_date': module_data['fecha_inicio_1'],
                                'end_date': module_data['fecha_fin_1'],
                                'module_name': module_name,
                                'credits': module_data.get('credits', 1),
                                'duration_weeks': module_data.get('duration_weeks', 3),
                            })
                    except (ValueError, TypeError):
                        continue
            
            # Process ciclo 2 if it exists (using new field names)
            if 'fecha_inicio_2' in module_data and module_data['fecha_inicio_2']:
                start_date = module_data['fecha_inicio_2']
                if isinstance(start_date, str):
                    try:
                        start_date_dt = datetime.datetime.fromisoformat(start_date)
                        if start_date_dt >= cutoff_date:
                            module_options.append({
                                'label': f"{module_name} (Ciclo 2 - Inicia: {start_date_dt.strftime('%m/%d/%Y')})",
                                'module_id': module_id,
                                'ciclo': 2,
                                'start_date': module_data['fecha_inicio_2'],
                                'end_date': module_data['fecha_fin_2'],
                                'module_name': module_name,
                                'credits': module_data.get('credits', 1),
                                'duration_weeks': module_data.get('duration_weeks', 3)
                            })
                    except (ValueError, TypeError):
                        continue
        
        # Sort by proximity to today's date
        module_options.sort(
            key=lambda x: abs((datetime.datetime.fromisoformat(x['start_date']) - today).days)
        )
        
        return module_options
        
    except Exception as e:
        st.error(f"Error al cargar los módulos: {str(e)}")
        return []

def adjust_for_breaks(start, end, breaks):
    """
    Adjusts the end date if a break overlaps the module period.
    """
    extra_days = datetime.timedelta(days=0)
    for b_start, b_end in breaks:
        if b_end < start or b_start > end:
            continue  # no overlap
        overlap_start = max(start, b_start)
        overlap_end = min(end, b_end)
        overlap_days = (overlap_end - overlap_start + datetime.timedelta(days=1)).days
        extra_days += datetime.timedelta(days=overlap_days)
    return start, end + extra_days

def generate_module_schedule(modules, first_cycle_start, num_cycles):
    """
    Args:
        modules (list of dict): Each dict has 'name', 'order', 'duration_weeks'
        first_cycle_start (datetime.date): Starting date for cicle 1
        num_cycles (int): Number of cycles to generate

    Returns:
        dict: { cycle_number: [ {module_name, start_date, end_date}, ... ] }
    """
    modules_sorted = sorted(modules, key=lambda m: m['order'])
    schedule = {}
    current_cycle_start = first_cycle_start

    for cicle in range(1, num_cycles + 1):
        schedule[cicle] = []
        current_start = current_cycle_start

        for mod in modules_sorted:
            end_date = current_start + datetime.timedelta(weeks=mod['duration_weeks'])
            schedule[cicle].append({
                'module_name': mod['name'],
                'start_date': current_start,
                'end_date': end_date,
            })
            current_start = end_date  # next module starts after this

        # Calculate next cicle start: last module end + 1 day
        current_cycle_start = schedule[cicle][-1]['end_date'] + datetime.timedelta(days=1)

    return schedule

def highlight_style(theme):
    """Returns a CSS style string for a given theme."""
    themes = {
        'warning': "background-color: #fffce7; color: #926c05",
        'info': "background-color: #1c83e11a; color: #004280",
        'success': "background-color: #21c3541a; color: #177233",
        'error': "background-color: #f8d7da; color: #7d353b"
    }
    return themes.get(theme, "")


def strip_email_and_map_course(course_email):
    """Strips the @part of an email and maps course codes to their names."""
    course, _ = course_email.split('@')
    course = course.upper()
    course_map = {
        'CBA2': 'Computer Business Applications 2',
        'CBA1': 'Computer Business Applications 1',
        'PCT': 'Patient Care Technician',   
        'DATABASE': 'Database Administration',
        'HAVC': 'HVAC Technician'
    }
    return course_map.get(course, course)

@st.cache_data(ttl=60*60)  # Cache for 1 hour
def load_all_attendance(_db, user_email, attendance_last_updated):
    """Load all attendance records for a user at once"""
    try:
        # Replace dots in email for Firebase key
        user_key = user_email.replace('.', ',')
        # Get all attendance data for this user
        all_attendance = _db.child("attendance").child(user_key).get().val() or {}
        return all_attendance
    except Exception as e:
        st.error(f"Error loading attendance data: {e}")
        return {}