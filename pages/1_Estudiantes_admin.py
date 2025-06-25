import streamlit as st
import pandas as pd
import datetime
import time
import urllib.parse
from config import setup_page
from utils import get_available_modules, get_last_updated, set_last_updated, get_module_name_by_id
from utils_admin import admin_get_students_by_email, admin_get_student_group_emails, admin_load_students, admin_save_students, load_breaks, parse_breaks, calculate_end_date, load_breaks_from_db

def create_whatsapp_link(phone: str) -> str:
    if pd.isna(phone) or not str(phone).strip():
        return ""
    phone = ''.join(filter(str.isdigit, str(phone)))
    return f"https://wa.me/{phone}" if phone else ""

def create_teams_link(email: str) -> str:
    if pd.isna(email) or not str(email).strip() or '@' not in str(email):
        return ""
    return f"https://teams.microsoft.com/l/chat/0/0?users={email}"

# --- Initialize session state variables at the very top ---
# This ensures they exist before any part of the script tries to access them.
if 'editor_key' not in st.session_state:
    st.session_state.editor_key = 0
if 'students_df_by_course' not in st.session_state:
    st.session_state.students_df_by_course = {} # This will store DataFrames per course
if 'last_module_credit' not in st.session_state:
    st.session_state.last_module_credit = None
if 'last_module_id' not in st.session_state:
    st.session_state.last_module_id = None
if 'last_module_name' not in st.session_state:
    st.session_state.last_module_name = None

# --- End Initialize session state variables ---


# --- Login Check ---
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()
# --- End Login Check ---

# Setup page title (now that config is done and user is logged in)
setup_page("Gestión de Estudiantes por Administrador")


# --- Select Course ---
st.subheader("1. Seleccionar Curso")

# Get available courses (emails)
course_emails = admin_get_student_group_emails()

selected_course = None # Initialize selected_course before the if/else block

if course_emails:
    full_emails_for_options = course_emails.copy() # Good practice to copy if you modify original later
    course_options = {
        email: {
            'label': email.capitalize().split('@')[0], # Display part without domain
            'value': email                              # Full email with domain
        }
        for email in full_emails_for_options
    }

    selected_course = st.selectbox(
        "Seleccione un Curso para agregar a los nuevos estudiantes:",
        options=full_emails_for_options,
        format_func=lambda x: course_options[x]['label'],
        index=0,
        key="course_selector" # Added key for consistency
    )

else:
    st.warning("No se encontraron cursos disponibles.")
    selected_course = None # Ensure it's explicitly None if no courses

def get_end_date(start_date, num_weeks):
    try:
        if isinstance(start_date, str):
            start_date = datetime.datetime.fromisoformat(start_date)
        elif isinstance(start_date, datetime.date):
            start_date = datetime.datetime.combine(start_date, datetime.time.min)

        start_date = start_date.date()  # <-- línea clave para evitar el error

        break_data = load_breaks_from_db()
        break_list = parse_breaks(break_data)
        end_date = calculate_end_date(start_date, num_weeks, break_list)

        print("\n\nend_date", end_date)
        return end_date.isoformat()
    except (ValueError, TypeError) as e:
        print("❌ Error al calcular la fecha final:", e)
        return None

def get_weeks(selected_course):
    total_duration_weeks = 0
    modules = selected_course  # 'modules' is a list of dictionaries
    
    # Iterate directly over the list
    for module in modules:
        # Access the value using the dictionary key
        total_duration_weeks += module['duration_weeks']
        
    return total_duration_weeks
    
# --- Cached Student Data Loading Function ---
# This function will load student data from the database and cache it.
# It will re-run only if selected_course changes or the cache is explicitly cleared.
@st.cache_data(ttl=3600) # Cache data for 1 hour
def get_current_students_data(course_email, students_last_updated):
    """Loads student data for the given course email, optimized with caching."""
    if not course_email:
        return pd.DataFrame(), None # Return empty DataFrame if no course is selected
    # st.info(f"Cargando estudiantes para el curso: {course_email.capitalize().split('@')[0]}...")
    df, timestamp = admin_load_students(course_email, students_last_updated)
    st.success("Estudiantes cargados exitosamente." if df is not None else "Error al cargar estudiantes.")
    return df, timestamp

