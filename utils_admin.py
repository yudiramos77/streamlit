import streamlit as st
import pandas as pd
import uuid
import numpy as np
from config import db # Assuming db is your Firebase Realtime Database reference from config.py
import datetime
import time


def admin_get_last_updated(table_name, course_email):
    """
    Fetch the last_updated timestamp for a given table from Firebase metadata.
    
    Args:
        table_name (str): The name of the data section ('attendance', 'students', 'modules', etc.)
        course_email (str): The email of the course to get the last updated timestamp for
    
    Returns:
        str or None: The last_updated ISO timestamp, or None if not found.
    """
    print("\n\admin_get_last_updated", course_email)
    if course_email:
        course_email = course_email.replace('.', ',')
        ref = db.child("metadata").child(table_name).child(course_email)
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
        
def admin_set_last_updated(table_name, course_email):
    """
    Update the last_updated timestamp for a given table in Firebase metadata to current UTC time.
    
    Args:
        table_name (str): The name of the data section ('attendance', 'students', 'modules', etc.)
        course_email (str): The email of the course to update
    
    Returns:
        str: The new last_updated ISO timestamp.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if course_email:
        safe_email = course_email.replace('.', ',')
        db.child("metadata").child(table_name).child(safe_email).update({
            'last_updated': now_iso
        }, token=st.session_state.user_token)
    else:
        db.child("metadata").child(table_name).update({
            'last_updated': now_iso
        }, token=st.session_state.user_token)
    return now_iso
    
def admin_get_students_by_email(email):
    """
    Retrieves student records from the database based on the provided email.
    This function is designed for a database structure where the email
    is the primary key under 'students', and its value is an object
    containing a 'data' array of student details.

    Args:
        email (str): The email address which is also the key under the 'students' node.

    Returns:
        dict: A dictionary of student records if found, or an empty dictionary
              if no students are found or an error occurs.
    """
    try:
        # Reference to the 'students' node in your database
        students_ref = db.child("students")

        # Directly access the student data using the email as the key.
        # Firebase keys cannot contain '.', '#', '$', '[', or ']'
        # If your email keys literally contain '.' like "cba2@iti.edu",
        # you might need to escape them or store them differently if direct
        # key access doesn't work. However, typically, Firebase handles
        # this if the key was set using a string.
        snapshot = students_ref.child(email.replace('.', ',')).get(token=st.session_state.user_token) # Common workaround for '.' in keys

        # Check if any data was returned for that specific email key
        if not snapshot.val():
            print(f"No student entry found for email key: {email}")
            return {}

        # The data under this email key is an object, and within it,
        # you have a 'data' array.
        student_data_array = snapshot.val().get("data")

        if not student_data_array:
            print(f"No 'data' array found for email key: {email}")
            return {}

        # If you want to return a dictionary where keys are derived (e.g., index)
        # or if you just want the list of student objects:
        found_students = {}
        for i, student_record in enumerate(student_data_array):
            # You might want a unique key for each student record.
            # Using a combination of email and index, or a 'canvas_id' if unique.
            key = f"{email}_{i}" # Example key: "cba2@iti.edu_0"
            found_students[key] = student_record

        print(f"Found {len(student_data_array)} records for email key: {email}")
        print(found_students)
        return found_students

    except Exception as e:
        print(f"Error querying students by email key '{email}': {str(e)}")
        return {}

@st.cache_data(ttl=60*60*5) # 5 hours
def admin_get_student_group_emails():
    """
    Retrieves the top-level email keys (representing student groups)
    from the 'students' node in the database.

    Returns:
        list: A list of email strings (e.g., "cba2@iti,edu"), or an empty list
              if no student groups are found or an error occurs.
    """
    try:
        students_ref = db.child("students")
        students_snapshot = students_ref.get(token=st.session_state.user_token)
        print('\n\n---------------------------------database readed-------------------------\n\n', {k: v['data'][0] if v and 'data' in v else None for k, v in students_snapshot.val().items()})

        if not students_snapshot.val():
            print("No student entries found in the database")
            return []

        email_keys = []
        for student_key, _ in students_snapshot.val().items():
            email_keys.append(student_key)

        print(f"Found {len(email_keys)} student group emails.")
        print(email_keys)
        return email_keys

    except Exception as e:
        print(f"Error retrieving student group emails: {str(e)}")
        return []
    
@st.cache_data
def admin_load_students(course_email, last_updated):
    """
    Load students data from Firebase and ensure all required fields are present.
    
    Returns:
        tuple: (DataFrame with student data, filename) or (None, None) if error or no data
    """
    try:
        user_email = course_email
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

def admin_save_students(course_email, students_df):
    """
    Save students data to Firebase with proper handling of all fields.
    
    Args:
        course_email (str): Email of the course to save students to
        students_df (DataFrame): DataFrame containing student records
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        if students_df is None or students_df.empty:
            st.warning("No student data to save.")
            return False
            
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
            'fecha_inicio': None,
            'fecha_fin': None
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
            db.child("students").child(course_email).set(data, token=st.session_state.user_token)
            st.success(f"Successfully saved {len(df)} student records to {course_email}.")
            admin_set_last_updated('students', course_email)
            return True
        except Exception as firebase_error:
            st.error(f"Firebase error: {str(firebase_error)}")
            return False
            
    except Exception as e:
        st.error(f"Error saving students: {str(e)}")
        if 'df' in locals():
            st.error(f"Columns in DataFrame: {', '.join(df.columns)}")
        return False

