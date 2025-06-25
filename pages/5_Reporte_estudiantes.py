import streamlit as st
import pandas as pd
import datetime
import urllib.parse
from config import setup_page
from utils import (
    load_students,
    get_module_on_date, get_highest_module_credit, get_last_updated,
    get_module_name_by_id, load_modules, highlight_style
)

# --- Login Check ---
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()
# --- End Login Check ---

setup_page("Reporte de Estudiantes")

# Module section

if 'modules_df' not in st.session_state:
    st.session_state.modules_df = None

if 'current_module_id_for_today' not in st.session_state:
    st.session_state.current_module_id_for_today = None

if 'current_module_id_for_today' in st.session_state and st.session_state.current_module_id_for_today is None:
    result = get_module_on_date(st.session_state.get('email').replace('.', ','))
    # print("\n\nresult\n", result)
    if result and 'module_id' in result:
        st.session_state.current_module_id_for_today = result['firebase_key']
        print("\n\ncurrent_module_id_for_today\n", result['firebase_key'])
        print("\n\nst.session_state.current_module_id_for_today\n", st.session_state.current_module_id_for_today)
    else:
        st.warning("No se encontró un módulo activo para hoy.")


# st.button(
#     "Limpiar Módulo Actual",
#     on_click=lambda: st.session_state.update({"current_module_id_for_today": None}),
#     help="Borra el módulo actual guardado en la sesión actual."
# )

# Student section
students_last_updated = get_last_updated('students')
# print("\n\nstudents_last_updated\n", students_last_updated)
df_loaded, _ = load_students(students_last_updated)
# print("\n\ndf_loaded\n", df_loaded)

if df_loaded is None or df_loaded.empty:
    st.info("No hay estudiantes registrados.")