# --- Load current students based on selected_course ---
# This block uses the cached function and stores the result in session state.
# This ensures the database is read only once per course per session.
if selected_course:
    if selected_course not in st.session_state.students_df_by_course:
        students_last_updated = get_last_updated('students', selected_course)
        df_loaded, _ = get_current_students_data(selected_course, students_last_updated) # Use the cached function
        if df_loaded is not None:
            st.session_state.students_df_by_course[selected_course] = df_loaded
        else:
            st.session_state.students_df_by_course[selected_course] = pd.DataFrame() # Store an empty DataFrame on failure
            st.warning(f"No se pudieron cargar estudiantes para el curso: {selected_course}. Iniciando con una lista vacía.")
    else:
        df_loaded = st.session_state.students_df_by_course[selected_course]
else:
    df_loaded = pd.DataFrame() # Provide an empty DataFrame if no course is selected
    st.info("Por favor, seleccione un curso para cargar los estudiantes.")

# print("\nLoaded df_loaded (from DB/Session State):\n", df_loaded)
# print("\nSession State (students_df_by_course):\n", st.session_state.students_df_by_course)


# --- Select Module ---
if selected_course: # Only show module selection if a course is selected
    st.divider()
    st.subheader("2. Seleccionar Módulo")

    try:
        modules_last_updated = get_last_updated('modules', selected_course)
        # st.info(f"Módulos actualizados el: {modules_last_updated}")
        module_options = get_available_modules(selected_course, modules_last_updated)
        st.session_state.module_data = module_options
        # print("\n\nmodule_data", st.session_state.module_data)
        # print("\n\nmodule_options", module_options)

        if module_options:
            selected_module = st.selectbox(
                "Seleccione un módulo para agregar a los nuevos estudiantes:",
                options=module_options,
                format_func=lambda x: x['label'],
                index=0,
                key="module_selector" # Added key for consistency
            )

            # Store selected module in session state for later use
            if selected_module: # Ensure a module is actually selected
                st.session_state.selected_module = selected_module
                st.session_state.selected_module_id = selected_module['module_id']
                st.session_state.selected_ciclo = selected_module['ciclo']

                # Get previous module id and order based on the credit value
                prev_module_id = None
                if module_options:
                    sorted_modules = sorted(module_options, key=lambda x: x['credits'])
                    current_module_idx = sorted_modules.index(selected_module)
                    if current_module_idx > 0:
                        prev_module_id = sorted_modules[current_module_idx - 1]['module_id']
                        prev_module_credit = sorted_modules[current_module_idx - 1]['credits']
                        prev_module_name = sorted_modules[current_module_idx - 1]['module_name']
                    else:
                        last_module = sorted_modules[-1]
                        prev_module_id = last_module['module_id']
                        prev_module_credit = last_module['credits']
                        prev_module_name = last_module['module_name']

                st.session_state.last_module_credit = prev_module_credit
                st.session_state.last_module_id = prev_module_id
                st.session_state.last_module_name = prev_module_name



        else:
            st.info("No hay módulos disponibles. Por favor, agregue módulos en la sección de Módulos.")

    except Exception as e:
        st.error(f"Error al cargar los módulos: {str(e)}")

st.divider()
st.subheader("3. Agregar Estudiantes")

# Create tabs for different input methods
tab1, tab2 = st.tabs(["📤 Subir Archivo", "✏️ Ingresar Texto"])

with tab1:
    st.subheader("Cargar desde Archivo")
    uploaded_file = st.file_uploader(
        "Seleccione un archivo CSV o Excel con los estudiantes",
        type=['csv', 'xlsx', 'xls'],
        key="file_uploader"
    )

with tab2:
    st.subheader("Ingresar Datos Manualmente")
    st.write("Ingrese los datos de los estudiantes en el siguiente formato:")
    st.code("Nombre, Email, Canvas ID, Telefono", language="text")

    students_text_area = st.text_area(
        "Ingrese un estudiante por línea. Solo el nombre es obligatorio.",
        height=150,
        key="text_area_input",
        placeholder="Ejemplo:\nJuan Pérez, juan@email.com,8780GOM , 786-123-4567\nAna García, ana@email.com, 9879PER, 786-123-4568\n..."
    )
    submit_add_students_text = st.button("Agregar Estudiantes")