@st.cache_data(ttl=1)
def admin_get_available_modules(user_email: str) -> list:
    """
    Retrieve and process available modules for a user.

    Args:
        user_email: The user's email (with . replaced with , for Firebase path)

    Returns:
        list: List of module options with their details, sorted by proximity to current date
    """
    try:
        # Create a fresh Firebase reference for this operation
        # Note: You should ensure 'db' is initialized before this function is called.
        modules_ref = db.child("modules").child(user_email).get(token=st.session_state.user_token)
        # print("\n\nAvailable modules for user:", modules_ref.val())
        # if 'call_count' not in st.session_state:
        #     st.session_state.call_count = 0
        # st.session_state.call_count += 1
        # print(f"\n{st.session_state.call_count} ---get_available_modules-data from firebase----\n", modules_ref.val())

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

            # --- Extract ALL relevant module data fields ---
            # Debug: Print the raw module data
            # print(f"\nRaw module data for {module_id}:", module_data)
            
            # Use .get() with a default value to avoid KeyError if a field is missing in Firebase
            start_date_str = module_data.get('fecha_inicio_1')
            end_date_str = module_data.get('fecha_fin_1')  # Check if this field exists in your database
            
            # Try different possible field names for duration and credits
            duration_weeks = 0
            if 'duracion_semanas' in module_data:
                duration_weeks = module_data['duracion_semanas']
            elif 'duration_weeks' in module_data:
                duration_weeks = module_data['duration_weeks']
                
            credits = 0
            if 'creditos' in module_data:
                credits = module_data['creditos']
            elif 'credits' in module_data:
                credits = module_data['credits']
                
            description = module_data.get('description', '')  # Try English version first
            if not description:  # Fall back to Spanish if English version doesn't exist
                description = module_data.get('descripcion', '')
                
            ciclo = module_data.get('ciclo', 1)  # Default to 1 if not specified
            
            # Debug: Print the extracted values
            print(f"Extracted values - duration: {duration_weeks}, credits: {credits}, description: {description}")

            start_date_dt = None
            if isinstance(start_date_str, str):
                try:
                    start_date_dt = datetime.datetime.fromisoformat(start_date_str)
                except (ValueError, TypeError):
                    pass # Keep start_date_dt as None if parsing fails

            # Only add the module if start_date is parsed successfully and is within cutoff
            if start_date_dt and start_date_dt >= cutoff_date:
                # print(f"\n\nAdding module {module_name} to options list...")
                module_entry = {
                    'label': f"{module_name} (Ciclo {ciclo} - Inicia: {start_date_dt.strftime('%m/%d/%Y')})",
                    'module_id': module_id,
                    'module_name': module_name, # Original name
                    'ciclo': ciclo,
                    'start_date': start_date_str, # Keep as string for this function's return, conversion happens in UI
                    'end_date': end_date_str,     # Include end_date
                    'duration_weeks': duration_weeks,
                    'credits': credits,           # Add credits
                    'description': description,   # Add description
                    'firebase_key': module_id     # This is often useful, same as module_id
                }
                module_options.append(module_entry)

        # Sort by proximity to today's date
        # Ensure 'start_date' is a string before trying fromisoformat
        module_options.sort(
            key=lambda x: abs((datetime.datetime.fromisoformat(x['start_date']) - today).days)
            if 'start_date' in x and isinstance(x['start_date'], str) and x['start_date'] else float('inf')
        )

        return module_options

    except Exception as e:
        st.error(f"Error al cargar los módulos: {str(e)}")
        return []

