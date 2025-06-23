import streamlit as st
import pandas as pd
import datetime
import urllib.parse
from config import setup_page
from utils import save_students, load_students, get_available_modules, get_last_updated, set_last_updated, get_module_name_by_id

def create_whatsapp_link(phone: str) -> str:
    if pd.isna(phone) or not str(phone).strip():
        return ""
    phone = ''.join(filter(str.isdigit, str(phone)))
    return f"https://wa.me/{phone}" if phone else ""

def create_teams_link(email: str) -> str:
    if pd.isna(email) or not str(email).strip() or '@' not in str(email):
        return ""
    return f"https://teams.microsoft.com/l/chat/0/0?users={email}"

# --- Login Check ---
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop() 
# --- End Login Check ---

# Setup page title (now that config is done and user is logged in)
setup_page("Gestión de Estudiantes")

# Load current students to display count
students_last_updated = get_last_updated('students')
df_loaded, _ = load_students(students_last_updated)

if df_loaded is not None and not df_loaded.empty:
    st.subheader(f"Total de Estudiantes Registrados: {len(df_loaded)}")
    st.divider()

# --- Select Module ---
st.subheader("1. Seleccionar Módulo")

try:
    user_email = st.session_state.get('email', '').replace('.', ',')
    modules_last_updated = get_last_updated('modules', user_email)
    module_options = get_available_modules(user_email, modules_last_updated)
    
    if module_options:
        selected_module = st.selectbox(
            "Seleccione un módulo para agregar a los nuevos estudiantes:",
            options=module_options,
            format_func=lambda x: x['label'],
            index=0
        )
        
        # Store selected module in session state for later use
        if selected_module:
            st.session_state.selected_module = selected_module
            st.session_state.selected_module_id = selected_module['module_id']
            st.session_state.selected_ciclo = selected_module['ciclo']
    else:
        st.info("No hay módulos disponibles. Por favor, agregue módulos en la sección de Módulos.")
        
except Exception as e:
    st.error(f"Error al cargar los módulos: {str(e)}")

st.divider()
st.subheader("2. Agregar Estudiantes")

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
                    'modulo': st.session_state.selected_module.get('module_name'),
                    'ciclo': st.session_state.selected_module.get('ciclo'),
                    'firebase_key': st.session_state.selected_module_id
                }
                
                if module_info['fecha_inicio'] and isinstance(module_info['fecha_inicio'], str):
                    try:
                        # Convert to datetime and format consistently
                        module_info['fecha_inicio'] = datetime.datetime.fromisoformat(module_info['fecha_inicio']).strftime('%Y-%m-%d')
                        # Add module info to all uploaded students
                        df_upload['fecha_inicio'] = module_info['fecha_inicio']
                        df_upload['modulo'] = module_info['modulo']
                        df_upload['ciclo'] = module_info['ciclo']
                        df_upload['modulo_id'] = module_info['firebase_key']
                    except (ValueError, TypeError):
                        module_info = {}  # Reset if date conversion fails
            
            st.subheader("Vista Previa del Archivo Subido")
            st.write(f"Total de estudiantes en el archivo: {len(df_upload)}")
            if module_info.get('fecha_inicio'):
                st.info(f"Se asignará el módulo '{module_info['modulo']}' (Ciclo {module_info['ciclo']}) con fecha de inicio: {module_info['fecha_inicio']}")
            st.dataframe(df_upload)
            
            if st.button("Guardar Estudiantes Subidos (reemplaza la lista existente)"):
                if save_students(df_upload):
                    st.success("¡Datos de estudiantes del archivo guardados exitosamente! La lista existente fue reemplazada.")
                    set_last_updated('students')
                    st.rerun()
    
    except Exception as e:
        st.error(f"Error procesando el archivo: {str(e)}")
        st.error("Por favor, asegúrese de que el archivo no esté abierto en otro programa e inténtelo de nuevo.")