if uploaded_file is not None:
    try:
        if selected_course is None:
            st.warning("Por favor, seleccione un curso antes de subir estudiantes.")
            st.stop()

        # Read the uploaded file
        if uploaded_file.name.endswith('.csv'):
            df_upload = pd.read_csv(uploaded_file)
        else:  # Excel file
            df_upload = pd.read_excel(uploaded_file)

        # Normalize column names and handle case sensitivity
        df_upload.columns = df_upload.columns.str.lower().str.strip()

        # Ensure required columns exist
        required_columns = {'nombre'}
        missing_columns = required_columns - set(df_upload.columns)

        if missing_columns:
            st.error(f"Error: El archivo subido no contiene las columnas requeridas: {', '.join(missing_columns)}. "
                     f"Por favor asegúrese de que su archivo incluya al menos la columna: nombre")
        else:
            # Process required fields
            df_upload['nombre'] = df_upload['nombre'].astype(str).str.strip()

            # Initialize optional fields if they don't exist
            optional_fields = {
                'email': '',
                'canvas_id': '',
                'telefono': ''
            }

            for field, default_value in optional_fields.items():
                if field not in df_upload.columns:
                    df_upload[field] = default_value
                else:
                    # Clean up the data
                    df_upload[field] = df_upload[field].fillna('').astype(str).str.strip()

            # Get the selected module's details if available
            module_info = {}
            if 'selected_module' in st.session_state and 'selected_module_id' in st.session_state:
                module_info = {
                    'fecha_inicio': st.session_state.selected_module.get('start_date'),
                    'fecha_fin': st.session_state.selected_module.get('end_date'),
                    'modulo': st.session_state.selected_module.get('module_name'),
                    'ciclo': st.session_state.selected_module.get('ciclo'),
                    'firebase_key': st.session_state.selected_module_id
                }

                if module_info['fecha_inicio'] and module_info['fecha_fin'] and isinstance(module_info['fecha_inicio'], str) and isinstance(module_info['fecha_fin'], str):
                    try:
                        # Convert to datetime and format consistently
                        module_info['fecha_inicio'] = datetime.datetime.fromisoformat(module_info['fecha_inicio']).strftime('%Y-%m-%d')
                        module_info['fecha_fin'] = datetime.datetime.fromisoformat(module_info['fecha_fin']).strftime('%Y-%m-%d')
                        # Add module info to all uploaded students
                        df_upload['fecha_inicio'] = module_info['fecha_inicio']
                        df_upload['fecha_fin'] = module_info['fecha_fin']
                        df_upload['modulo'] = module_info['modulo']
                        df_upload['ciclo'] = module_info['ciclo']
                        df_upload['modulo_id'] = module_info['firebase_key']
                    except (ValueError, TypeError):
                        module_info = {}  # Reset if date conversion fails

            st.subheader("Vista Previa del Archivo Subido")
            st.write(f"Total de estudiantes en el archivo: {len(df_upload)}")
            if module_info.get('fecha_inicio'):
                st.info(f"Se asignará el módulo '{module_info['modulo']}' con fecha de inicio: {module_info['fecha_inicio']}")
            st.dataframe(df_upload)

            if st.button("Guardar Estudiantes Subidos (reemplaza la lista existente)", key="save_uploaded_students_btn"):
                if admin_save_students(selected_course, df_upload): # Pass selected_course
                    st.success("¡Datos de estudiantes del archivo guardados exitosamente! La lista existente fue reemplazada.")
                    st.session_state.students_df_by_course[selected_course] = df_upload.copy() # Update session state copy
                    st.session_state.editor_key += 1 # Increment key to force data_editor refresh
                    get_current_students_data.clear() # Clear the cache for the loading function
                    time.sleep(1)
                    st.rerun()

    except Exception as e:
        st.error(f"Error procesando el archivo: {str(e)}")
        st.error("Por favor, asegúrese de que el archivo no esté abierto en otro programa e inténtelo de nuevo.")

