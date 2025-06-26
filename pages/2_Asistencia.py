import streamlit as st
import pandas as pd
import datetime
import re
import io
import time
from utils import save_attendance, load_students, delete_attendance_dates, get_attendance_dates, get_last_updated
from config import setup_page, db

# --- Session Check ---
# This block now checks for both login status AND a valid session structure
# required by the authentication utility functions.
if (
    not st.session_state.get("logged_in")
    or "token_expires_at" not in st.session_state
    or st.session_state.get("token_expires_at") is None
):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Si el problema persiste, es posible que su sesión anterior haya caducado. Por favor, regrese a la página de Login y vuelva a iniciar sesión.")
    st.stop()
# --- End Session Check ---

setup_page("Gestión de Asistencia")

SPANISH_DAY_NAMES = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo"
}

if 'attendance_data' not in st.session_state:
    st.session_state.attendance_data = {
        'last_updated': None,
        'dates': [],
        'records': {}
    }
if 'processed_files_this_session' not in st.session_state:
    st.session_state.processed_files_this_session = set()
if 'uploader_key_suffix' not in st.session_state:
    st.session_state.uploader_key_suffix = 0
if 'current_batch_data_by_date' not in st.session_state:
    st.session_state.current_batch_data_by_date = {}
if 'prepared_attendance_dfs' not in st.session_state:
    st.session_state.prepared_attendance_dfs = {}
if 'last_uploaded_files' not in st.session_state:
    st.session_state.last_uploaded_files = None
if 'show_delete_all_dialog' not in st.session_state:
    st.session_state.show_delete_all_dialog = False
if 'show_delete_selected_dialog' not in st.session_state:
    st.session_state.show_delete_selected_dialog = False
if 'show_edit_dialog' not in st.session_state:
    st.session_state.show_edit_dialog = False
if 'to_delete' not in st.session_state:
    st.session_state.to_delete = []
if 'edit_dates_list' not in st.session_state:
    st.session_state.edit_dates_list = []

def update_attendance_session_state():
    attendance_last_updated = get_last_updated('attendance', st.session_state.email)
    
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

def extract_date_from_filename(filename: str) -> datetime.date | None:
    patterns = [
        r'(Informe de Asistencia )',
        r'(Attendance report )'
    ]
    for pattern in patterns:
        match_keyword = re.search(pattern, filename, re.IGNORECASE)
        if match_keyword:
            date_str_candidate = filename[match_keyword.end():]
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

def reset_dialog_states():
    st.session_state.show_delete_all_dialog = False
    st.session_state.show_delete_selected_dialog = False
    st.session_state.show_edit_dialog = False

# Define the callback function that will be executed ONLY when the button is clicked
def prepare_edit_dialog(selected_dates):
    """Sets the session state required to open the edit dialog."""
    if not selected_dates:
        st.warning("Por favor seleccione al menos una fecha para editar.")
        return
    reset_dialog_states()
    st.session_state.edit_dates_list = selected_dates
    st.session_state.show_edit_dialog = True