def save_modules_to_db(user_email: str, modules_data: list[dict]) -> bool:
    """
    Save module changes to Firebase, updating existing ones and adding new ones.
    Handles deletions by omission if the entire list is considered the source of truth.
    """
    try:
        # --- FIX: Sanitize the email to create a valid Firebase key ---
        user_email_sanitized = user_email # Example sanitization
        
        # --- CRITICAL FIX: Use update/push instead of set ---
        user_modules_ref = db.child("modules").child(user_email_sanitized)
        
        updates = {}
        for module in modules_data:
            # Check if the module has a firebase_key. A key means it's an existing record.
            # pd.notna() is important because the key could be NaN for new rows.
            firebase_key = module.get('firebase_key')

            if firebase_key and pd.notna(firebase_key):
                # --- This is an UPDATE to an existing module ---
                # We build a dictionary of updates to send in one batch
                updates[f"{firebase_key}"] = module
            else:
                # --- This is a NEW module, so we PUSH it ---
                # .push() generates the unique ID for us
                user_modules_ref.push(module, token=st.session_state.user_token)

        # Send all updates for existing records in a single, efficient call
        if updates:
            user_modules_ref.update(updates, token=st.session_state.user_token)

        # Note: This logic does not handle row DELETION from the database.
        # If a user can delete rows, you would need a more complex sync:
        # 1. Fetch all keys from Firebase.
        # 2. Get all keys from the UI DataFrame.
        # 3. For any key in Firebase but not in the UI, issue a .child(key).remove() call.

        # update_modules_in_session() might need to be called after the operation
        # or rely on the st.rerun() to reload from DB. The rerun is cleaner.
        admin_set_last_updated('modules', user_email)
        return True

    except Exception as e:
        st.error(f"Error al guardar los módulos: {str(e)}")
        return False

def load_breaks():
    """
    Loads all 'breaks' data from the Firebase Realtime Database.
    Handles cases where data is empty or not in expected dictionary format.
    """
    try:
        # Create a fresh reference to the 'breaks' child node
        breaks_ref = db.child("breaks")
        breaks_data = breaks_ref.get(token=st.session_state.user_token).val() or {} # Get data, default to empty dict if None
        
        # Ensure the retrieved data is a dictionary
        if not isinstance(breaks_data, dict):
            st.warning(f"Se esperaba un diccionario para 'breaks', pero se obtuvo: {type(breaks_data)}. Retornando diccionario vacío.")
            return {}
        return breaks_data
    except Exception as e:
        st.error(f"Error al cargar las semanas de descanso: {e}")
        return {}

def load_breaks_from_db():
    """Load breaks from Firebase and format them for date calculations."""
    try:
        breaks_ref = db.child("breaks").get(token=st.session_state.user_token)
        if not breaks_ref.val():
            return []
            
        breaks_list = []
        for break_id, break_data in breaks_ref.val().items():
            if not break_data or not isinstance(break_data, dict):
                continue
                
            try:
                start_date = datetime.datetime.strptime(break_data.get('start_date', ''), '%Y-%m-%d').date()
                duration_weeks = int(break_data.get('duration_weeks', 1))
                end_date = start_date + datetime.timedelta(days=duration_weeks * 7 - 1)
                
                breaks_list.append({
                    'name': break_data.get('name', 'Semana de Descanso'),
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                })
            except (ValueError, KeyError) as e:
                st.warning(f"Error al procesar semana de descanso {break_id}: {e}")
                continue
                
        return breaks_list
    except Exception as e:
        st.error(f"Error al cargar semanas de descanso: {e}")
        return []