# --- Add Multiple Students via Text Area ---
if 'text_area_input' in st.session_state and st.session_state.text_area_input and submit_add_students_text:
    if selected_course is None:
        st.warning("Por favor, seleccione un curso antes de agregar estudiantes.")
        st.stop()
        
    if not students_text_area.strip():
        st.warning("El área de texto está vacía. Por favor, ingrese nombres de estudiantes.")
    else:
        lines = students_text_area.strip().split('\n')
        potential_new_entries = [line.strip() for line in lines if line.strip()] # Renamed for clarity

        if not potential_new_entries:
            st.warning("No se encontraron nombres de estudiantes válidos en el área de texto después del procesamiento.")
        else:
            # Get the current students for the selected course from session state
            # This is already ensured by the loading block above
            current_students_df = st.session_state.students_df_by_course[selected_course].copy()
            # print("\nCurrent students df:\n", current_students_df)
            # Ensure all columns exist in current_students_df before operations
            all_expected_cols = ['nombre', 'email', 'canvas_id', 'telefono', 'whatsapp', 'teams', 'fecha_inicio', 'fecha_fin', 'modulo', 'ciclo', 'modulo_id']
            for col in all_expected_cols:
                if col not in current_students_df.columns:
                    current_students_df[col] = '' # Add missing columns as empty strings

            existing_normalized_names = set(current_students_df['nombre'].astype(str).str.lower().str.strip())

            added_count = 0
            skipped_names = []
            students_to_add_list = []

            unique_potential_new_entries_set = set() # To track unique entries in this input session
            unique_potential_new_names_list = [] # To maintain order and process unique entries

            for entry in potential_new_entries:
                parts = [p.strip() for p in entry.split(',', 3)]
                name_candidate = parts[0] if len(parts) > 0 else ''
                normalized_name_candidate = name_candidate.lower().strip()

                if not name_candidate:
                    continue # Skip empty names

                if normalized_name_candidate not in unique_potential_new_entries_set:
                    unique_potential_new_names_list.append(entry)
                    unique_potential_new_entries_set.add(normalized_name_candidate)
                else:
                    # Mark as skipped if duplicate within this input session
                    if name_candidate not in skipped_names: # Avoid adding same skipped name multiple times
                        skipped_names.append(name_candidate)

            # Get the selected module's details if available
            module_info = {}
            if 'selected_module' in st.session_state and 'selected_module_id' in st.session_state:
                module_info = {
                    'fecha_inicio': st.session_state.selected_module.get('start_date'),
                    'fecha_fin': st.session_state.selected_module.get('end_date'),
                    'modulo': get_module_name_by_id(selected_course, st.session_state.selected_module_id) or '',
                    'ciclo': st.session_state.selected_module.get('ciclo', ''),
                    'modulo_id': st.session_state.selected_module_id,
                    'duration_weeks': st.session_state.selected_module.get('duration_weeks')
                }

                if module_info['fecha_inicio'] and isinstance(module_info['fecha_inicio'], str):
                    try:
                        module_info['fecha_inicio'] = datetime.datetime.fromisoformat(module_info['fecha_inicio']).strftime('%Y-%m-%d')
                   

                        # total_duration_weeks = 0
                        # max_order = 0
                        # modules = st.session_state.modules_df_by_course[selected_course]
                        # for index, row in modules.iterrows():
                        #     total_duration_weeks += row['duration_weeks']
                        #     max_order = max(row['credits'], max_order)
                        
                        # module_info['total_duration_weeks'] = total_duration_weeks
                        # module_info['max_order'] = max_order
                
                        # print("\n\nmodule_info", st.session_state.students_df_by_course[selected_course])
                        # print("\n\nmodule_info", st.session_state.module_data)
                        num_weeks = get_weeks(st.session_state.module_data)
                        # print("\n\nnum_weeks", num_weeks)
                        module_info['fecha_fin'] = get_end_date(module_info['fecha_inicio'], num_weeks)
                        # print("\n\nmodule_info", module_info['fecha_fin'])
                    except (ValueError, TypeError):
                        module_info = {} # Reset if date conversion fails

            for student_entry in unique_potential_new_names_list:
                parts = [p.strip() for p in student_entry.split(',', 3)]
                name = parts[0] if len(parts) > 0 else ''
                email = parts[1] if len(parts) > 1 else ''
                canvas_id = parts[2] if len(parts) > 2 else ''
                telefono = parts[3] if len(parts) > 3 else ''

                normalized_name = name.lower().strip()

                if normalized_name not in existing_normalized_names:
                    student_data = {
                        'nombre': name,
                        'email': email,
                        'canvas_id': canvas_id,
                        'telefono': telefono,
                        'whatsapp': create_whatsapp_link(telefono),
                        'teams': create_teams_link(email),
                        'fecha_inicio': module_info.get('fecha_inicio', ''),
                        'fecha_fin': module_info.get('fecha_fin', ''),
                        'modulo': module_info.get('modulo', ''),
                        'ciclo': module_info.get('ciclo', ''),
                        'modulo_id': module_info.get('modulo_id', ''),
                        'modulo_fin_order': st.session_state.last_module_credit,
                        'modulo_fin_id': st.session_state.last_module_id,
                        'modulo_fin_name': st.session_state.last_module_name
                    }
                    students_to_add_list.append(student_data)
                    added_count += 1
                else:
                    if name not in skipped_names: # Ensure it's not already added from unique_potential_new_entries_set
                        skipped_names.append(name)

            if not students_to_add_list:
                st.info("No hay nuevos estudiantes para agregar. Todos los nombres proporcionados ya existen o eran duplicados en la entrada.")
                if skipped_names:
                    st.caption(f"Nombres omitidos (ya existen o duplicados): {', '.join(skipped_names)}")
            else:
                students_to_add_list_copy = [student_data.copy() for student_data in students_to_add_list]
                for student_data in students_to_add_list_copy:
                    student_data.pop('whatsapp', None)
                    student_data.pop('teams', None)

                new_students_df = pd.DataFrame(students_to_add_list_copy)
                updated_students_df = pd.concat([current_students_df, new_students_df], ignore_index=True)

                # print("\n\nupdated_students_df", updated_students_df)
                if admin_save_students(selected_course, updated_students_df): # Pass selected_course
                    st.success(f"¡{added_count} estudiante(s) agregado(s) exitosamente!")
                    if skipped_names:
                        st.caption(f"Nombres omitidos (ya existen o duplicados en la entrada): {', '.join(skipped_names)}")
                    st.session_state.students_df_by_course[selected_course] = updated_students_df.copy() # Update session state copy
                    st.session_state.editor_key += 1 # Increment key to force data_editor refresh
                    get_current_students_data.clear() # Clear the cache for the loading function
                    st.rerun()
                else:
                    st.error("Error al agregar estudiantes desde el área de texto.")