@st.dialog("Editar Asistencia")
def edit_selected_dialog():
    if not st.session_state.get('edit_dates_list'):
        st.warning("No hay fechas seleccionadas para editar.")
        if st.button("Cerrar"):
            st.session_state.show_edit_dialog = False
            st.rerun()
        return

    selected_date_str = st.selectbox(
        "Seleccione la fecha que desea editar:",
        options=st.session_state.edit_dates_list,
        index=0,
        key="edit_dialog_selectbox"
    )

    if not selected_date_str:
        st.stop()

    date_key = datetime.datetime.strptime(selected_date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
    students_last_updated = get_last_updated('students')
    students_df_master, _ = load_students(students_last_updated)

    if students_df_master is None or students_df_master.empty:
        st.error("Lista de estudiantes no encontrada. Por favor, súbala en la página de 'Gestión de Estudiantes'.")
        if st.button("Cerrar"):
            st.session_state.show_edit_dialog = False
            st.rerun()
        return

    # 1. Get the raw attendance data for the date, which could be a list or a dict.
    saved_attendance_raw = st.session_state.attendance_data['records'].get(date_key, {})
    
    # 2. Standardize the data into a single dictionary format: {student_id: status}
    attendance_lookup = {}
    if isinstance(saved_attendance_raw, list):
        # This handles the old format from file uploads: a list of {'Nombre': ..., 'Presente': ...}
        # We need a quick way to look up a student's ID from their name.
        name_to_id_map = {row['nombre']: str(idx) for idx, row in students_df_master.iterrows()}
        for record in saved_attendance_raw:
            student_name = record.get('Nombre')
            student_id = name_to_id_map.get(student_name)
            if student_id:
                status = 'presente' if record.get('Presente', False) else 'ausente'
                attendance_lookup[student_id] = status
    elif isinstance(saved_attendance_raw, dict):
        # This handles the correct format: a dictionary of {student_id: status}
        attendance_lookup = saved_attendance_raw
    
    edit_records = []
    for index, student_row in students_df_master.iterrows():
        student_id = str(index) 
        student_name = student_row['nombre']
        
        # Now we use our standardized `attendance_lookup` dictionary, which is guaranteed to work.
        status = attendance_lookup.get(student_id, 'ausente') 
        is_present = (status == 'presente' if isinstance(status, str) else bool(status))
        edit_records.append({'ID': student_id, 'Nombre': student_name, 'Presente': is_present})

    if not edit_records:
        st.warning("No se pudieron construir los registros de edición.")
        if st.button("Cerrar"):
            st.session_state.show_edit_dialog = False
            st.rerun()
        return
        
    edit_df = pd.DataFrame(edit_records)
    st.markdown(f"**Editando asistencia para el {selected_date_str}**")
    
    edit_df_no_id = edit_df.drop(columns=["ID"])
    edited_df_in_dialog = st.data_editor(
        edit_df_no_id,
        column_config={
            'Nombre': st.column_config.TextColumn('Nombre del Estudiante', disabled=True),
            'Presente': st.column_config.CheckboxColumn('¿Presente?')
        },
        hide_index=True,
        key=f'attendance_editor_dialog_{date_key}'
    )


    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Guardar Cambios", type="primary"):
            try:
                updated_records_for_db = edited_df_in_dialog.to_dict('records')

                date_obj = datetime.datetime.strptime(date_key, '%Y-%m-%d').date()
                if save_attendance(date_obj, updated_records_for_db):
                    st.session_state.attendance_data['records'][date_key] = updated_records_for_db
                    st.session_state.attendance_data['last_updated'] = datetime.datetime.now().isoformat()
                    st.toast("¡Cambios guardados!", icon="✅")
                    time.sleep(1)
                    
                    
                else:
                    st.error("Error al guardar los cambios.")
            except Exception as e:
                st.error(f"Ocurrió un error al guardar: {str(e)}")

    with col2:
        if st.button("❌ Cerrar Editor"):
            st.session_state.show_edit_dialog = False
            st.session_state.edit_dates_list = []
            st.rerun()

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
                    st.session_state.current_batch_data_by_date = {}
                    st.session_state.prepared_attendance_dfs = {}
                    st.session_state.processed_files_this_session = set()
                    st.session_state.uploader_key_suffix += 1
                    st.session_state.attendance_data = {'last_updated': None, 'dates': [], 'records': {}}
                    reset_dialog_states()
                    st.success("Todas las asistencias eliminadas exitosamente.")
                    st.rerun()
                else:
                    st.error("Error al eliminar las asistencias.")
            except Exception as e:
                st.error(f"Error inesperado al eliminar las asistencias: {str(e)}")
    with col2:
         # When the "Cerrar Editor" button is clicked, we now clean up ALL related session state.
        if st.button("❌ Cerrar Editor"):
            # Set the flag to hide the dialog
            st.session_state.show_edit_dialog = False
            # Clear the list of dates that were selected for editing
            st.session_state.edit_dates_list = []
            # Rerun the script to make the dialog disappear
            st.rerun()
    
attendance_data = update_attendance_session_state()
all_attendance_dates = attendance_data['dates']

if all_attendance_dates:
    st.header("Archivos de Asistencia guardados")
    with st.expander("Ver y editar lista de fechas", expanded=True):
        try:
            dates_df = pd.DataFrame({
                'Día': [SPANISH_DAY_NAMES[datetime.datetime.strptime(d, '%Y-%m-%d').strftime('%A')] for d in all_attendance_dates],
                'Fecha': [datetime.datetime.strptime(d, '%Y-%m-%d').strftime('%m/%d/%Y') for d in all_attendance_dates],
                'Seleccionar': [False] * len(all_attendance_dates)
            })
            dates_df = dates_df[["Seleccionar", "Día", "Fecha"]]
            
            st.info("Marque las casillas para editar o eliminar las asistencias correspondientes.")
            
            edited_df = st.data_editor(
                dates_df,
                column_config={
                    "Seleccionar": st.column_config.CheckboxColumn("Seleccionar", width="small", pinned=True),
                    "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                    "Día": st.column_config.TextColumn("Día", disabled=True, width="small"),
                },
                hide_index=True,
                use_container_width=True,
                key="attendance_dates_selector"
            )
            
            selected_rows = edited_df[edited_df['Seleccionar']]
            
            col1, col2, col3 = st.columns([2, 2, 6])
            with col1:
                if st.button("Eliminar todo", type="primary", use_container_width=True):
                    reset_dialog_states()
                    st.session_state.show_delete_all_dialog = True
                    st.rerun() # Rerun is fine for dialogs that self-manage state.
            
            # This logic now uses the callback
            if not selected_rows.empty:
                selected_dates_list = selected_rows['Fecha'].tolist()
                with col2:
                    if st.button("Eliminar", use_container_width=True):
                        reset_dialog_states()
                        st.session_state.to_delete = selected_dates_list
                        st.session_state.show_delete_selected_dialog = True
                        st.rerun()
                with col3:
                    # Use the on_click callback here. It runs BEFORE the script reruns.
                    # We pass the selected dates as an argument to the callback.
                    st.button(
                        "Editar Seleccionados", 
                        type="secondary", 
                        use_container_width=True,
                        on_click=prepare_edit_dialog,
                        args=(selected_dates_list,)
                    )

        except Exception as e:
            st.error(f"Error al cargar las asistencias: {str(e)}")
else:
    st.info("No hay asistencias registradas.")

if st.session_state.get('show_edit_dialog', False):
    edit_selected_dialog()
elif st.session_state.show_delete_selected_dialog:
    confirm_delete_selected_dialog()
elif st.session_state.show_delete_all_dialog:
    confirm_delete_all_dialog()

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
        tried_encodings_list = ['utf-16', 'utf-8', 'utf-8-sig', 'latin-1', 'cp1252'] 
        try:
            file_content_str = file_bytes.decode('utf-16')
        except UnicodeDecodeError:
            for enc in [e for e in tried_encodings_list if e != 'utf-16']:
                try:
                    file_content_str = file_bytes.decode(enc)
                    break 
                except UnicodeDecodeError:
                    continue
        if file_content_str is None:
            st.error(f"Error al decodificar '{report_file.name}'. Intentados: {', '.join(tried_encodings_list)}.")
            files_skipped_summary[report_file.name] = "Falló la decodificación"
            st.session_state.processed_files_this_session.add(report_file.name)
            continue
        names_from_report = parse_attendance_report(file_content_str, report_file.name)
        if names_from_report:
            st.session_state.current_batch_data_by_date.setdefault(file_date, set()).update(names_from_report)
            files_processed_summary.setdefault(file_date, []).append(report_file.name)
        else:
            st.warning(f"No se pudieron extraer nombres de '{report_file.name}'.")
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

if uploaded_reports and st.session_state.current_batch_data_by_date:
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
                st.info(f"No se generaron registros de asistencia para {date_obj.strftime('%Y-%m-%d')}.")
        
        if st.session_state.prepared_attendance_dfs:
            st.success("Tablas de asistencia preparadas. Proceda al Paso 3.")
            st.rerun()
        else:
            st.warning("No se pudieron preparar tablas de asistencia.")

if st.session_state.prepared_attendance_dfs:
    st.divider()
    st.subheader("Paso 3: Revisar y Guardar Asistencia")
    st.caption("Revise los registros de asistencia abajo. Marque la casilla 'Presente' para los estudiantes que asistieron. Desmarque para los ausentes.")

    dates_with_data = sorted(st.session_state.prepared_attendance_dfs.keys())

    if not dates_with_data:
        st.info("No hay datos de asistencia preparados para mostrar.")
    else:
        if st.button("💾 Guardar Todos los Reportes", type="primary", key="save_all_reports"):
            save_success = True
            saved_count = 0
            for date_obj, df in st.session_state.prepared_attendance_dfs.items():
                date_str = date_obj.strftime('%Y-%m-%d')
                attendance_data_to_save = df.to_dict('records')
                if save_attendance(date_obj, attendance_data_to_save):
                    saved_count += 1
                else:
                    save_success = False
                    st.error(f"Error al guardar la asistencia para {date_str}.")
            if save_success and saved_count > 0:
                st.toast("¡Informes guardados exitosamente!", icon="✅")
                st.success(f"¡Se guardaron exitosamente {saved_count} reporte(s) de asistencia!")
                st.balloons()
                update_attendance_session_state()
                st.session_state.current_batch_data_by_date = {}
                st.session_state.prepared_attendance_dfs = {}
                st.session_state.processed_files_this_session = set()
                st.session_state.uploader_key_suffix += 1
                time.sleep(3)
                st.rerun()
            elif saved_count == 0:
                st.warning("No se pudo guardar ningún reporte. Por favor intente de nuevo.")

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
                key=f"attendance_editor_upload_{selected_date_str}"
            )
            st.session_state.prepared_attendance_dfs[selected_date_obj] = edited_df

            col1, col2, _ = st.columns([2, 3, 2])
            with col1:
                if st.button(f"💾 Guardar {selected_date_str}", key=f"save_{selected_date_str}"):
                    attendance_data_to_save = edited_df.to_dict('records')
                    if save_attendance(selected_date_obj, attendance_data_to_save):
                        update_attendance_session_state()
                        st.success(f"¡Asistencia guardada exitosamente para {selected_date_str}!")
                        del st.session_state.prepared_attendance_dfs[selected_date_obj]
                        st.rerun()
                    else:
                        st.error(f"Error al guardar asistencia para {selected_date_str}.")
            with col2:
                if st.button("🗑️ Limpiar Ficheros Cargados"):
                    st.session_state.current_batch_data_by_date = {}
                    st.session_state.prepared_attendance_dfs = {}
                    st.session_state.processed_files_this_session = set()
                    st.session_state.uploader_key_suffix += 1
                    st.rerun()
            st.markdown("---")
        else:
            st.warning("La fecha seleccionada ya no tiene datos preparados. Por favor, recargue o seleccione otra fecha.")