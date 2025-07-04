import streamlit as st
import pandas as pd
import urllib.parse
import datetime
from config import setup_page, db
from utils import create_filename_date_range, get_student_email, get_student_start_date, get_student_phone, date_format, get_student_modulo_inicio, get_student_modulo_fin, get_student_end_date
from utils_admin import admin_get_student_group_emails, admin_load_students, admin_get_last_updated, admin_get_attendance

# --- Session Check ---
if not st.session_state.get("logged_in"):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página de Login y vuelva a iniciar sesión.")
    st.stop()
# --- End Session Check ---

setup_page("Reportes de Asistencia")

# --- Session State Initialization for Caching ---
if 'cached_course_email' not in st.session_state:
    st.session_state.cached_course_email = None
if 'students_df' not in st.session_state:
    st.session_state.students_df = pd.DataFrame()
if 'attendance_records' not in st.session_state:
    st.session_state.attendance_records = {}
if 'course_data_cache' not in st.session_state:
    st.session_state.course_data_cache = {}

# Manual Spanish day name mapping
SPANISH_DAY_NAMES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado",
    "Sunday": "Domingo"
}

# --- Data Loading and Caching Function ---
def load_data_into_session(course_email):
    """
    Loads all student and attendance data for a course into the session state.
    Only performs database calls if the selected course has changed.
    """
    
    with st.spinner(f"Cargando todos los datos para el curso {course_email}..."):
        # Load students for the selected course
        students_last_updated = admin_get_last_updated('students', course_email)
        students_df, _ = admin_load_students(course_email, students_last_updated)
    

        # This ensures the DataFrame index (likely the student ID from Firebase) becomes a column named 'id'
        if students_df is not None and not students_df.empty:
            students_df = students_df.reset_index().rename(columns={'index': 'id'})
        else:
            students_df = pd.DataFrame()
        
        st.session_state.students_df = students_df

        # Load ALL attendance records for the course into a dictionary
        try:
            attendance_last_updated = admin_get_last_updated('attendance', course_email)
            # print("\n\nattendance_last_updated", attendance_last_updated)
            user_email_db_key = course_email.replace('.', ',')
            all_records = admin_get_attendance(user_email_db_key, attendance_last_updated)

            st.session_state.attendance_records = all_records
        except Exception as e:
            st.error(f"No se pudieron cargar los registros de asistencia: {e}")
            all_records = {}
            # st.session_state.attendance_records = {}

        # Store/Update the loaded data for THIS course in the cache
        # This will overwrite any previous data for this course_email, ensuring it's fresh
        st.session_state.course_data_cache[course_email] = {
            'students_df': students_df,
            'attendance_records': all_records
        }
        # st.write(f"Latest data for {course_email} loaded and updated in cache.")

        # Update the cache key to prevent reloading
        # st.session_state.cached_course_email = course_email
    
    # Always make the currently active data available in dedicated session_state keys
    # This allows downstream code to simply refer to st.session_state.students_df etc.
    st.session_state.students_df = st.session_state.course_data_cache[course_email]['students_df']
    st.session_state.attendance_records = st.session_state.course_data_cache[course_email]['attendance_records']


# --- Main UI ---

# 1. Select Course
st.subheader("1. Seleccionar Curso")
course_emails = admin_get_student_group_emails()
selected_course = None

if course_emails:
    course_options = {email: email.capitalize().split('@')[0] for email in course_emails}
    selected_course = st.selectbox(
        "Seleccione un curso para generar el reporte:",
        options=list(course_options.keys()),
        format_func=lambda x: course_options[x],
        index=0,
        key="course_selector"
    )
else:
    st.warning("No se encontraron cursos disponibles.")

st.divider()

