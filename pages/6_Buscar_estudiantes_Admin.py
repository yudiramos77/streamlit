import streamlit as st
import pandas as pd
from config import setup_page
from utils_admin import admin_get_student_group_emails, find_students
from utils import strip_email_and_map_course

# def create_whatsapp_link(phone: str) -> str:
#     if pd.isna(phone) or not str(phone).strip():
#         return ""
#     phone = ''.join(filter(str.isdigit, str(phone)))
#     return f"https://wa.me/{phone}" if phone else ""

# def create_teams_link(email: str) -> str:
#     if pd.isna(email) or not str(email).strip() or '@' not in str(email):
#         return ""
#     return f"https://teams.microsoft.com/l/chat/0/0?users={email}"

# --- Initialize session state variables at the very top ---



# --- Login Check ---
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()
# --- End Login Check ---

# This ensures they exist before any part of the script tries to access them.
# if 'all_students_df' not in st.session_state:
#     st.session_state['all_students_df'] = pd.DataFrame() # Initialize as empty DataFrame

# # Cargar datos de estudiantes desde Firebase y guardalos en session
# if not st.session_state['all_students_df'].empty:
#     # Aquí carga la tabla completa desde Firebase
#     st.session_state['all_students_df'] = find_students(student_name, modules_selected_course)
# else:
#     # Ya está cargada
#     df_students = st.session_state['all_students_df']


def create_whatsapp_link(phone: str) -> str:
    if pd.isna(phone) or not str(phone).strip():
        return ""
    phone = ''.join(filter(str.isdigit, str(phone)))
    return f"https://wa.me/{phone}" if phone else ""

def create_teams_link(email: str) -> str:
    if pd.isna(email) or not str(email).strip() or '@' not in str(email):
        return ""
    return f"https://teams.microsoft.com/l/chat/0/0?users={email}"


# Setup page title (now that config is done and user is logged in)
setup_page("Buscador de Estudiantes por Administrador")

course_emails = admin_get_student_group_emails()

modules_selected_course = None # Initialize modules_selected_course before the if/else block

if course_emails:
    full_emails_for_options = course_emails.copy() # Good practice to copy if you modify original later
    course_options = {
        email: {
            'label': email.capitalize().split('@')[0], # Display part without domain
            'value': email                              # Full email with domain
        }
        for email in full_emails_for_options
    }

else:
    st.warning("No se encontraron cursos disponibles.")
    modules_selected_course = None # Ensure it's explicitly None if no courses

# --- Mapping for status selectbox ---
status_mapping = {
    "- No seleccionado -": "all",
    "Graduado": "graduated",
    "En curso": "in_progress",
    "No iniciado": "not_started"
}

# Usamos un formulario para capturar los datos
with st.form("student_form"):
    # Creamos tres columnas
    col1, col2, col3 = st.columns(3)
    
    # Campos dentro de cada columna
    with col1:
        student_name = st.text_input("Nombre del Estudiante")
    
    with col2:
        course_options_with_empty = [""] + full_emails_for_options
        modules_selected_course = st.selectbox(
            "Curso",
            options=course_options_with_empty,
            format_func=lambda x: course_options.get(x, {}).get('label', 'Seleccione un curso') if x else "Todos los cursos",
            index=0,
            key="course_selector"
        )
        
    
    with col3:
        # Your new selectbox for status
        selected_display_status = st.selectbox(
            "Estado",
            options=list(status_mapping.keys()), # Use the display names as options
            index=2,
            key="status_selector"
        )
        # Get the internal status value
        selected_internal_status = status_mapping[selected_display_status]
    
    # Botón para enviar el formulario
    submitted = st.form_submit_button("Buscar Estudiante", type="primary")



