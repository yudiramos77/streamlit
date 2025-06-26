import streamlit as st
import pandas as pd
import urllib.parse
import datetime
from config import setup_page, db
from utils import create_filename_date_range, get_student_email, get_student_start_date, get_student_phone, date_format
from utils_admin import admin_get_student_group_emails, admin_load_students, admin_get_last_updated

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
    if st.session_state.cached_course_email != course_email:
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
                user_email_db_key = course_email.replace('.', ',')
                all_records = db.child("attendance").child(user_email_db_key).get(token=st.session_state.user_token).val() or {}
                st.session_state.attendance_records = all_records
            except Exception as e:
                st.error(f"No se pudieron cargar los registros de asistencia: {e}")
                st.session_state.attendance_records = {}

            # Update the cache key to prevent reloading
            st.session_state.cached_course_email = course_email

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
    today = datetime.date.today()
    default_start_date = today.replace(day=1)

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Fecha de Inicio", value=default_start_date, key="report_start_date", format="MM/DD/YYYY")
    with col2:
        end_date = st.date_input("Fecha de Fin", value=today, key="report_end_date", format="MM/DD/YYYY")

    all_attendance_dates = sorted(st.session_state.attendance_records.keys())
    if all_attendance_dates:
        st.caption("Asistencia(s) guardada(s):")
        all_badges = " ".join([f":gray-badge[:material/calendar_today: {datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime('%m-%d-%Y')}]" for date_str in all_attendance_dates])
        st.markdown(all_badges)
    else:
        st.caption("No hay fechas con asistencia registrada para este curso.")

    if start_date > end_date:
        st.error("Error: La fecha de inicio no puede ser posterior a la fecha de fin.")
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

            def get_first_name(full_name: str) -> str:
                return full_name.strip().split()[0].capitalize()

            if students_never_attended_list:
                st.warning(f"{len(students_never_attended_list)} estudiante(s) no tuvieron registros de 'Presente' en este período:")
                
                never_attended_data = []
                for student_name in students_never_attended_list:
                    start_date_str = get_student_start_date(all_students_df, student_name)
                    phone = get_student_phone(all_students_df, student_name)
                    
                    message = f"Hola {get_first_name(student_name)}, notamos que no has asistido. ¿Todo bien? Contáctanos."
                    whatsapp_link = create_whatsapp_link(phone, message) if phone else '#'
    
                    never_attended_data.append({
                        'Nombre': student_name.strip(),
                        'Inicio': start_date_str,
                        'Teléfono': phone or 'No disponible',
                        'WhatsApp': whatsapp_link
                    })

                df_never_attended = pd.DataFrame(never_attended_data)
                
                st.dataframe(
                    df_never_attended, use_container_width=True, hide_index=True,
                    column_config={'WhatsApp': st.column_config.LinkColumn("WhatsApp", display_text="Contactar")}
                )
                
                csv_export_never = df_never_attended.drop(columns=['WhatsApp']).to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="Descargar Lista (Nunca Asistieron)", data=csv_export_never,
                    file_name=f"nunca_asistieron_{start_date.strftime('%Y%m%d')}_a_{end_date.strftime('%Y%m%d')}.csv",
                    mime='text/csv', key='download_never_attended_csv_btn', type="primary"
                )
            else:
                st.success("¡Excelente! Todos los estudiantes registrados asistieron al menos una vez en el rango de fechas seleccionado.")