# --- DATE CALCULATION LOGIC ---

def parse_breaks(breaks_data):
    """
    Convierte una lista de diccionarios de vacaciones en tuplas de fechas (inicio, fin).
    Omite entradas inválidas.
    """
    parsed = []
    for b in breaks_data:
        try:
            start = datetime.datetime.strptime(b['start_date'], '%Y-%m-%d').date()
            end = datetime.datetime.strptime(b['end_date'], '%Y-%m-%d').date()
            parsed.append((start, end))
        except (ValueError, TypeError):
            # Saltar entradas de vacaciones inválidas o incompletas
            continue
    return parsed

def adjust_date_for_breaks(current_date, breaks):
    """
    Verifica si una fecha cae dentro de un período de vacaciones.
    Si es así, retorna el próximo lunes después del final del break.
    Si no, retorna la misma fecha (ajustada a lunes si no lo es).
    """
    for b_start, b_end in breaks:
        if b_start <= current_date <= b_end:
            next_day = b_end + datetime.timedelta(days=1)
            # Snap to next Monday
            days_to_monday = (7 - next_day.weekday()) % 7
            adjusted_date = next_day + datetime.timedelta(days=days_to_monday)
            return adjusted_date

    # Si no cae en vacaciones, también ajustar al lunes más cercano si no lo es
    if current_date.weekday() != 0:
        days_to_monday = (7 - current_date.weekday()) % 7
        current_date += datetime.timedelta(days=days_to_monday)

    return current_date

def calculate_end_date(start_date, num_weeks, breaks):
    """
    Calculates the end date from a start date and a number of weeks,
    taking into account any breaks within that period.
    The `breaks` parameter is expected to be a list of (start_date, end_date) tuples.
    """
    end_date = start_date + datetime.timedelta(weeks=num_weeks)

    # print("\n\nstart_date from calculate_end_date", start_date)
    # print("\n\nnum_weeks from calculate_end_date", num_weeks)
    # print("\n\nbreaks from calculate_end_date", breaks)
    total_break_days = 0
    for b_start, b_end in breaks:
        if start_date <= b_end and end_date >= b_start:
            overlap_start = max(start_date, b_start)
            overlap_end = min(end_date, b_end)
            # Include the end date in count
            total_break_days += (overlap_end - overlap_start).days + 1  

    end_date += datetime.timedelta(days=total_break_days)
    print("\n\nend_date", end_date)
    return end_date

def row_to_clean_dict(row: pd.Series) -> dict:
    """
    • Converts NaN / None / pd.NA to "" (empty text)  
    • Converts pandas.Timestamp → python datetime.datetime  
    • Leaves every other value unchanged
    """
    clean = {}
    for k, v in row.items():
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
            clean[k] = ""
        elif isinstance(v, pd.Timestamp):
            clean[k] = v.strftime("%Y-%m-%d")  # <- convert to string
        else:
            clean[k] = v
    return clean

def save_new_module_to_db(user_email: str, module_data: dict) -> str:
    """
    Save a new module to Firebase, adding it to the modules list for the user.
    """
    try:
        user_modules_ref = db.child("modules").child(user_email)
        result = user_modules_ref.push(module_data, token=st.session_state.user_token)
        return result["name"]
    except Exception as e:
        st.error(f"Error al guardar el módulo: {str(e)}")
        return None

def transform_module_input(raw: dict) -> dict:
    return {
        "name": raw.get("Nombre Módulo", ""),
        "description": raw.get("Descripción", ""),
        "duration_weeks": raw.get("Duración", 1),
        "credits": raw.get("Orden", 0),
        "fecha_inicio_1": raw.get("Fecha Inicio", ""),
        "fecha_fin_1": raw.get("Fecha Fin", ""),
        "created_at": datetime.datetime.now().isoformat(),
        "module_id": str(uuid.uuid4()),  # unique module ID 
        "firebase_key": "",              # you can change this if dynamic
        # firebase_key will be added AFTER saving to Firebase, if needed
    }