else:
    # Clean and format the data
    if 'ciclo' in df_loaded.columns:
        df_loaded = df_loaded.drop(columns=['ciclo'])
    
    # Format date columns
    date_columns = ['fecha_inicio', 'fecha_fin']
    for col in date_columns:
        if col in df_loaded.columns:
            df_loaded[col] = pd.to_datetime(df_loaded[col], errors='coerce').dt.strftime('%m/%d/%Y')
    
    # Select and order columns to display
    display_columns = ['nombre', 'email', 'telefono', 'modulo', 'fecha_inicio','modulo_fin_name', 'fecha_fin', 'modulo_fin_id' ]
    display_columns = [col for col in display_columns if col in df_loaded.columns]
    
    # Rename columns for display
    column_names = {
        'nombre': 'Nombre',
        'email': 'Correo Electrónico',
        'telefono': 'Teléfono',
        'modulo': 'Módulo (ID)',
        'modulo_nombre': 'Módulo',
        'fecha_inicio': 'Fecha de Inicio',
        'fecha_fin': 'Fecha de Finalización',
        'modulo_fin_name': 'Módulo (Final)',
        }

    current_module_id = st.session_state.get('current_module_id_for_today')

    total_students = len(df_loaded)
    # print("total_students", total_students)

    df_loaded['_fecha_inicio_dt'] = pd.to_datetime(df_loaded['fecha_inicio']).dt.date
    df_loaded['_fecha_fin_dt'] = pd.to_datetime(df_loaded['fecha_fin']).dt.date

    # Then create formatted versions for display
    df_loaded['fecha_inicio'] = df_loaded['_fecha_inicio_dt'].apply(lambda x: x.strftime('%m/%d/%Y'))
    df_loaded['fecha_fin'] = df_loaded['_fecha_fin_dt'].apply(lambda x: x.strftime('%m/%d/%Y'))

    today = datetime.date.today()
    students_in_module = len(df_loaded[
        (df_loaded['_fecha_inicio_dt'] <= today) &
        (df_loaded['_fecha_fin_dt'] >= today)
    ])
    # print("students_in_module", students_in_module)

    students_not_in_module = total_students - students_in_module
    # print("students_not_in_module", students_not_in_module)

    students_in_last_module = len(df_loaded[
        (df_loaded['_fecha_fin_dt'] <= today)
    ])

    last_module_students = df_loaded[
        (df_loaded['_fecha_inicio_dt'] <= today) &
        (df_loaded['_fecha_fin_dt'] >= today) &
        (df_loaded['_fecha_fin_dt'] == df_loaded.groupby('email')['_fecha_fin_dt'].transform('max'))
    ]
    df_loaded['En Ultimo Módulo'] = df_loaded['email'].apply(
        lambda x: 'Sí' if x in last_module_students['email'].unique() else 'No'
    )

    today = pd.to_datetime(today)
    df_loaded['_fecha_inicio_dt'] = pd.to_datetime(df_loaded['_fecha_inicio_dt'])
    df_loaded['_fecha_fin_dt'] = pd.to_datetime(df_loaded['_fecha_fin_dt'])


    students_in_last_module = len(df_loaded[
        (df_loaded['_fecha_inicio_dt'] <= today) &
        (df_loaded['_fecha_fin_dt'] >= today) &
        (df_loaded['modulo_fin_id'] == current_module_id)
    ])
    # print("students_in_last_module", students_in_last_module)


    students_finished = len(df_loaded[
        (df_loaded['_fecha_fin_dt'] <= today)
    ])
    # print("students_finished", students_finished)


    # ------ Highlight current module section ------
    # This section will highlight the current module in the DataFrame
    # Assuming df_loaded is your initial DataFrame and is already loaded
    

    # 1. Define all columns you need, including the one for logic
    # Using a single DataFrame is simpler than maintaining two.
    internal_columns = [
        'nombre', 'email', 'telefono', 'modulo', 'fecha_inicio', 
        'modulo_fin_name', 'fecha_fin', 'modulo_fin_id'
    ]
    df = df_loaded[internal_columns].copy()

    # 2. Create WhatsApp and Teams links
    default_message = "Hola, me comunico desde el instituto. ¿Cómo estás?"
    default_subject = "De Interamerican Technical Institute"
    
    def create_whatsapp_link(phone: str, message: str) -> str:
        phone = ''.join(filter(str.isdigit, phone))
        encoded_message = urllib.parse.quote(message)
        return f"https://wa.me/{phone}?text={encoded_message}"  

    def create_teams_link(email: str, message: str) -> str:
        encoded_message = urllib.parse.quote(message)
        return f"https://teams.microsoft.com/l/chat/0/0?users={email}&message={encoded_message}"  

    def create_email_link(email: str, message: str) -> str:
        to = urllib.parse.quote(email)
        subj = urllib.parse.quote(default_subject)
        body = urllib.parse.quote(message)
        return f"https://outlook.office.com/mail/deeplink/compose?to={to}&subject={subj}&body={body}"
    

    # Ensure phone numbers are strings and clean them
    df['telefono'] = df['telefono'].astype(str).str.strip()
    
    # Create WhatsApp links
    df['whatsapp_link'] = df['telefono'].apply(create_whatsapp_link, message=default_message)  
    # Create Teams links
    df['teams_link'] = df['email'].apply(create_teams_link, message=default_message)
    # Create Email links
    df['email_link'] = df['email'].apply(create_email_link, message=default_message)
    
    # 3. Rename columns for user-friendly display
    column_renames = {
        'nombre': 'Nombre',
        'email': 'Correo Electrónico',
        'telefono': 'Teléfono',
        'modulo': 'Módulo (ID)',
        'fecha_inicio': 'Fecha de Inicio',
        'fecha_fin': 'Fecha de Finalización',
        'modulo_fin_name': 'Módulo (Final)',
        'whatsapp_link': 'WhatsApp',
        'teams_link': 'Microsoft Teams',
        'email_link': 'Email Link',
    }
    df_renamed = df.rename(columns=column_renames)


    def highlight_row_warning(row):
        """
        Highlights a row in yellow if it's the current module and has already started.
        """
        try:
            is_current_module = row.get('modulo_fin_id') == current_module_id
            is_module_started = False
            start_date_val = row.get('Fecha de Inicio')

            if pd.notna(start_date_val):
                try:
                    start_date = pd.to_datetime(start_date_val).date()
                    is_module_started = start_date <= datetime.date.today()
                except (ValueError, TypeError):
                    is_module_started = False
            
            if is_current_module and is_module_started:

                return [highlight_style('warning') for _ in row]

        except Exception as e:
            print(f"Error processing row in highlight_function: {row.to_dict()}")
            print(f"Error was: {e}")

        return ['' for _ in row]

    def highlight_row_error(row):
        """
        Highlights a row in red if fecha_fin is in the past.
        """
        try:
            # Asegúrate de que la columna exista y no sea nula antes de comparar
            end_date_val = row.get('Fecha de Finalización') # <--- CORREGIDO
            fecha_fin_in_past = False
            if pd.notna(end_date_val):
                # Convierte a fecha para una comparación segura
                end_date = pd.to_datetime(end_date_val).date()
                fecha_fin_in_past = end_date < datetime.date.today()
            
            if fecha_fin_in_past:
                return [highlight_style('error') for _ in row]

        except Exception as e:
            print(f"Error processing row in highlight_function: {row.to_dict()}")
            print(f"Error was: {e}")

        return ['' for _ in row]

    def highlight_row_success(row):
        """
        Highlights a row in green if fecha_inicio is in the future.
        """
        try:
            # Asegúrate de que la columna exista y no sea nula antes de comparar
            start_date_val = row.get('Fecha de Inicio') # <--- CORREGIDO
            fecha_inicio_in_future = False
            if pd.notna(start_date_val):
                # Convierte a fecha para una comparación segura
                start_date = pd.to_datetime(start_date_val).date()
                fecha_inicio_in_future = start_date > datetime.date.today()
            
            if fecha_inicio_in_future:
                return [highlight_style('success') for _ in row]

        except Exception as e:
            print(f"Error processing row in highlight_function: {row.to_dict()}")
            print(f"Error was: {e}")

        return ['' for _ in row]

    # Sort the DataFrame by 'Fecha de Inicio'
    df_renamed = df_renamed.sort_values(by='Fecha de Inicio', ascending=True)   

    # 4. Decide whether to apply styling
    if current_module_id:
        # Apply the style to the renamed DataFrame
        df_to_show = df_renamed.style.apply(highlight_row_warning, axis=1).apply(highlight_row_error, axis=1).apply(highlight_row_success, axis=1)
    else:
        # If no ID is set, just use the regular DataFrame
        df_to_show = df_renamed

    

    # Metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total", total_students, border=True)
    with col2:
        st.metric("En Curso", students_in_module, border=True)
    with col3:
        st.metric("Último Módulo", students_in_last_module, border=True)
    with col4:
        st.metric("Graduados", students_finished, border=True)
    with col5:
        st.metric("No comenzado", students_not_in_module - students_finished, border=True)




