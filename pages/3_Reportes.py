import streamlit as st
import pandas as pd
import urllib.parse
import datetime
from config import setup_page, db # Assuming db is implicitly used by load_attendance via utils
from utils import load_attendance, load_students # Use the centralized functions
from utils import create_filename_date_range, load_attendance, get_attendance_dates, load_students, get_last_updated, get_student_email, get_student_start_date, get_student_phone, date_format, load_all_attendance


# --- Session Check ---
# This block now checks for both login status AND a valid session structure
# required by the authentication utility functions.
# st.write(st.session_state)
if (
    not st.session_state.get("logged_in")
    or "token_expires_at" not in st.session_state
    or st.session_state.get("token_expires_at") is None
):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Si el problema persiste, es posible que su sesión anterior haya caducado. Por favor, regrese a la página de Login y vuelva a iniciar sesión.")
    st.stop()
# --- End Session Check ---


# --- Session Check ---
if 'all_attendance_data' not in st.session_state:
    st.session_state.all_attendance_data = {}

# Setup page
setup_page("Reportes de Asistencia") # Reverted call

# Load all attendance data if not already loaded

with st.spinner("Cargando datos de asistencia..."):
    
    attendance_last_updated = get_last_updated('attendance', st.session_state.email)
    st.session_state.all_attendance_data = load_all_attendance( st.session_state.email, attendance_last_updated)

# Manual Spanish day name mapping to avoid locale/encoding issues
SPANISH_DAY_NAMES = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo"
}
# Main UI

# Initialize with default values