def sync_firebase_updates(df_old: pd.DataFrame, df_new: pd.DataFrame):
    """
    Syncs changes between old and new DataFrames to Firebase:
    - Deletes removed rows
    - Updates modified rows
    - Does NOT add new rows

    Args:
        df_old (pd.DataFrame): Original DataFrame with firebase_key
        df_new (pd.DataFrame): Edited DataFrame with firebase_key
    """
    # Make sure indexes are clean
    df_old = df_old.reset_index(drop=True)
    df_new = df_new.reset_index(drop=True)

    # Drop rows without firebase_key
    df_old = df_old[df_old["firebase_key"] != ""]
    df_new = df_new[df_new["firebase_key"] != ""]

    # Find deleted rows
    old_keys = set(df_old["firebase_key"])
    new_keys = set(df_new["firebase_key"])
    deleted_keys = old_keys - new_keys

    for key in deleted_keys:
        try:
            db.child("modules").child(key).delete()
        except Exception as e:
            print(f"Error deleting {key}: {e}")

    # Find modified rows
    for key in new_keys:
        new_row = df_new[df_new["firebase_key"] == key].iloc[0]
        old_row = df_old[df_old["firebase_key"] == key].iloc[0]

        if not new_row.equals(old_row):
            try:
                clean_data = row_to_clean_dict(new_row)
                db.child("modules").child(key).update(clean_data)
            except Exception as e:
                print(f"Error updating {key}: {e}")

def update_module_to_db(course_id: str, firebase_key: str, module_data: dict):
    print("\n\n --- modules uodating to db", course_id, firebase_key, module_data)
    try:
        db.child("modules").child(course_id).child(firebase_key).update(module_data, token=st.session_state.user_token)
        admin_set_last_updated('modules', course_id)
    except Exception as e:
        st.error(f"Error al actualizar el módulo: {str(e)}")

def delete_module_from_db(course_id: str, firebase_key: str):
    try:
        db.child("modules").child(course_id).child(firebase_key).remove(token=st.session_state.user_token)
        admin_set_last_updated('modules', course_id)
    except Exception as e:
        st.error(f"Error al eliminar el módulo: {str(e)}")