# 5. Display the DataFrame and hide the column
    st.dataframe(
        df_to_show,
        hide_index=True,
        use_container_width=True,
        column_config={
            # Setting a column's configuration to None completely removes it from display.
            "modulo_fin_id": None,
            # Your other column configurations for renaming headers remain the same
            "Nombre": "Estudiante",
            "Correo Electrónico": "Email",
            "Teléfono": "Teléfono",
            "Módulo (ID)": "Módulo (Inicio)",
            "Fecha de Inicio": "Inicio",
            "Fecha de Finalización": "Fin",
            "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="💬"),
            "Microsoft Teams": st.column_config.LinkColumn("Teams", display_text="💻"),
            "Email Link": st.column_config.LinkColumn("Email", display_text="📧")
        },
        column_order=[
            "Nombre", 
            "Correo Electrónico", 
            "Teléfono", 
            "Email Link", 
            "WhatsApp", 
            "Microsoft Teams", 
            "Módulo (ID)", 
            "Fecha de Inicio", 
            "Fecha de Finalización", 
            "Último Módulo",
            
        ]
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.warning("Último módulo")
    with col2:
        st.error("Graduados")
    with col3:
        st.success("No han empezado")

    # st.info("Por favor, seleccione un módulo para ver los estudiantes.")
    # st.warning("Por favor, seleccione un módulo para ver los estudiantes.")
    # st.success("Por favor, seleccione un módulo para ver los estudiantes.")