if submitted:
    if student_name:
        # Call the find_students function to get the data
        # 'results' DataFrame will now include the 'course_email' column
        results = find_students(student_name, modules_selected_course, selected_internal_status)

        # Add WhatsApp Link column
        if 'telefono' in results.columns and not results.empty:
            results['Whatsapp Link'] = results['telefono'].apply(create_whatsapp_link)
        else:
            # If 'telefono' column doesn't exist or results are empty, add an empty column
            results['Whatsapp Link'] = '' # Initialize with empty strings

        # Add Teams Link column
        if 'email' in results.columns and not results.empty:
            results['Teams Link'] = results['email'].apply(create_teams_link)
        else:
            # If 'email' column doesn't exist or results are empty, add an empty column
            results['Teams Link'] = '' # Initialize with empty strings



        # Strip '@iti,edu' from the 'course_email' column if it exists and is a string
        if 'course_email' in results.columns and not results.empty:
            # Apply the stripping operation. Use .str accessor for string methods on Series.
            # Use .apply() with a lambda for more complex logic or error handling if needed,
            # but .str.split().str[0] is clean here.
            results['course_email'] = results['course_email'].apply(strip_email_and_map_course)
            # results['course_email'] = results['course_email'].astype(str).str.upper().str.split('@').str[0]
            # .astype(str) is important to handle potential non-string values gracefully,
            # though our find_students should ensure it's always a string.

        # Convertir fecha_inicio a formato m/d/Y
        if 'fecha_inicio' in results.columns and not results.empty:
            # Convert to datetime first, handling potential errors
            results['fecha_inicio'] = pd.to_datetime(results['fecha_inicio'], errors='coerce')
            # Now apply strftime, dropping any NaT values that resulted from 'coerce'
            results['fecha_inicio'] = results['fecha_inicio'].dt.strftime('%m/%d/%Y').fillna('') # Fill NaN (NaT) with empty string

        # Convertir fecha_fin a formato m/d/Y
        if 'fecha_fin' in results.columns and not results.empty:
            # Convert to datetime first, handling potential errors
            results['fecha_fin'] = pd.to_datetime(results['fecha_fin'], errors='coerce')
            # Now apply strftime
            results['fecha_fin'] = results['fecha_fin'].dt.strftime('%m/%d/%Y').fillna('') # Fill NaN (NaT) with empty string


        # Define all columns you want to display, including 'course_email'
        # This list also defines the order of the columns.
        columns_to_display_order = [
            'course_email', 'nombre', 'email', 'telefono', 'modulo', 'fecha_inicio',
            'modulo_fin_name', 'fecha_fin', 'Whatsapp Link', 'Teams Link'
        ]

        # Filter the DataFrame to only include the columns you want to display
        # and ensure they exist in the DataFrame. This prevents KeyError.
        # We'll also apply renaming to these selected columns.
        
        # Create a mapping for renaming columns for display
        column_rename_map = {
            'nombre': 'Nombre',
            'email': 'Correo Electrónico',
            'telefono': 'Teléfono',
            'modulo': 'Módulo (Inicio)',
            'fecha_inicio': 'Fecha de Inicio',
            'modulo_fin_name': 'Módulo (Final)',
            'fecha_fin': 'Fecha de Finalización',
            'course_email': 'Curso', # Added translation for course_email
            'Whatsapp Link': 'WhatsApp', # Renamed for display
            'Teams Link': 'Teams'       # Renamed for display
        }
        
        # Identify columns present in results AND in our desired display list
        actual_columns_for_display = [col for col in columns_to_display_order if col in results.columns]
        
        # Select and rename columns in one go for clarity
        if not results.empty:
            display_df = results[actual_columns_for_display].rename(columns=column_rename_map)
        else:
            # If results is empty, create an empty DataFrame with renamed columns
            # to avoid errors when trying to display an empty table with specific headers.
            empty_cols = [column_rename_map.get(col, col) for col in actual_columns_for_display]
            display_df = pd.DataFrame(columns=empty_cols)


        if not display_df.empty:
            print(modules_selected_course) # Keep this for your internal debugging
            
            # Determine the course message for the success message
            course_message = modules_selected_course.split('@')[0] if modules_selected_course else 'todos los cursos'
            
            st.success(f"✅ Se encontraron {len(display_df)} estudiante(s) con **{student_name}** en **{course_message}** con estado **{selected_display_status}**")

            column_configuration = {
                "WhatsApp": st.column_config.LinkColumn(
                    "WhatsApp",
                    help="Click para enviar mensaje por WhatsApp",
                    display_text="Chat", # Text displayed for the link
                    width="small" # Adjust width as needed
                ),
                "Teams": st.column_config.LinkColumn(
                    "Teams",
                    help="Click para iniciar chat en Microsoft Teams",
                    display_text="Chat", # Text displayed for the link
                    width="small"
                ),
            }
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config=column_configuration # Pass the configuration here
            )
        else:
            st.warning(" ⚠️ No se encontraron estudiantes que coincidan con los criterios de búsqueda.")
    else:
        st.warning("⚠️ Por favor, complete todos los campos obligatorios.")