def find_students(search_term: str, course_email: str = None, status: str = "in_progress") -> pd.DataFrame:
    """
    Fetches student data from Firebase, applies name/email search and status filters.

    Args:
        search_term (str): The name or email substring to search for.
        course_email (str, optional): The specific course email to filter by.
                                       Defaults to None (search all courses).
        status (str, optional): The enrollment status to filter by ("all", "in_progress", "graduated", "not_started").
                                Defaults to "all".

    Returns:
        pd.DataFrame: A DataFrame of matched students with expected columns.
    """
    try:
        students_ref = db.child("students")

        if course_email == "":
            course_email = None

        raw_students_data = []

        if course_email:
            # Fetch data for a specific course
            snapshot = students_ref.child(course_email).child("data").get(token=st.session_state.user_token)
            if snapshot.val() is not None:
                # Firebase can return dict (if a single item) or list (if multiple items)
                # Ensure we handle both cases correctly
                if isinstance(snapshot.val(), dict):
                    # If data is a dictionary where keys are student IDs/indices
                    for student_key, student_data_raw in snapshot.val().items():
                        if isinstance(student_data_raw, dict):
                            student_data_raw['course_email'] = course_email # Add course_email
                            raw_students_data.append(student_data_raw)
                elif isinstance(snapshot.val(), list):
                    # If data is a list (e.g., if pushed as an array in Firebase)
                    for student_data_raw in snapshot.val():
                        if isinstance(student_data_raw, dict):
                            student_data_raw['course_email'] = course_email # Add course_email
                            raw_students_data.append(student_data_raw)
        else:
            # Fetch data for all courses
            all_courses_snapshot = students_ref.get(token=st.session_state.user_token)
            if all_courses_snapshot.val() is not None:
                for course_node in all_courses_snapshot.each():
                    course_key = course_node.key()
                    course_data_val = course_node.val()

                    if isinstance(course_data_val, dict):
                        data_node = course_data_val.get("data", {})
                        if isinstance(data_node, dict):
                            # Students are dictionaries within "data"
                            for student_key, student_data_raw in data_node.items():
                                if isinstance(student_data_raw, dict):
                                    student_data_raw['course_email'] = course_key
                                    raw_students_data.append(student_data_raw)
                        elif isinstance(data_node, list):
                            # Students are a list within "data"
                            for student_data_raw in data_node:
                                if isinstance(student_data_raw, dict):
                                    student_data_raw['course_email'] = course_key
                                    raw_students_data.append(student_data_raw)

        # Define expected columns and their default values
        expected_columns = {
            'nombre': '',
            'email': '',
            'telefono': '',
            'modulo': '',
            'fecha_inicio': '',
            'modulo_fin_name': '',
            'fecha_fin': '',
            'course_email': ''
        }

        # Create DataFrame from raw data, ensuring all expected columns are present
        if raw_students_data:
            df = pd.DataFrame(raw_students_data)
            # Fill missing expected columns with empty strings
            for col in expected_columns:
                if col not in df.columns:
                    df[col] = expected_columns[col]
            # Ensure column order
            df = df[list(expected_columns.keys())]
        else:
            return pd.DataFrame(columns=list(expected_columns.keys()))

        # Convert date columns to datetime objects for filtering
        df['_fecha_inicio_dt'] = pd.to_datetime(df['fecha_inicio'], errors='coerce')
        df['_fecha_fin_dt'] = pd.to_datetime(df['fecha_fin'], errors='coerce')
        today_dt = pd.Timestamp(datetime.date.today())

        # --- Apply Filters ---
        filtered_df = df.copy()

        # 1. Apply search_term filter
        if search_term:
            search_term_lower = search_term.lower()
            filtered_df = filtered_df[
                filtered_df['nombre'].astype(str).str.lower().str.contains(search_term_lower) |
                filtered_df['email'].astype(str).str.lower().str.contains(search_term_lower)
            ]

        # 2. Apply status filter
        if status == "in_progress":
            filtered_df = filtered_df[
                (filtered_df['_fecha_inicio_dt'].notna()) &
                (filtered_df['_fecha_fin_dt'].notna()) &
                (filtered_df['_fecha_inicio_dt'] <= today_dt) &
                (filtered_df['_fecha_fin_dt'] >= today_dt)
            ]
        elif status == "graduated":
            filtered_df = filtered_df[
                (filtered_df['_fecha_fin_dt'].notna()) &
                (filtered_df['_fecha_fin_dt'] < today_dt)
            ]
        elif status == "not_started":
            filtered_df = filtered_df[
                (filtered_df['_fecha_inicio_dt'].notna()) &
                (filtered_df['_fecha_inicio_dt'] > today_dt)
            ]
        # No 'else' needed for "all" as it means no status filtering applied

        return filtered_df.drop(columns=['_fecha_inicio_dt', '_fecha_fin_dt'], errors='ignore')

    except Exception as e:
        # It's better to log the full traceback for debugging in production
        # import traceback
        # st.error(f"Error al buscar estudiantes: {e}\n{traceback.format_exc()}")
        st.error(f"Error al buscar estudiantes: {e}")
        return pd.DataFrame(columns=list(expected_columns.keys())) # Ensure expected_columns is defined or passed

