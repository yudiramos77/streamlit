import streamlit as st
import pandas as pd
import datetime
import re
import io
import time
from utils import save_attendance, load_students, delete_attendance_dates, get_attendance_dates, get_last_updated
from config import setup_page, db

# Initialize session state for login if it doesn't exist
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- Login Check ---
if not st.session_state.logged_in:
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()
# --- End Login Check ---

# Setup page title (now that config is done and user is logged in)
setup_page("Gestión de Asistencia")

# --- Session State Initialization ---
if 'attendance_data' not in st.session_state:
    st.session_state.attendance_data = {
        'last_updated': None,
        'dates': [],
        'records': {}
    }

if 'processed_files_this_session' not in st.session_state:
    st.session_state.processed_files_this_session = set()
    st.session_state.uploader_key_suffix = 0  # Initialize as integer
    st.session_state.current_batch_data_by_date = {}
    st.session_state.prepared_attendance_dfs = {}
    st.session_state.last_uploaded_files = None  # Track last uploaded files

def update_attendance_session_state():
    """Update the session state with the latest attendance data from the database"""
    attendance_last_updated = get_last_updated('attendance', st.session_state.email)
    
    # Only fetch from DB if our local copy is stale or doesn't exist
    if (st.session_state.attendance_data['last_updated'] != attendance_last_updated or 
            not st.session_state.attendance_data['dates']):
        try:
            user_email = st.session_state.email.replace('.', ',')
            all_dates = db.child("attendance").child(user_email).get(token=st.session_state.user_token).val() or {}
            
            st.session_state.attendance_data = {
                'last_updated': attendance_last_updated,
                'dates': sorted(all_dates.keys(), reverse=True),
                'records': all_dates
            }
        except Exception as e:
            st.error(f"Error updating attendance data: {str(e)}")
    return st.session_state.attendance_data

if 'current_batch_data_by_date' not in st.session_state:
    st.session_state.current_batch_data_by_date = {}

if 'prepared_attendance_dfs' not in st.session_state:
    st.session_state.prepared_attendance_dfs = {}

if 'processed_files_this_session' not in st.session_state:
    st.session_state.processed_files_this_session = set()

# Initialize dialog states
if 'show_delete_all_dialog' not in st.session_state:
    st.session_state.show_delete_all_dialog = False

if 'show_delete_selected_dialog' not in st.session_state:
    st.session_state.show_delete_selected_dialog = False

if 'to_delete' not in st.session_state:
    st.session_state.to_delete = []

# --- Helper Functions ---
def extract_date_from_filename(filename: str) -> datetime.date | None:
    # Define patterns to match
    patterns = [
        r'(Informe de Asistencia )',
        r'(Attendance report )'
    ]

    for pattern in patterns:
        match_keyword = re.search(pattern, filename, re.IGNORECASE)
        if match_keyword:
            # Get the part after the matched keyword
            date_str_candidate = filename[match_keyword.end():]

            # Look for date pattern at the start
            match_date = re.match(r'(\d{1,2})-(\d{1,2})-(\d{2})', date_str_candidate)
            if match_date:
                month, day, year_short = map(int, match_date.groups())
                year = 2000 + year_short
                try:
                    return datetime.date(year, month, day)
                except ValueError:
                    return None
    return None