# attendance_last_updated = get_last_updated('attendance', st.session_state.email)
all_attendance = get_attendance_dates(attendance_last_updated)
if all_attendance:
    today = datetime.date.today()
    all_attendance_dates = sorted(all_attendance)
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
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=4)

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
        if all_attendance:
            st.caption("Registros de Asistencia existentes:")
            # Display dates in a grid
            current_week = [today - datetime.timedelta(days=today.weekday() + i) for i in range(7)]
            all_badges = " ".join([f":green-badge[:material/calendar_today: {date.strftime('%m-%d-%Y')}]" if date in current_week else f":gray-badge[:material/calendar_today: {date.strftime('%m-%d-%Y')}] " for date in sorted({datetime.datetime.strptime(date_str, '%Y-%m-%d').date() for date_str in all_attendance})])
            st.markdown(all_badges)
        else:
            st.caption("No hay fechas con asistencia registrada")
            
    except Exception as e:
        st.error(f"Error al cargar fechas de asistencia: {str(e)}")

    if start_date > end_date:
        st.error("Error: La fecha de inicio no puede ser posterior a la fecha de fin.") # Translated
    else:
        if st.button("Generar Reporte", key="generate_report_btn", type="primary"): # Translated
            # 1. Load all students
            students_last_updated = get_last_updated('students')
            attendance_last_updated = get_last_updated('attendance')
            all_students_df, _ = load_students(students_last_updated)
            if all_students_df is None or all_students_df.empty:
                st.error("No se pudo cargar la lista de estudiantes. Por favor, registre estudiantes en la página 'Estudiantes'.") # Translated
                st.stop()
            
            # Assuming student names are in 'nombre' column and are unique identifiers
            master_student_list = set(all_students_df['nombre'].astype(str).str.strip().unique())
            total_registered_students = len(master_student_list)

            # 2. Process attendance data for the date range
            daily_summary_data = []
            students_present_in_range = set() # This still considers all days for 'never attended'
            
            current_date_iter = start_date
            
            spinner_message = f"Cargando y procesando asistencia desde {start_date.strftime('%Y-%m-%d')} hasta {end_date.strftime('%Y-%m-%d')}..." # Translated
            with st.spinner(spinner_message):
                print("all attendance data", st.session_state.all_attendance_data)
                while current_date_iter <= end_date:
                    # Exclude weekends (Saturday=5, Sunday=6 in weekday() method)
                    if current_date_iter.weekday() >= 5: # 0=Monday, 1=Tuesday, ..., 5=Saturday, 6=Sunday
                        current_date_iter += datetime.timedelta(days=1)
                        continue # Skip to next day if it's a weekend

                    # Get attendance from pre-loaded data
                    date_key = current_date_iter.strftime('%Y-%m-%d')
                    # Assign daily_attendance_records immediately with a default of an empty list
                    daily_attendance_records = st.session_state.all_attendance_data.get(date_key, [])
                    
                    # Ensure daily_attendance_records is actually a list
                    if not isinstance(daily_attendance_records, list):
                        st.error(f"Error: Data for {date_key} was expected to be a list of records, but got {type(daily_attendance_records)}. Treating as empty.")
                        daily_attendance_records = [] # Reset to empty list to prevent further errors

                    present_today_count = 0
                    if daily_attendance_records: # Check if the list of records is not empty
                        # Iterate over each student's attendance record in the list
                        for record in daily_attendance_records:
                            # Ensure each record is a dictionary before trying to access its items
                            if isinstance(record, dict):
                                # Access student name using the 'Nombre' key
                                student_name = record.get('Nombre')
                                # Check the 'Presente' status
                                if record.get('Presente', False): # Default to False if 'Presente' key is missing
                                    present_today_count += 1
                                    # Add the student name to the set of students present in the range
                                    if student_name: # Only add if a name was found
                                        students_present_in_range.add(student_name)
                            # else:
                            #     st.warning(f"DEBUG: Found a non-dictionary item in the attendance list for {date_key}: {record}. Skipping this item.")
                    
                    absent_today_count = total_registered_students - present_today_count
                    english_day_name = current_date_iter.strftime('%A')
                    spanish_day_name = SPANISH_DAY_NAMES.get(english_day_name, english_day_name) # Fallback to English if not found
                    
                    daily_summary_data.append({
                        'Fecha': date_format(current_date_iter, '%Y-%m-%d'), # Keep 'Fecha' or 'Date'
                        'Día': spanish_day_name.capitalize(), # Spanish Day Name, capitalized
                        '# Presentes': present_today_count, # Translated
                        '# Ausentes': absent_today_count    # Translated
                    })
                    current_date_iter += datetime.timedelta(days=1)
            
            # 3. Display Daily Summary Report
            if daily_summary_data:
                summary_header = f"Resumen Diario de Asistencia: {date_format(start_date, '%Y-%m-%d')} hasta {date_format(end_date, '%Y-%m-%d')}" # Translated
                st.subheader(summary_header)
                df_summary_display = pd.DataFrame(daily_summary_data)
                # Reorder columns for better display, including Day Name
                cols_order = ['Fecha', 'Día', '# Presentes', '# Ausentes'] # Updated column names
                df_summary_display = df_summary_display[cols_order]
                st.dataframe(df_summary_display, use_container_width=True, hide_index=True)
                
                csv_export = df_summary_display.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Descargar Resumen", # Translated
                    data=csv_export,
                    file_name=f"resumen_asistencia_diaria_sin_fines_semana_{start_date.strftime('%Y%m%d')}_a_{end_date.strftime('%Y%m%d')}.csv", # Translated filename
                    mime='text/csv',
                    key='download_summary_csv_btn'
                )
            else:
                st.info("No se procesaron datos de asistencia para días laborables en el rango de fechas seleccionado.") # Translated

            # 4. Identify and Display Students Who Never Attended
            st.divider()
            st.subheader("Estudiantes que Nunca Asistieron en las fechas Seleccionadas") # Clarify this includes weekends if data existed
            students_never_attended_list = sorted(list(master_student_list - students_present_in_range))
            
            def create_whatsapp_link(phone: str, message: str) -> str:
                phone = ''.join(filter(str.isdigit, phone))
                encoded_message = urllib.parse.quote(message)
                return f"https://wa.me/{phone}?text={encoded_message}"  

            def create_teams_link(email: str, message: str) -> str:
                encoded_message = urllib.parse.quote(message)
                return f"https://teams.microsoft.com/l/chat/0/0?users={email}&message={encoded_message}"  

            def get_first_name(full_name: str) -> str:
                return full_name.strip().split()[0].capitalize()

            if students_never_attended_list:
                warning_msg = f"{len(students_never_attended_list)} estudiante(s) no tuvieron registros de 'Presente' en este período:"
                st.warning(warning_msg)
                
                # Get student data with start dates
                try:
                    students_last_updated = get_last_updated('students')
                    all_students_df, _ = load_students(students_last_updated)
                except Exception as e:
                    st.error(f"Error loading student data: {str(e)}")
                    all_students_df = pd.DataFrame()
                
                # Create DataFrame for display with start dates
                never_attended_data = []
                for student_name in students_never_attended_list:
                    start_date = get_student_start_date(all_students_df, student_name)
                    phone = get_student_phone(all_students_df, student_name)
                    email = get_student_email(all_students_df, student_name)
                    student_name_only = get_first_name(student_name)
            
                    if phone:
                        message = f"Hola {student_name_only}, notamos que no has asistido a clases. ¿Todo está bien? Por favor contáctanos."
                        whatsapp_link = create_whatsapp_link(phone, message)
                    else:
                        whatsapp_link = '#'

                    if email:
                        message = f"Hola {student_name_only}, notamos que no has asistido a clases. ¿Todo está bien? Por favor contáctanos."
                        teams_link = create_teams_link(email, message)
                    else:
                        teams_link = '#'
        
                    never_attended_data.append({
                        'Nombre': student_name.strip(),
                        'Inicio': start_date,
                        'Teléfono': phone or 'No disponible',
                        'Email': email or 'No disponible',
                        'WhatsApp': whatsapp_link,
                        'Teams': teams_link
                    })

                df_never_attended = pd.DataFrame(never_attended_data)

                # Create a copy of the DataFrame without the email column for display
                display_columns = [col for col in df_never_attended.columns if col != 'Email']
                df_display = df_never_attended[display_columns].copy()

                # Use st.dataframe for better display
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'WhatsApp': st.column_config.LinkColumn(width="small", display_text="Contactar"),
                        'Teams': st.column_config.LinkColumn(width="small", display_text="Contactar")
                    }
                )
                # Create CSV download
                try:
                    # Remove only the WhatsApp and Teams columns, keep email and phone
                    df_export = df_never_attended.drop(columns=['WhatsApp', 'Teams'], errors='ignore')
                    
                    # Convertir a CSV
                    csv_never_attended = df_export.to_csv(index=False, encoding='utf-8-sig')
                    
                    # Crear nombre de archivo con el rango de fechas
                    date_suffix = create_filename_date_range(start_date, end_date)
                    filename = f"nunca_asistieron{date_suffix}.csv"
                    
                    st.download_button(
                        label="Descargar Lista de Estudiantes que Nunca Asistieron",
                        data=csv_never_attended,
                        file_name=filename,
                        mime='text/csv; charset=utf-8-sig',
                        key='download_never_attended_csv_btn',
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"Error creating download file: {str(e)}")

                    # Intento de respaldo sin fecha
                    try:
                        # Remove only the WhatsApp and Teams columns, keep email and phone
                        df_export = df_never_attended.drop(columns=['WhatsApp', 'Teams'], errors='ignore')
                        
                        csv_never_attended = df_export.to_csv(index=False, encoding='utf-8-sig')
                        
                        st.download_button(
                            label="Descargar Lista de Estudiantes que Nunca Asistieron",
                            data=csv_never_attended,
                            file_name="nunca_asistieron.csv",
                            mime='text/csv; charset=utf-8-sig',
                            key='download_never_attended_csv_btn_fallback',
                            type="primary"
                        )
                    except Exception as fallback_e:
                        st.error(f"Error creating fallback download: {str(fallback_e)}")

            else:
                st.success("Todos los estudiantes registrados asistieron al menos una vez en el rango de fechas seleccionado (considerando todos los días).")

else:
    st.warning("No se encontraron registros de asistencia")
    st.stop()