# --- Add Multiple Students via Text Area ---
if 'text_area_input' in st.session_state and st.session_state.text_area_input and submit_add_students_text:
    if not students_text_area.strip():
        st.warning("El área de texto está vacía. Por favor, ingrese nombres de estudiantes.")
    else:
        lines = students_text_area.strip().split('\n')
        potential_new_names = [line.strip() for line in lines if line.strip()]
        
        if not potential_new_names:
            st.warning("No se encontraron nombres de estudiantes válidos en el área de texto después del procesamiento.")
        else:
            current_students_df = df_loaded
            if current_students_df is None:
                # Initialize with all required and optional columns
                current_students_df = pd.DataFrame(columns=[
                    'nombre', 'email', 'canvas_id', 'telefono', 
                    'whatsapp', 'teams', 'fecha_inicio', 'modulo', 'ciclo', 'modulo_id'
                ])
                
                # Ensure all columns exist with proper types
                column_types = {
                    'nombre': str,
                    'email': str,
                    'canvas_id': str,
                    'telefono': str,
                    'fecha_inicio': 'datetime64[ns]',
                    'modulo': str,
                    'ciclo': str,
                    'modulo_id': str
                }
                
                for col, dtype in column_types.items():
                    if col not in current_students_df.columns:
                        if dtype == str:
                            current_students_df[col] = ''
                        else:
                            current_students_df[col] = pd.Series(dtype=dtype)
                    else:
                        current_students_df[col] = current_students_df[col].astype(dtype) if dtype != str else current_students_df[col].fillna('').astype(str)

            existing_normalized_names = set(current_students_df['nombre'].str.lower().str.strip())
            
            added_count = 0
            skipped_names = []
            students_to_add_list = []
            
            unique_potential_new_names = []
            seen_in_input = set()
            for name in potential_new_names:
                normalized_name = name.lower().strip()
                if normalized_name not in seen_in_input:
                    unique_potential_new_names.append(name)
                    seen_in_input.add(normalized_name)
            
            # Get the selected module's details if available
            module_info = {}
            if 'selected_module' in st.session_state and 'selected_module_id' in st.session_state:
                module_info = {
                    'fecha_inicio': st.session_state.selected_module.get('start_date'),
                    'modulo': get_module_name_by_id(user_email, st.session_state.selected_module_id) or '',
                    'ciclo': st.session_state.selected_module.get('ciclo', ''),
                    'modulo_id': st.session_state.selected_module_id  # Store the Firebase key as modulo_id
                }
                
                if module_info['fecha_inicio'] and isinstance(module_info['fecha_inicio'], str):
                    try:
                        # Convert to datetime and format consistently
                        module_info['fecha_inicio'] = datetime.datetime.fromisoformat(module_info['fecha_inicio']).strftime('%Y-%m-%d')
                    except (ValueError, TypeError):
                        module_info = {}  # Reset if date conversion fails

            for student_entry in unique_potential_new_names:
                # Split the line into components (name, email, phone, canvas_id)
                parts = [p.strip() for p in student_entry.split(',', 3)]
                name = parts[0] if len(parts) > 0 else ''
                email = parts[1] if len(parts) > 1 else ''
                canvas_id = parts[2] if len(parts) > 2 else ''
                telefono = parts[3] if len(parts) > 3 else ''
                
                if not name:  # Skip empty names
                    continue
                    
                normalized_name = name.lower().strip()
                
                if normalized_name not in existing_normalized_names:
                    student_data = {
                        'nombre': name,
                        'email': email,
                        'canvas_id': canvas_id,
                        'telefono': telefono
                    }
                    
                    if module_info:
                        student_data.update({
                            'fecha_inicio': module_info.get('fecha_inicio', ''),
                            'modulo': module_info.get('modulo', ''),
                            'ciclo': module_info.get('ciclo', ''),
                            'modulo_id': module_info.get('modulo_id', '')  # Use modulo_id consistently
                        })
                        
                    students_to_add_list.append(student_data)
                    added_count += 1
                else:
                    skipped_names.append(name)
            
            if not students_to_add_list:
                st.info("No hay nuevos estudiantes para agregar. Todos los nombres proporcionados ya existen o eran duplicados en la entrada.")
                if skipped_names:
                    st.caption(f"Nombres omitidos (ya existen o duplicados): {', '.join(skipped_names)}")
            else:
                new_students_df = pd.DataFrame(students_to_add_list)
                updated_students_df = pd.concat([current_students_df, new_students_df], ignore_index=True)
                
                if save_students(updated_students_df):
                    set_last_updated('students')
                    st.success(f"¡{added_count} estudiante(s) agregado(s) exitosamente!")
                    if skipped_names:
                        st.caption(f"Nombres omitidos (ya existen o duplicados en la entrada): {', '.join(skipped_names)}")
                    st.rerun()
                else:
                    st.error("Error al agregar estudiantes desde el área de texto.")

# Rest of the file remains the same...
st.divider()

st.subheader(f"Estudiantes Actuales (Total: {len(df_loaded) if df_loaded is not None else 0})")