def parse_attendance_report(file_content_str: str, filename_for_debug: str) -> list:
    lines = file_content_str.splitlines()
    start_marker_found_at = -1
    end_marker_found_at = -1

    for i, line in enumerate(lines):
        line_stripped_lower = line.strip().lower()
        if line_stripped_lower.startswith("2. participants"):
            start_marker_found_at = i
            continue 
        if start_marker_found_at != -1 and line_stripped_lower.startswith("3. in-meeting activities"):
            end_marker_found_at = i
            break 

    if start_marker_found_at == -1:
        st.warning(f"No se pudo encontrar el marcador de sección '2. Participants' en '{filename_for_debug}'.")
        return []

    actual_data_start_index = start_marker_found_at + 1
    actual_data_end_index = end_marker_found_at if end_marker_found_at != -1 else len(lines)

    participant_data_lines = lines[actual_data_start_index : actual_data_end_index]

    if not participant_data_lines:
        st.warning(f"No se encontraron líneas de datos entre '2. Participantes' y '3. Actividades en la reunión' (o fin de archivo) en '{filename_for_debug}'.")
        return []

    header_row_index_in_block = -1
    for i, line_in_block in enumerate(participant_data_lines):
        line_norm = line_in_block.strip().lower()
        if "name" in line_norm and ("first join" in line_norm or "last leave" in line_norm or "email" in line_norm or "duration" in line_norm):
            header_row_index_in_block = i
            break
    if header_row_index_in_block == -1:
        st.warning(f"No se pudo encontrar la fila de encabezado en el archivo: {filename_for_debug}")
        return []

    csv_like_data_for_pandas = "\n".join(participant_data_lines[header_row_index_in_block:])
    
    try:
        df = pd.read_csv(io.StringIO(csv_like_data_for_pandas), sep='\t')
        df.columns = [col.strip().lower() for col in df.columns] 
        
        if "name" in df.columns:
            return df["name"].astype(str).str.strip().unique().tolist()
        else:
            st.warning(f"Columna 'nombre' no encontrada después del análisis en '{filename_for_debug}'. Columnas encontradas: {df.columns.tolist()}")
            return []
    except pd.errors.EmptyDataError:
        st.warning(f"No se pudieron analizar filas de datos del contenido CSV en '{filename_for_debug}'. El encabezado identificado podría haber sido la última línea o los datos estaban vacíos.")
        return []
    except Exception as e:
        st.error(f"Error analizando datos CSV de la sección 'Participantes' de '{filename_for_debug}': {e}")
        return []

# --- Dialog Functions ---
def reset_dialog_states():
    """Reset all dialog states to ensure only one can be open at a time"""
    st.session_state.show_delete_all_dialog = False
    st.session_state.show_delete_selected_dialog = False

@st.dialog("Confirmar eliminación")
def confirm_delete_selected_dialog():
    if 'to_delete' not in st.session_state or not st.session_state.to_delete:
        st.warning("No hay asistencias seleccionadas para eliminar.")
        reset_dialog_states()
        st.rerun()
        return
        
    count = len(st.session_state.to_delete)
    st.write(
        f"¿Está seguro que desea eliminar las {count} asistencias seleccionadas? "
        "**Esta acción no se puede deshacer.**"
    )
    
    col1, col2, _ = st.columns([3, 3, 3])
    
    with col1:
        if st.button("✅ Sí, eliminar", type="primary"):
            try:
                if delete_attendance_dates(st.session_state.to_delete):
                    # Update session state
                    for date_str in st.session_state.to_delete:
                        try:
                            date_key = datetime.datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
                            if date_key in st.session_state.attendance_data['records']:
                                del st.session_state.attendance_data['records'][date_key]
                                st.session_state.attendance_data['dates'].remove(date_key)
                        except ValueError:
                            continue
                    
                    st.session_state.uploader_key_suffix += 1
                    st.session_state.to_delete = []
                    reset_dialog_states()
                    st.success("Asistencias eliminadas exitosamente.")
                    st.rerun()
                else:
                    st.error("Error al eliminar las asistencias seleccionadas.")
            except Exception as e:
                st.error(f"Error inesperado al eliminar asistencias: {str(e)}")
    
    with col2:
        if st.button("❌ Cancelar"):
            reset_dialog_states()
            st.rerun()

@st.dialog("Confirmar eliminación total")
def confirm_delete_all_dialog():
    st.write(
        "¿Está seguro que desea eliminar TODAS las asistencias? "
        "**Esta acción no se puede deshacer.**"
    )
    
    col1, col2, _ = st.columns([4, 3, 3])
    
    with col1:
        if st.button("✅ Sí, eliminar todo", type="primary"):
            try:
                if delete_attendance_dates(delete_all=True):
                    # Clear all relevant session state variables
                    st.session_state.current_batch_data_by_date = {}
                    st.session_state.prepared_attendance_dfs = {}
                    st.session_state.processed_files_this_session = set()
                    st.session_state.uploader_key_suffix += 1
                    st.session_state.attendance_data = {
                        'last_updated': None,
                        'dates': [],
                        'records': {}
                    }
                    reset_dialog_states()
                    st.success("Todas las asistencias eliminadas exitosamente.")
                    st.rerun()
                else:
                    st.error("Error al eliminar las asistencias.")
            except Exception as e:
                st.error(f"Error inesperado al eliminar las asistencias: {str(e)}")
    
    with col2:
        if st.button("❌ Cancelar"):
            reset_dialog_states()
            st.rerun()
            