if selected_course:
    load_data_into_session(selected_course)

    # 2. Select Date Range
    st.subheader("2. Seleccionar Rango de Fechas")
    
    # Initialize with default values
    today = datetime.date.today()

    all_attendance_dates = sorted(st.session_state.attendance_records.keys())
    if all_attendance_dates:
        try:
            today = datetime.datetime.strptime(max(all_attendance_dates), '%Y-%m-%d').date()
            min_date = datetime.datetime.strptime(min(all_attendance_dates), '%Y-%m-%d').date()
            default_start_date = min_date
            default_end_date = today
        except (ValueError, TypeError):
            today = datetime.date.today()
            default_start_date = today.replace(day=1)
            default_end_date = today
    else:
        today = datetime.date.today()
        default_start_date = today.replace(day=1)
        default_end_date = today

    # --- Step 2: Initialize session state if needed ---
    if 'report_start_date' not in st.session_state:
        st.session_state.report_start_date = default_start_date
    if 'report_end_date' not in st.session_state:
        st.session_state.report_end_date = default_end_date
    if 'week_loaded' not in st.session_state:
        st.session_state.week_loaded = False

    # --- Step 3: Calculate current week range ---
    # Correct calculation for week_start (Monday)
    week_start = today - datetime.timedelta(days=today.weekday())
    # Correct calculation for week_end (Sunday)
    week_end = week_start + datetime.timedelta(days=6)

    # Ensure start and end dates fall within min/max range
    start_val = st.session_state.report_start_date
    end_val = st.session_state.report_end_date

    # Clamp values within the allowed range
    start_val = max(start_val, default_start_date)
    start_val = min(start_val, default_end_date)

    end_val = max(end_val, default_start_date)
    end_val = min(end_val, default_end_date)

    # --- Step 4: Date input controls ---
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.report_start_date = st.date_input(
            "Fecha de Inicio",
            value=start_val,
            key="report_start_date_input",
            format="MM/DD/YYYY",
            min_value=default_start_date,
            max_value=default_end_date
        )

    with col2:
        st.session_state.report_end_date = st.date_input(
            "Fecha de Fin",
            value=end_val,
            key="report_end_date_input",
            format="MM/DD/YYYY",
            min_value=default_start_date,
            max_value=default_end_date
        )

    # --- Step 5: Week checkbox logic ---
    load_current_week = st.checkbox(
        "Fecha de inicio y fin de la semana actual (o mas cercana)",
        value=st.session_state.week_loaded,
        key="load_current_week"
    )

    if load_current_week and not st.session_state.week_loaded:
        st.session_state.report_start_date = week_start
        st.session_state.report_end_date = week_end
        st.session_state.week_loaded = True
        st.rerun()
    elif not load_current_week and st.session_state.week_loaded:
        st.session_state.report_start_date = default_start_date
        st.session_state.report_end_date = default_end_date
        st.session_state.week_loaded = False
        st.rerun()

    # --- Step 6: Use final values ---
    start_date = st.session_state.report_start_date
    end_date = st.session_state.report_end_date

    try:
        # Get all attendance dates
        if st.session_state.attendance_records:
            st.caption("Registros de Asistencia existentes:")
            # Display dates in a grid
            # Correctly generate dates for the current week (Monday to Sunday)
            current_week_dates = [week_start + datetime.timedelta(days=i) for i in range(7)]
            
            # Convert attendance record keys to date objects for comparison
            attendance_date_objects = {datetime.datetime.strptime(date_str, '%Y-%m-%d').date() for date_str in st.session_state.attendance_records}

            all_badges = " ".join([
                f":green-badge[:material/calendar_today: {date.strftime('%m-%d-%Y')}]" 
                if date in current_week_dates else 
                f":gray-badge[:material/calendar_today: {date.strftime('%m-%d-%Y')}] "
                for date in sorted(attendance_date_objects)
            ])
            st.markdown(all_badges)
        else:
            st.caption("No hay fechas con asistencia registrada")
            
    except Exception as e:
        st.error(f"Error al cargar fechas de asistencia: {str(e)}")

    if start_date > end_date:
        st.error("Error: La fecha de inicio no puede ser posterior a la fecha de fin.") # Translated
    else:
        if st.button("Generar Reporte", key="generate_report_btn", type="primary"):
            all_students_df = st.session_state.students_df
            if all_students_df.empty or 'id' not in all_students_df.columns or 'nombre' not in all_students_df.columns:
                st.error("La lista de estudiantes está vacía o no tiene las columnas 'id' y 'nombre'. Verifique los datos del curso.")
                st.stop()
            
            master_student_list = set(all_students_df['nombre'].astype(str).str.strip().unique())
            total_registered_students = len(master_student_list)

            # --- FIX STARTS HERE ---
            # 1. Create a useful ID -> Name mapping dictionary for fast lookups.
            student_id_to_name = all_students_df.set_index('id')['nombre'].to_dict()
            # 2. The line that caused the crash is removed.
            # --- FIX ENDS HERE ---

            daily_summary_data = []
            students_present_in_range = set()
            
            spinner_message = "Generando reporte desde los datos locales..."
            with st.spinner(spinner_message):
                current_date_iter = start_date
                while current_date_iter <= end_date:
                    if current_date_iter.weekday() >= 5:
                        current_date_iter += datetime.timedelta(days=1)
                        continue

                    date_key = current_date_iter.strftime('%Y-%m-%d')
                    daily_attendance_dict = st.session_state.attendance_records.get(date_key, {})
                    
                    present_today_count = 0
                    if daily_attendance_dict:
                        # CASE 1: Handle the LIST format (your current structure)
                        if isinstance(daily_attendance_dict, list):
                            for record in daily_attendance_dict:
                                # Firebase can create 'null' entries in lists, so we check if the record is a dictionary
                                if isinstance(record, dict):
                                    is_present = record.get('Presente', False)
                                    
                                    if is_present:
                                        present_today_count += 1
                                        student_name = record.get('Nombre')
                                        if student_name:
                                            # Add the name directly from the attendance record
                                            students_present_in_range.add(student_name.strip())

                        # CASE 2: Handle the DICTIONARY format (for backward compatibility or other courses)
                        elif isinstance(daily_attendance_dict, dict):
                            for student_id, details in daily_attendance_dict.items():
                                status = details.get('status', 'ausente') if isinstance(details, dict) else (details or 'ausente')
                                
                                if status.lower() == 'presente':
                                    present_today_count += 1
                                    student_name = student_id_to_name.get(student_id)
                                    if student_name:
                                        students_present_in_range.add(student_name.strip())
                        
                        # CASE 3: Warn about any other unexpected format
                        else:
                            st.warning(f"Se omitieron los datos de asistencia para el {date_key} debido a un formato de datos desconocido: '{type(daily_attendance_dict).__name__}'.")

                    absent_today_count = total_registered_students - present_today_count
                    english_day_name = current_date_iter.strftime('%A')
                    spanish_day_name = SPANISH_DAY_NAMES.get(english_day_name, english_day_name)
                    
                    daily_summary_data.append({
                        'Fecha': date_format(current_date_iter, '%Y-%m-%d'),
                        'Día': spanish_day_name.capitalize(),
                        '# Presentes': present_today_count,
                        '# Ausentes': absent_today_count
                    })
                    current_date_iter += datetime.timedelta(days=1)
            
            # Display Daily Summary Report
            if daily_summary_data:
                st.subheader(f"Resumen Diario de Asistencia: {date_format(start_date, '%Y-%m-%d')} a {date_format(end_date, '%Y-%m-%d')}")
                df_summary_display = pd.DataFrame(daily_summary_data)[['Fecha', 'Día', '# Presentes', '# Ausentes']]
                st.dataframe(df_summary_display, use_container_width=True, hide_index=True)
                
                csv_export = df_summary_display.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="Descargar Resumen", data=csv_export,
                    file_name=f"resumen_asistencia_{start_date.strftime('%Y%m%d')}_a_{end_date.strftime('%Y%m%d')}.csv",
                    mime='text/csv', key='download_summary_csv_btn'
                )
            
            # Identify and Display Students Who Never Attended
            st.divider()
            st.subheader("Estudiantes que Nunca Asistieron en el Rango de Fechas")
            students_never_attended_list = sorted(list(master_student_list - students_present_in_range))
            
            def create_whatsapp_link(phone: str, message: str) -> str:
                phone_digits = ''.join(filter(str.isdigit, str(phone)))
                return f"https://wa.me/{phone_digits}?text={urllib.parse.quote(message)}"
    
            def create_teams_link(email: str, message: str) -> str:
                encoded_message = urllib.parse.quote(message)
                return f"https://teams.microsoft.com/l/chat/0/0?users={email}&message={encoded_message}"

            def get_first_name(full_name: str) -> str:
                return full_name.strip().split()[0].capitalize()

            if students_never_attended_list:
                st.warning(f"{len(students_never_attended_list)} estudiante(s) no tuvieron registros de 'Presente' en este período:")
                
                never_attended_data = []
                for student_name in students_never_attended_list:
                    modulo_inicio = get_student_modulo_inicio(all_students_df, student_name)
                    modulo_fin = get_student_modulo_fin(all_students_df, student_name)  
                    start_date_str = get_student_start_date(all_students_df, student_name)
                    end_date = get_student_end_date(all_students_df, student_name)
                    phone = get_student_phone(all_students_df, student_name)
                    email = get_student_email(all_students_df, student_name)
                    
                    # message = f"Hola {get_first_name(student_name)}, notamos que no has asistido. ¿Todo bien? Contáctanos."
                    # whatsapp_link = create_whatsapp_link(phone, message) if phone else '#'
    
                    if phone:
                        message = f"Hola {get_first_name(student_name)}, notamos que no has asistido. ¿Todo bien? Contáctanos."
                        whatsapp_link = create_whatsapp_link(phone, message) if phone else '#'
                    else:
                        whatsapp_link = '#'

                    if email:
                        message = f"Hola {get_first_name(student_name)}, notamos que no has asistido. ¿Todo bien? Contáctanos."
                        teams_link = create_teams_link(email, message)
                    else:
                        teams_link = '#'
                    never_attended_data.append({
                        'Nombre': student_name.strip(),
                        'Modulo Inicio': modulo_inicio,
                        'Inicio': start_date_str,
                        'Modulo Fin': modulo_fin,
                        'Fin': end_date,
                        'Teléfono': phone or 'No disponible',
                        'WhatsApp': whatsapp_link,
                        'Teams': teams_link
                    })

                df_never_attended = pd.DataFrame(never_attended_data)
                
                st.dataframe(
                    df_never_attended, use_container_width=True, hide_index=True,
                    column_config={
                        'WhatsApp': st.column_config.LinkColumn("WhatsApp", display_text="Contactar"),
                        'Teams': st.column_config.LinkColumn(width="small", display_text="Contactar"),
                        'Inicio': st.column_config.DateColumn(
                            'Inicio',
                            format="MM/DD/YYYY"
                        ),
                        'Fin': st.column_config.DateColumn(
                            'Fin',
                            format="MM/DD/YYYY"
                        )  
                    }
                )
                
                csv_export_never = df_never_attended.drop(columns=['WhatsApp', 'Teams']).to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="Descargar Lista (Nunca Asistieron)", data=csv_export_never,
                    file_name="nunca_asistieron.csv",
                    mime='text/csv', key='download_never_attended_csv_btn', type="primary"
                )
            else:

                st.success("¡Excelente! Todos los estudiantes registrados asistieron **al menos una vez** en el rango de fechas seleccionado.", icon=":material/thumb_up:")