def admin_delete_attendance_dates(dates_to_delete=None, delete_all=False, course_email=None):
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

    if dates_to_delete:
            print(f"✅ Entrando al bloque para eliminar fechas específicas: {dates_to_delete}")
            success_count = 0
            
            # Loop through the list of date STRINGS (e.g., '06/20/2025')
            for date_str_mmddyyyy in dates_to_delete:
                try:
                    # 1. PARSE the string from 'MM/DD/YYYY' format into a datetime object.
                    date_obj = datetime.datetime.strptime(date_str_mmddyyyy, '%m/%d/%Y')
                    
                    # 2. FORMAT that datetime object into the 'YYYY-MM-DD' string needed for the Firebase key.
                    date_key = date_obj.strftime('%Y-%m-%d')
                    
                    print(f"  -> Intentando eliminar la llave: {date_key}") # New debug print
                    
                    # 3. Remove the specific date node from Firebase using the correct key.
                    db.child("attendance").child(course_email).child(date_key).remove(token=st.session_state.user_token)
                    success_count += 1
                except ValueError:
                    st.warning(f"Formato de fecha inválido, omitiendo: '{date_str_mmddyyyy}'")
                except Exception as e:
                    st.warning(f"No se pudo eliminar la fecha '{date_str_mmddyyyy}': {e}")
            
            # Return True only if at least one date was successfully deleted
            return success_count > 0

    try:
        user_email_key = course_email.replace('.', ',')
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
                admin_set_last_updated('attendance', course_email)
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
                    admin_set_last_updated('attendance', course_email)
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

def admin_save_attendance(date: datetime.date, attendance_data: list, course_email: str):
    """Save attendance data to Firebase for a specific date."""
    try:
        user_email = course_email.replace('.', ',')
        date_str = date.strftime('%Y-%m-%d')
        # Ensure student names (keys in attendance_data) are safe for Firebase paths if necessary
        # For now, assuming they are simple strings.
        db.child("attendance").child(user_email).child(date_str).set(attendance_data, token=st.session_state.user_token)
        admin_set_last_updated('attendance', user_email)
        return True
    except Exception as e:
        st.error(f"Error saving attendance for {date_str}: {str(e)}")
        return False

@st.cache_data
def admin_get_attendance_dates(email: str, attendance_last_updated: str):
    """
    Get a list of all dates with saved attendance records.
    Returns a sorted list of date strings in 'YYYY-MM-DD' format.
    """
    print("\n\nattendance_last_updated", attendance_last_updated)
    print("\n\nemail", email)
    try:
        user_email = email.replace('.', ',')
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

@st.cache_data
def admin_get_attendance(email: str, attendance_last_updated: str):
    """
    Get a list of all dates with saved attendance records.
    Returns a sorted list of date strings in 'YYYY-MM-DD' format.
    """
    # print("\n\nattendance_last_updated", attendance_last_updated)
    # print("\n\nemail", email)
    try:
        user_email = email.replace('.', ',')
        docs = db.child("attendance").child(user_email).get(token=st.session_state.user_token).val() or {}
        return docs
    except Exception as e:
        st.error(f"Error loading attendance dates: {str(e)}")
        return []

@st.cache_data(ttl=60*60*2) # 2 hours 
def admin_load_attendance(course_email: str, date: datetime.date, attendance_last_updated: str) -> dict:
    """Load attendance data from Firebase for a specific date."""
    try:
        user_email = course_email.replace('.', ',')
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


# students
#     cba2@iti,edu
#         data
#             0
#                 canvas_id : "6848PER"
#                 ciclo : "1"
#                 email : "samantha.perez@iti.edu"
#                 fecha_fin : "2025-06-22"
#                 fecha_inicio : "2025-06-02"
#                 modulo : "Quickbooks I"
#                 modulo_fin_id : "-OT7wMyoKd7BTOAnpmzr"
#                 modulo_fin_name : "Quickbooks I"
#                 modulo_fin_order : 12
#                 modulo_id : "-OT7v9y4HwvBF1fScEM7"
#                 nombre : "Samantha Perez"
#                 telefono : "7866229067"
#             1
#             2
#             3
#             4
#             5
#             filename:"students.xlsx"
#             metadata timestamp: "2025-06-20T15:55:40.866010Z"
#     database@iti,edu
#         data
#             0
#             1
#             2
#                 canvas_id: "CBADS"
#                 ciclo: "1"
#                 email: "Database-estudiante2@itit.edu"
#                 fecha_inicio: "2025-06-12"
#                 modulo: "moduloDatabase"
#                 modulo_id: "-OS_541fyrIWYfFmO6tZ"
#                 nombre: "S"
#                 telefono: "876-098-9877"
#             3