# ---- Section Students Display and Management ---

if df_loaded is not None and not df_loaded.empty:
    st.subheader(f"Total de Estudiantes Registrados: {len(df_loaded)}")
    st.divider()

st.subheader(f"Estudiantes Actuales en el curso {selected_course.capitalize().split('@')[0] if selected_course else 'No Seleccionado'} (Total: {len(df_loaded) if df_loaded is not None else 0})")

if df_loaded is not None and not df_loaded.empty:
    if 'nombre' not in df_loaded.columns:
        st.error("Los datos de los estudiantes no tienen la columna 'nombre', que es obligatoria.")
    else:
        # Make a copy of the dataframe for editing and display
        df_display = df_loaded.copy()

        # Ensure necessary columns for display/editing exist
        cols_to_ensure = ['Eliminar', 'nombre', 'email', 'canvas_id', 'telefono',
                          'whatsapp', 'teams', 'fecha_inicio', 'fecha_fin', 'modulo', 'ciclo', 'modulo_id', 'modulo_fin_order', 'modulo_fin_id', 'modulo_fin_name']
        for col in cols_to_ensure:
            if col not in df_display.columns:
                df_display[col] = '' # Initialize missing columns with empty strings

        # Set 'Eliminar' column (checkbox) - must be first for checkbox to appear on left
        if 'Eliminar' not in df_display.columns:
            df_display.insert(0, 'Eliminar', False)

        # Update module names using modulo_id
        for idx, row in df_display.iterrows():
            if pd.notna(row.get('modulo_id')) and row['modulo_id']:
                module_name = get_module_name_by_id(selected_course, str(row['modulo_id']))
                # print("\n module name returned", module_name) # Diagnostic print, can remove
                if module_name:
                    df_display.at[idx, 'modulo'] = module_name

        # Generate links (apply to the display DataFrame)
        df_display['whatsapp'] = df_display['telefono'].apply(create_whatsapp_link)
        df_display['teams'] = df_display['email'].apply(create_teams_link)

        # Define all columns that should be displayed in the editor
        display_columns = [
            'Eliminar', 'nombre', 'email', 'canvas_id', 'telefono',
            'whatsapp', 'teams', 'modulo', 'fecha_inicio', 'modulo_fin_name', 'fecha_fin', 'modulo_fin_order', 'modulo_fin_id',
        ]

        # Create the `editable_df` with only the columns intended for `st.data_editor`
        editable_df = df_display[display_columns].copy()

        # Define column configurations
        column_config = {
            "Eliminar": st.column_config.CheckboxColumn(
                "Borrar",
                help="Seleccione estudiantes para eliminar",
                default=False,
                width="small",
                pinned=True # This makes sure the checkbox column is always visible
            ),
            "nombre": st.column_config.TextColumn(
                "Nombre del Estudiante",
                help="Nombre completo del estudiante",
                required=True,
                width="medium"
            ),
            "email": st.column_config.TextColumn(
                "Correo Electrónico",
                help="Correo electrónico del estudiante",
                width="medium"
            ),
            "canvas_id": st.column_config.TextColumn(
                "ID de Canvas",
                help="ID del estudiante en Canvas",
                width="small"
            ),
            "telefono": st.column_config.TextColumn(
                "Teléfono",
                help="Número de teléfono principal",
                width="small"
            ),
            "whatsapp": st.column_config.LinkColumn(
                "WhatsApp",
                help="Contactar por WhatsApp",
                width="small",
                display_text="💬",
                disabled=True
            ),
            "teams": st.column_config.LinkColumn(
                "Teams",
                help="Contactar por Teams",
                width="small",
                display_text="💻",
                disabled=True
            ),
            "modulo": st.column_config.TextColumn(
                "Módulo (Inicio)",
                help="Módulo actual del estudiante",
                disabled=True
            ),
            "fecha_inicio": st.column_config.DateColumn(
                "Fecha de Inicio",
                help="Fecha de inicio en el módulo",
                format="MM/DD/YYYY",
                disabled=True
            ),
            "fecha_fin": st.column_config.DateColumn(
                "Fecha de Fin",
                help="Fecha de fin en el módulo",
                format="MM/DD/YYYY",
                disabled=True
            ),
            "modulo_fin_name": st.column_config.TextColumn(
                "Módulo (Fin)",
                help="Módulo final del estudiante",
                disabled=True
            ),
            "modulo_fin_id": None,
            "modulo_fin_order": None,
            "ciclo": None, # Explicitly mark as hidden if not in display_columns
            "modulo_id": None # Explicitly mark as hidden if not in display_columns
        }

        # Only include column configurations for columns present in `editable_df`
        actual_column_config = {k: v for k, v in column_config.items() if k in editable_df.columns}

        # Display the editable table
        edited_df = st.data_editor(
            editable_df,
            column_config=actual_column_config,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"students_editor_{st.session_state.editor_key}" # Use the editor_key to force refresh
        )

        # --- IMPORTANT: Ensure 'Eliminar' column is treated as boolean for reliable button state ---
        if 'Eliminar' in edited_df.columns:
            edited_df['Eliminar'] = edited_df['Eliminar'].astype(bool)
        # ------------------------------------------------------------------------------------------

        # --- Save Changes Button (for edits made directly in the table) ---
        if st.button("💾 Guardar Cambios", key="save_changes_btn"):
            # Prepare df_to_save based on df_loaded (the original data)
            # We will merge changes from edited_df into df_loaded (the source of truth)
            df_to_save = df_loaded.copy()

            # Identify which rows/columns have changed (excluding generated/hidden columns)
            # The columns that the user can actually edit in the table are:
            # 'nombre', 'email', 'canvas_id', 'telefono'
            user_editable_cols = ['nombre', 'email', 'canvas_id', 'telefono']

            changes_detected = False
            # Iterate through the original DataFrame's indices to match with edited_df
            for i, original_row in df_loaded.iterrows():
                # Get the corresponding row from edited_df (assuming row order is preserved by data_editor)
                if i < len(edited_df): # Ensure index exists in edited_df
                    edited_row = edited_df.loc[i] # Access by label if original index used for editable_df was simple numerical range

                    for col in user_editable_cols:
                        original_value = str(original_row.get(col, '')).strip()
                        edited_value = str(edited_row.get(col, '')).strip()

                        if original_value != edited_value:
                            df_to_save.at[i, col] = edited_value # Apply change to the copy
                            changes_detected = True

            if changes_detected:
                if admin_save_students(selected_course, df_to_save): # Pass selected_course
                    st.success("¡Cambios guardados exitosamente!")
                    st.session_state.students_df_by_course[selected_course] = df_to_save.copy() # Update session state copy
                    st.session_state.editor_key += 1 # Increment key to force data_editor refresh
                    get_current_students_data.clear() # Clear the cache for the loading function
                    st.rerun() # Force a full rerun to reflect changes
                else:
                    st.error("Error al guardar los cambios. Intente nuevamente.")
            else:
                st.info("No se detectaron cambios para guardar.")

        # --- Delete Students Button (Always Visible, Disabled when no selection) ---
        students_selected_for_deletion = edited_df[edited_df['Eliminar'] == True]
        delete_button_disabled = students_selected_for_deletion.empty # True if no students are selected

        # The button is now always present, but its 'disabled' state changes based on selection
        if st.button("🗑️ Eliminar Estudiantes Seleccionados", type="primary", disabled=delete_button_disabled, key="delete_students_btn"):
            if not students_selected_for_deletion.empty: # Double-check the condition inside the button press
                names_to_delete = students_selected_for_deletion['nombre'].tolist()

                # Get the current students data from session state as the base for deletion
                current_students_df_from_session = st.session_state.students_df_by_course[selected_course].copy()

                normalized_names_to_delete = {str(name).lower().strip() for name in names_to_delete}

                students_to_keep_df = current_students_df_from_session[
                    ~current_students_df_from_session['nombre'].astype(str).str.lower().str.strip().isin(normalized_names_to_delete)
                ]

                if admin_save_students(selected_course, students_to_keep_df): # Pass selected_course
                    st.success(f"¡{len(names_to_delete)} estudiante(s) eliminado(s) exitosamente!")
                    st.session_state.students_df_by_course[selected_course] = students_to_keep_df.copy() # Update session state copy
                    st.session_state.editor_key += 1 # Increment key to force data_editor refresh
                    get_current_students_data.clear() # Clear the cache for the loading function
                    st.rerun() # Force a full rerun to reflect changes
                else:
                    st.error("Error al guardar los cambios después de intentar eliminar estudiantes.")
            else:
                st.warning("Por favor, seleccione al menos un estudiante para eliminar.") # This message is unlikely to be seen now as button is disabled
        # Removed the `elif any(edited_df['Eliminar']): pass` as it's redundant with the `disabled` logic

        # --- Download CSV Button ---
        expected_fields = ["nombre", "email", "canvas_id", "telefono"]
        filtered_df = edited_df[expected_fields]
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar CSV",
            data=csv,
            file_name="estudiantes.csv",
            mime='text/csv'
        )

elif df_loaded is not None and df_loaded.empty:
    st.info("La lista de estudiantes está actualmente vacía. Suba un archivo para agregar estudiantes.")
else: # This else branch will trigger if df_loaded is None (e.g. no course selected initially)
    st.info("No se encontraron datos de estudiantes o falló la carga. Por favor, suba un archivo para comenzar.")