# Get attendance data from session state
attendance_data = update_attendance_session_state()
all_attendance = attendance_data['dates']

if all_attendance:
    # --- Main UI --- 
    st.header("Archivos de Asistencia guardados")

    with st.expander("Ver lista de fechas"):
        try:
            # Get all attendance dates            
            if all_attendance:
                # Create a DataFrame with the dates and a delete column
                dates_df = pd.DataFrame({
                    'Fecha': [datetime.datetime.strptime(d, '%Y-%m-%d').strftime('%m/%d/%Y') for d in attendance_data['dates']],
                    'Eliminar': [False] * len(attendance_data['dates'])
                })
                
                # Move 'Eliminar' column to the first position
                dates_df = dates_df[["Eliminar", "Fecha"]]
                
                # Display the data editor
                st.info("Seleccione los ficheros de asistencia a eliminar para eliminar individualmente o Eliminar todo")
                
                edited_df = st.data_editor(
                    dates_df,
                    column_config={
                        "Eliminar": st.column_config.CheckboxColumn("Borrar", width="small", pinned=True),
                        "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="attendance_dates_editor"
                )
                
                # Show the delete buttons
                col1, col2, _ = st.columns([2, 3, 5])
                
                with col1:
                    if st.button("Eliminar todo", type="primary", key="delete_all_btn"):
                        reset_dialog_states()  # Close any other open dialogs
                        st.session_state.show_delete_all_dialog = True
                        st.rerun()
                
                with col2:
                    # Only show delete selected button if any rows are checked
                    if edited_df is not None and 'Eliminar' in edited_df.columns and edited_df['Eliminar'].any():
                        if st.button("Eliminar seleccionados", type="secondary", key="delete_selected_btn"):
                            reset_dialog_states()  # Close any other open dialogs
                            st.session_state.to_delete = edited_df[edited_df['Eliminar']]['Fecha'].tolist()
                            st.session_state.show_delete_selected_dialog = True
                            st.rerun()
            else:
                st.info("No hay asistencias registradas.")
            
        except Exception as e:
            st.error(f"Error al cargar las asistencias: {str(e)}")

    # Show dialogs if needed - only one at a time
    if st.session_state.show_delete_selected_dialog:
        confirm_delete_selected_dialog()
    elif st.session_state.show_delete_all_dialog:
        confirm_delete_all_dialog()

# --- Main UI --- 
st.header("Subir Archivos de Informe de Asistencia")
uploaded_reports = st.file_uploader(
    "Las fechas se detectarán de los nombres de archivo.",
    type=['csv'],
    accept_multiple_files=True,
    key=f"report_uploader_daily_{st.session_state.uploader_key_suffix}",
    on_change=lambda: [
        setattr(st.session_state, 'current_batch_data_by_date', {}),
        setattr(st.session_state, 'prepared_attendance_dfs', {})
    ],
    help="Suba archivos CSV. La fecha se detecta del nombre de archivo (p.ej., '...Attendance Report MM-DD-YY.csv')"
)

if uploaded_reports:
    # Clear previous data if new files are uploaded
    if uploaded_reports != st.session_state.get('last_uploaded_files', []):
        st.session_state.current_batch_data_by_date = {}
        st.session_state.prepared_attendance_dfs = {}
        st.session_state.processed_files_this_session = set()
        st.session_state.last_uploaded_files = uploaded_reports
    
    files_processed_summary = {}
    files_skipped_summary = {}

    for report_file in uploaded_reports:
        if report_file.name in st.session_state.processed_files_this_session:
            continue

        file_date = extract_date_from_filename(report_file.name)

        if not file_date:
            st.warning(f"Omitiendo '{report_file.name}': No se pudo extraer la fecha del nombre del archivo.")
            files_skipped_summary[report_file.name] = "Sin fecha en el nombre del archivo"
            st.session_state.processed_files_this_session.add(report_file.name)
            continue

        file_bytes = report_file.getvalue()
        file_content_str = None
        successful_encoding = None
        tried_encodings_list = ['utf-16', 'utf-8', 'utf-8-sig', 'latin-1', 'cp1252'] 

        try:
            file_content_str = file_bytes.decode('utf-16')
            successful_encoding = 'utf-16'
        except UnicodeDecodeError:
            other_encodings_to_attempt = [enc for enc in tried_encodings_list if enc != 'utf-16']
            for enc in other_encodings_to_attempt:
                try:
                    file_content_str = file_bytes.decode(enc)
                    successful_encoding = enc
                    break 
                except UnicodeDecodeError:
                    continue
        
        if file_content_str is None:
            st.error(f"Error al decodificar '{report_file.name}'. Intentados: {', '.join(tried_encodings_list)}. El archivo podría estar corrupto o en una codificación no soportada.")
            files_skipped_summary[report_file.name] = "Falló la decodificación"
            st.session_state.processed_files_this_session.add(report_file.name)
            continue

        names_from_report = parse_attendance_report(file_content_str, report_file.name)
        
        if names_from_report:
            st.session_state.current_batch_data_by_date.setdefault(file_date, set()).update(names_from_report)
            files_processed_summary.setdefault(file_date, []).append(report_file.name)
        else:
            st.warning(f"No se pudieron extraer nombres de '{report_file.name}' (después de decodificación exitosa). Verifique la lógica del analizador o la estructura del archivo.")
            files_skipped_summary[report_file.name] = "Falló el análisis de nombres"
        
        st.session_state.processed_files_this_session.add(report_file.name)

    if files_processed_summary:
        st.markdown("### ✅ Archivos Procesados Exitosamente")

        for date_obj, filenames in files_processed_summary.items():
            attendee_count = len(st.session_state.current_batch_data_by_date.get(date_obj, set()))
            
            with st.expander(f"{date_obj.strftime('%m/%d/%Y')} — {len(filenames)} archivo(s), {attendee_count} asistentes únicos"):
                col1, col2 = st.columns([1, 3])
                col1.markdown("**Archivos:**")
                for filename in filenames:
                    col2.write(f"📄 {filename}")
    
    if files_skipped_summary:
        st.markdown("**Archivos Omitidos:**")
        for filename, reason in files_skipped_summary.items():
            st.write(f"- {filename}: {reason}")

if not st.session_state.current_batch_data_by_date and not uploaded_reports:
    st.info("Suba archivos de informe de asistencia para comenzar.")
elif not st.session_state.current_batch_data_by_date and uploaded_reports:
    st.info("No se procesaron datos de asistencia de los archivos subidos. Verifique los archivos e inténtelo de nuevo.")

if uploaded_reports:
    if st.session_state.current_batch_data_by_date:
        st.divider()
        st.subheader("Paso 2: Preparar Tablas de Asistencia")
        if st.button("Preparar Tablas de Asistencia para Edición"):
            students_last_updated = get_last_updated('students')
            students_df, _ = load_students(students_last_updated)
            if students_df is None or students_df.empty:
                st.error("No se encontraron datos de estudiantes. Por favor, suba una lista de estudiantes en la página 'Gestión de Estudiantes' primero.")
                st.stop()
            
            student_names_master_list = students_df['nombre'].astype(str).str.strip().tolist()

            for date_obj, names_from_reports_set in st.session_state.current_batch_data_by_date.items():
                normalized_names_from_reports = {name.lower().strip() for name in names_from_reports_set}
                
                attendance_records = []
                for master_name in student_names_master_list:
                    normalized_master_name = master_name.lower().strip()
                    present = normalized_master_name in normalized_names_from_reports
                    attendance_records.append({'Nombre': master_name, 'Presente': present})
                
                if attendance_records:
                    attendance_df = pd.DataFrame(attendance_records)
                    st.session_state.prepared_attendance_dfs[date_obj] = attendance_df
                else:
                    st.info(f"No se generaron registros de asistencia para {date_obj.strftime('%Y-%m-%d')} porque la lista de estudiantes está vacía o no hubo coincidencias.")
            
            if st.session_state.prepared_attendance_dfs:
                st.success("Tablas de asistencia preparadas. Proceda al Paso 3.")
                st.rerun()
            else:
                st.warning("No se pudieron preparar tablas de asistencia. Verifique los datos de los estudiantes y los archivos de reporte.")

    if st.session_state.prepared_attendance_dfs:
        st.divider()
        st.subheader("Paso 3: Revisar y Guardar Asistencia")
        st.caption("Revise los registros de asistencia abajo. Marque la casilla 'Presente' para los estudiantes que asistieron. Desmarque para los ausentes.")

        if not st.session_state.prepared_attendance_dfs:
            st.warning("No hay datos de asistencia preparados para guardar. Vaya al Paso 2 para preparar las tablas de asistencia.")
        else:
            dates_with_data = sorted(st.session_state.prepared_attendance_dfs.keys())

            if not dates_with_data:
                st.info("No hay datos de asistencia preparados para mostrar.")
            else:
                selected_date_str = st.selectbox(
                    "Seleccione una fecha para ver/editar asistencia:",
                    options=[d.strftime('%m/%d/%Y') for d in dates_with_data],
                    index=0
                )
                selected_date_obj = datetime.datetime.strptime(selected_date_str, '%m/%d/%Y').date()

                if selected_date_obj in st.session_state.prepared_attendance_dfs:
                    df_to_edit = st.session_state.prepared_attendance_dfs[selected_date_obj]
                    total_attended = df_to_edit['Presente'].value_counts().get(True, 0)
                    st.markdown(f"#### Asistencia para: {selected_date_obj.strftime('%A, %d de %B de %Y')} ({total_attended} de {len(df_to_edit)})")
                    edited_df = st.data_editor(
                        df_to_edit,
                        column_config={
                            "Nombre": st.column_config.TextColumn("Nombre del Estudiante", disabled=True, width="large"),
                            "Presente": st.column_config.CheckboxColumn("¿Presente?", default=False, width="small")
                        },
                        hide_index=True,
                        key=f"attendance_editor_{selected_date_str}"
                    )
                    st.session_state.prepared_attendance_dfs[selected_date_obj] = edited_df  # Update with edits

                    col1, col2, _ = st.columns([2, 3, 2])
                    with col1:
                        if st.button(f"💾 Guardar {selected_date_str}", key=f"save_{selected_date_str}"):
                            attendance_data_to_save = edited_df.to_dict('records')
                            if save_attendance(selected_date_obj, attendance_data_to_save):
                                # Update session state with new/updated attendance
                                date_key = selected_date_obj.strftime('%Y-%m-%d')
                                attendance_dict = {item['Nombre']: item['Presente'] for item in attendance_data_to_save}
                                
                                if date_key not in st.session_state.attendance_data['records']:
                                    st.session_state.attendance_data['dates'].append(date_key)
                                    st.session_state.attendance_data['dates'].sort(reverse=True)
                                
                                st.session_state.attendance_data['records'][date_key] = attendance_dict
                                st.session_state.attendance_data['last_updated'] = get_last_updated('attendance', st.session_state.email)
                                
                                st.success(f"¡Asistencia guardada exitosamente para {selected_date_str}!")
                                st.rerun()
                            else:
                                st.error(f"Error al guardar asistencia para {selected_date_str}.")
                    with col2:
                        if st.button("🗑️ Limpiar Ficheros Cargados"):
                            st.session_state.current_batch_data_by_date = {}
                            st.session_state.prepared_attendance_dfs = {}
                            st.session_state.processed_files_this_session = set()
                            st.rerun()
                    
                    # Add Save All button at the top
                    if st.button("💾 Guardar Todos los Reportes", type="primary", key="save_all_reports"):
                        save_success = True
                        saved_count = 0
                        
                        for date_obj, df in st.session_state.prepared_attendance_dfs.items():
                            date_str = date_obj.strftime('%Y-%m-%d')
                            attendance_data = df.to_dict('records')
                            if save_attendance(date_obj, attendance_data):
                                saved_count += 1
                            else:
                                save_success = False
                                st.error(f"Error al guardar la asistencia para {date_str}.")
                        
                        if save_success and saved_count > 0:
                            st.toast("¡Informes guardados exitosamente!", icon="✅")
                            st.success(f"¡Se guardaron exitosamente {saved_count} reporte(s) de asistencia!")
                            st.balloons()
                            st.session_state.processed_files_this_session = set()
                            
                            # Add delay to ensure toast is visible before rerun
                            time.sleep(3)  # 3 seconds delay
                            st.rerun()
                        elif saved_count == 0:
                            st.warning("No se pudo guardar ningún reporte. Por favor intente de nuevo.")
                    
                    st.markdown("---")
                else:
                    st.warning("La fecha seleccionada ya no tiene datos preparados. Por favor, recargue o seleccione otra fecha.")