if df_loaded is not None and not df_loaded.empty:
    if 'nombre' not in df_loaded.columns:
        st.error("Los datos de los estudiantes no tienen la columna 'nombre', que es obligatoria.")
    else:
        # Make a copy of the dataframe for editing
        df_display = df_loaded.copy()
        
        # Ensure modulo_id column exists
        if 'modulo_id' not in df_display.columns:
            df_display['modulo_id'] = ''
            
        # Ensure all required columns exist
        for col in ['modulo', 'whatsapp', 'teams']:
            if col not in df_display.columns:
                df_display[col] = ''
        
        # Update module names using modulo_id
        for idx, row in df_display.iterrows():
            if pd.notna(row.get('modulo_id')) and row['modulo_id']:
                module_name = get_module_name_by_id(user_email, str(row['modulo_id']))
                print("\n module name returned", module_name)
                if module_name:
                    df_display.at[idx, 'modulo'] = module_name
        
        if 'Eliminar' not in df_display.columns:
            df_display.insert(0, 'Eliminar', False)
            
        # Define column order with all possible columns (excluding hidden ones)
        all_columns = ['Eliminar', 'nombre', 'email', 'canvas_id', 'telefono', 
                     'whatsapp', 'teams', 'fecha_inicio', 'modulo']
        
        # Ensure all columns exist in the DataFrame
        for col in all_columns:
            if col not in df_display.columns:
                df_display[col] = ''
                
        # Define hidden columns
        hidden_columns = ['ciclo', 'modulo_id']
        
        # Create column order, ensuring all requested columns are included
        column_order = [col for col in all_columns if col not in hidden_columns]
        
        # Make a copy of the dataframe for editing
        editable_df = df_display[column_order].copy()
        
        # Generate links
        if 'telefono' in editable_df.columns:
            editable_df['whatsapp'] = editable_df['telefono'].apply(create_whatsapp_link)
        if 'email' in editable_df.columns:
            editable_df['teams'] = editable_df['email'].apply(create_teams_link)
        
        # Define column configurations
        column_config = {
            "Eliminar": st.column_config.CheckboxColumn(
                "Borrar",
                help="Seleccione estudiantes para eliminar",
                default=False,
                width="small",
                required=True,
                pinned=True
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
                display_text="💬"
            ),
            "teams": st.column_config.LinkColumn(
                "Teams",
                help="Contactar por Teams",
                width="small",
                display_text="💻"
            ),
            "modulo": st.column_config.TextColumn(
                "Módulo",
                help="Módulo actual del estudiante",
                disabled=True,
                width="small"
            ),
            # Hidden columns are not included in the column_order list
            "modulo_id": None,
            "fecha_inicio": st.column_config.DateColumn(
                "Fecha de Inicio",
                help="Fecha de inicio en el módulo",
                format="MM/DD/YYYY",
                disabled=True,
                width="small"
            ),
            # Hidden columns are not included in the column_order list
            "ciclo": None
        }
        
        # Only include columns that exist in the dataframe
        column_config = {k: v for k, v in column_config.items() if k in df_display.columns}
        
        # Display the editable table with all fields
        edited_df = st.data_editor(
            editable_df,
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"students_editor_{st.session_state.get('editor_key', 0)}"
        )
        
        # Add save button
        if st.button("💾 Guardar Cambios", key="save_changes_btn"):
            # Check if there are any changes
            if not edited_df['nombre'].equals(editable_df['nombre']):
                # Create a copy of the original dataframe to modify
                updated_df = df_loaded.copy()
                # Update only the names that have changed
                name_changes = edited_df[edited_df['nombre'] != editable_df['nombre']]
                
                # Apply changes to the original dataframe
                for idx, row in name_changes.iterrows():
                    original_idx = df_loaded.index[idx]
                    updated_df.at[original_idx, 'nombre'] = row['nombre']
                
                # Save the updated dataframe
                if save_students(updated_df):
                    set_last_updated('students')
                    st.success("¡Cambios guardados exitosamente!")
                    # Add a button to refresh the page to see changes
                    if st.button("Actualizar página"):
                        st.rerun()
                else:
                    st.error("Error al guardar los cambios. Intente nuevamente.")
            else:
                st.info("No se detectaron cambios para guardar.")
                
        students_selected_for_deletion = edited_df[edited_df['Eliminar'] == True]

        if not students_selected_for_deletion.empty:
            if st.button("Eliminar Estudiantes Seleccionados", type="primary"):
                names_to_delete = students_selected_for_deletion['nombre'].tolist()
                
                current_students_df_from_db = df_loaded
                if current_students_df_from_db is None:
                    st.error("No se pudieron recargar los datos de los estudiantes para realizar la eliminación. Por favor, inténtelo de nuevo.")
                else:
                    normalized_names_to_delete = {str(name).lower().strip() for name in names_to_delete}
                    
                    students_to_keep_df = current_students_df_from_db[
                        ~current_students_df_from_db['nombre'].astype(str).str.lower().str.strip().isin(normalized_names_to_delete)
                    ]
                    
                    if save_students(students_to_keep_df):
                        set_last_updated('students')
                        st.success(f"¡{len(names_to_delete)} estudiante(s) eliminado(s) exitosamente!")
                        st.rerun()
                    else:
                        st.error("Error al guardar los cambios después de intentar eliminar estudiantes.")
        elif any(edited_df['Eliminar']):
             pass 

elif df_loaded is not None and df_loaded.empty:
    st.info("La lista de estudiantes está actualmente vacía. Suba un archivo para agregar estudiantes.")
else:
    st.info("No se encontraron datos de estudiantes o falló la carga. Por favor, suba un archivo para comenzar.")
