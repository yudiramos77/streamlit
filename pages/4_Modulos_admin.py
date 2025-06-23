import streamlit as st
import pandas as pd
from config import setup_page
from utils_admin import delete_module_from_db, update_module_to_db, admin_get_student_group_emails, save_new_module_to_db, admin_get_available_modules, load_breaks_from_db, parse_breaks, adjust_date_for_breaks, row_to_clean_dict, transform_module_input, sync_firebase_updates
import datetime
import time

# --- Page Setup and Login Check ---
setup_page("Gestión de Módulos por Administrador")
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()

if st.button("Limpiar Sesión"):
    st.session_state.modules_df_by_course = {}
    st.session_state.editor_key = 0
    st.session_state.force_refresh = False
    st.success("Sesión borrada. Recargando...")
    st.rerun()

# --- Initialize session state variables at the very top ---
# This ensures they exist before any part of the script tries to access them.
if 'editor_key' not in st.session_state:
    st.session_state.editor_key = 0
if 'modules_df_by_course' not in st.session_state:
    st.session_state.modules_df_by_course = {} # This will store DataFrames per course
if 'force_refresh' not in st.session_state:
    st.session_state.force_refresh = False
if 'modules_date_updates' not in st.session_state:
    st.session_state.modules_date_updates = {}
# --- End Initialize session state variables ---


date_updates = st.session_state.get("modules_date_updates", {})

if date_updates:
    for course_email, course_data in date_updates.items():
        for firebase_key, module_data in course_data.items():
            if firebase_key is not None:
                update_module_to_db(course_email, firebase_key, {
                    'fecha_inicio_1': module_data['Fecha Inicio'].strftime('%Y-%m-%d'),
                    'fecha_fin_1': module_data['Fecha Fin'].strftime('%Y-%m-%d')
                })
           
    st.session_state.modules_date_updates = {} # Reset the cache after updating Firebase


# --- Select Course ---
st.subheader("1. Seleccionar Curso")

# Get available courses (emails)
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

    modules_selected_course = st.selectbox(
        "Seleccione un Curso para agregar a los nuevos módulos:",
        options=full_emails_for_options,
        format_func=lambda x: course_options[x]['label'],
        index=0,
        key="course_selector" # Added key for consistency
    )

else:
    st.warning("No se encontraron cursos disponibles.")
    modules_selected_course = None # Ensure it's explicitly None if no courses


def calculate_dates(start_date):
    breaks_data = load_breaks_from_db()
    # print("\n\nbreaks_data", breaks_data)
    breaks = parse_breaks(breaks_data)
    # print("\n\nbreaks", breaks)
    # Ensure start_date is a date object for comparison
    if hasattr(start_date, 'date'):
        start_date = start_date.date()
    adjusted_start = adjust_date_for_breaks(start_date, breaks)
    # Convert back to datetime for consistency with the rest of the app
    if isinstance(adjusted_start, datetime.date):
        return pd.Timestamp(adjusted_start)
    return adjusted_start

def is_missing_firebase_key(val):
    return pd.isna(val) or val in ["", "None", None]

# --- Select Module ---
if modules_selected_course: # Only show module selection if a course is selected
    st.divider()
    st.subheader("2. Seleccionar Módulo")
    st.info("Para guardar los cambios una vez que modifique la tabla de módulos, presione el botón 'Guardar Cambios'. Los campos Nombre de Modulo, Duración y Orden son obligatorios.")

try:
    # st.write("\n\nmodules_selected_course----->> ", modules_selected_course)
    
    # Initialize module_options to None
    module_options = None
    
    # Check if we have data in session state first
    if modules_selected_course in st.session_state.modules_df_by_course:
        module_options = st.session_state.modules_df_by_course[modules_selected_course]
        # print("\n\nmodule_options from session state\n\n ----- ", module_options)
    
    # If no data in session state, fetch from database
    if module_options is None or (isinstance(module_options, (pd.DataFrame, list, dict)) and len(module_options) == 0):
        module_data = admin_get_available_modules(modules_selected_course)
        if module_data is not None and ((isinstance(module_data, pd.DataFrame) and not module_data.empty) or 
                                       (isinstance(module_data, (list, dict)) and len(module_data) > 0)):
            module_options = module_data
            # print("\n\nmodule_options from db\n\n ----- ", module_options)
    
    # If we have valid module_options, process them
    if module_options is not None and ((isinstance(module_options, pd.DataFrame) and not module_options.empty) or 
                                     (isinstance(module_options, (list, dict)) and len(module_options) > 0)):
        # Convert to DataFrame if it's not already one and sort by 'Orden'
        df = (module_options if isinstance(module_options, pd.DataFrame) 
              else pd.DataFrame(module_options))

        # Sort by 'credits' if it exists
        if 'credits' in df.columns:
            df = df.sort_values('credits', ascending=True).reset_index(drop=True)

        # st.write("\n\nAvailable columns in module data:", df.columns.tolist())

        # Define your primary column mapping for known columns
        column_mapping = {
            'module_name': 'Nombre Módulo',
            'module_id': 'ID Módulo',
            'ciclo': 'Ciclo',
            'start_date': 'Fecha Inicio',
            'end_date': 'Fecha Fin',
            'duration_weeks': 'Duración',
            'credits': 'Orden',
            'description': 'Descripción',
            'firebase_key': 'firebase_key'
        }

        # Dynamically create display_columns to include ALL columns present in the DataFrame
        # and create display names for them.
        display_columns = []
        reverse_display_names = {} # To map display names back to original for saving

        for col in df.columns:
            # Use the mapped name if available, otherwise use the original column name
            display_name = column_mapping.get(col, col)
            display_columns.append(display_name)
            reverse_display_names[display_name] = col # Store reverse mapping

        if not display_columns:
            st.warning("No se encontraron columnas válidas para mostrar.")
            st.json(module_options[0] if module_options else {})  # Show raw data for debugging
            st.stop()

        # Create a copy for display, renaming columns
        # Ensure only columns that exist in df are selected, and then rename them
        display_df = df.rename(columns=column_mapping)[display_columns].copy()
        
        # Hide specific columns from display
        columns_to_hide = ["Ciclo", "label", "ID Módulo"]  # Add any other columns you want to hide here
        display_df = display_df.drop(columns=[col for col in columns_to_hide if col in display_df.columns])
        
        # Convert date columns from string to datetime
        date_columns = ["Fecha Inicio", "Fecha Fin"]
        for date_col in date_columns:
            if date_col in display_df.columns:
                display_df[date_col] = pd.to_datetime(display_df[date_col], errors='coerce')

        # Define column configurations for st.data_editor
        editor_column_config = {
            "ID Módulo": st.column_config.TextColumn(disabled=True),
            "Fecha Inicio": st.column_config.DateColumn(format="MM/DD/YYYY"),
            "Fecha Fin": st.column_config.DateColumn(format="MM/DD/YYYY"),
            "Duración": st.column_config.NumberColumn(min_value=1, step=1),
            "Orden": st.column_config.NumberColumn(min_value=1, step=1),
            "Descripción": st.column_config.TextColumn(),
            "firebase_key": st.column_config.TextColumn(disabled=True) 
        }

        # Initialize session state for this course if not exists OR if force refresh is needed
        if (modules_selected_course not in st.session_state.modules_df_by_course or 
            st.session_state.force_refresh):
            # Sort the DataFrame by 'Orden' column
            st.session_state.modules_df_by_course[modules_selected_course] = display_df.copy()
            st.session_state.force_refresh = False  # Reset force refresh flag

        # st.write("Editar módulos:")
        
        # Create a unique key that changes when we need to force refresh
        editor_key = f"main_editor_{modules_selected_course}_{st.session_state.editor_key}"
        # And when preparing the DataFrame for display, ensure firebase_key exists
        if 'firebase_key' not in df.columns:
            df['firebase_key'] = '' 
        
        # Use the session state version for the editor
        edited_df = st.data_editor(
            st.session_state.modules_df_by_course[modules_selected_course],
            use_container_width=True,
            num_rows="dynamic",
            column_config=editor_column_config,
            key=editor_key
        )
       
        # Add save button

        first_row = edited_df.iloc[0]
        last_row = edited_df.iloc[-1]
        # Check if all required fields are filled (using pd.notna for proper NaT handling)
        if all(pd.notna(last_row[col]) for col in ['Duración', 'Orden']):
            
            # recalculate dates    
            if st.button("Recalcular las fechas", key="recalcular_fechas"):
                today = pd.Timestamp.today().normalize()

                # Encuentra el módulo que contiene la fecha de hoy
                module_with_today = edited_df[
                    (edited_df['Fecha Inicio'].notna()) &
                    (edited_df['Fecha Fin'].notna()) &
                    (edited_df['Fecha Inicio'] <= today) &
                    (edited_df['Fecha Fin'] >= today)
                ]

                if not module_with_today.empty:
                    current_index = module_with_today.index[0]
                    current_order = edited_df.loc[current_index, 'Orden']
                    # print(f"Hoy cae en el módulo con orden {current_order}")

                    changed_rows = {}
                    last_date_used = None

                    # 👉 Recalcula fechas hacia adelante desde el módulo actual
                    for index, row in edited_df[edited_df['Orden'] >= current_order].sort_values('Orden').iterrows():
                        if pd.notna(row['Duración']):
                            if last_date_used is None:
                                new_start_date = calculate_dates(row['Fecha Inicio'])
                            else:
                                new_start_date = calculate_dates(last_date_used + pd.DateOffset(days=1))

                            new_end_date = new_start_date + pd.DateOffset(weeks=row['Duración']) - pd.DateOffset(days=1)

                            old_start = edited_df.loc[index, 'Fecha Inicio']
                            old_end = edited_df.loc[index, 'Fecha Fin']

                            if pd.Timestamp(new_start_date) != pd.Timestamp(old_start) or pd.Timestamp(new_end_date) != pd.Timestamp(old_end):
                                edited_df.loc[index, 'Fecha Inicio'] = new_start_date
                                edited_df.loc[index, 'Fecha Fin'] = new_end_date
                                firebase_key = edited_df.loc[index, 'firebase_key']
                                changed_rows.setdefault(modules_selected_course, {})[firebase_key] = {
                                    'Fecha Inicio': new_start_date,
                                    'Fecha Fin': new_end_date
                                }

                            last_date_used = new_end_date

                    # 🔁 Recalcula módulos anteriores al módulo actual si están en el pasado
                    for index, row in edited_df[edited_df['Orden'] < current_order].sort_values('Orden').iterrows():
                        if pd.notna(row['Duración']) and last_date_used is not None:
                            new_start_date = calculate_dates(last_date_used + pd.DateOffset(days=1))
                            new_end_date = new_start_date + pd.DateOffset(weeks=row['Duración']) - pd.DateOffset(days=1)

                            old_start = edited_df.loc[index, 'Fecha Inicio']
                            old_end = edited_df.loc[index, 'Fecha Fin']

                            if pd.Timestamp(new_start_date) != pd.Timestamp(old_start) or pd.Timestamp(new_end_date) != pd.Timestamp(old_end):
                                edited_df.loc[index, 'Fecha Inicio'] = new_start_date
                                edited_df.loc[index, 'Fecha Fin'] = new_end_date
                                firebase_key = edited_df.loc[index, 'firebase_key']
                                changed_rows.setdefault(modules_selected_course, {})[firebase_key] = {
                                    'Fecha Inicio': new_start_date,
                                    'Fecha Fin': new_end_date
                                }

                            last_date_used = new_end_date

                    # Guarda cambios
                    st.session_state.modules_df_by_course[modules_selected_course] = edited_df
                    st.session_state.modules_date_updates = changed_rows

                    # print(f"\n\nFinal result:\n{edited_df}")
                    st.rerun()
                else:
                    st.warning("No se encontró ningún módulo correspondiente al día actual.")

            # end date calculation
            if all(pd.notna(last_row[col]) for col in ['Fecha Inicio', 'Fecha Fin', 'Duración', 'Orden']):
                if st.button("💾 Guardar Cambios"):
                    

                    # for key, updates in date_updates.items():
                    #     idx = edited_df.index[edited_df['firebase_key'] == key]
                    #     if not idx.empty:
                    #         for field, value in updates.items():
                    #             edited_df.loc[idx, field] = value
                    
                    # Renombrar columnas visibles a nombres de base de datos
                    edited_df_for_save = edited_df.rename(columns=reverse_display_names)
                    old_df = st.session_state.modules_df_by_course[modules_selected_course]
                    new_df = edited_df_for_save.copy()

                    old_keys = set(old_df["firebase_key"].dropna().astype(str))
                    new_keys = set(new_df["firebase_key"].dropna().astype(str))

                    # Detectar filas nuevas (sin firebase_key)
                    new_rows = new_df[new_df["firebase_key"].apply(is_missing_firebase_key)]

                    # Guardar filas nuevas
                    for _, row in new_rows.iterrows():
                        clean = row_to_clean_dict(row)
                        data = transform_module_input(clean)
                        firebase_key = save_new_module_to_db(modules_selected_course, data)

                        # Update the end date of the last module
                        max_order = edited_df.loc[~edited_df.index.isin(new_rows.index), 'Orden'].max()
                        max_order_module = edited_df.loc[edited_df['Orden'] == max_order].squeeze()
                        fecha_fin = max_order_module['Fecha Fin']
                        if pd.notna(fecha_fin):
                            fecha_fin = fecha_fin + pd.DateOffset(days=1)
                            # print(f"\n\nFecha fin del módulo con mayor orden que no es el actual (ID: {firebase_key}): {fecha_fin}")
                            # data["Fecha Fin"] = fecha_fin
                        

                        if firebase_key:
                            new_df.loc[row.name, "firebase_key"] = firebase_key
                            st.session_state.modules_df_by_course[modules_selected_course] = new_df.copy()
                            st.success(f"Módulo nuevo guardado con ID: {firebase_key}")
                            st.session_state.editor_key += 1
                            time.sleep(1)
                            st.rerun()

                    # 🔁 Detectar y guardar filas modificadas
                    common_keys = old_keys & new_keys
                    for key in common_keys:
                        old_row = old_df[old_df["firebase_key"] == key].squeeze()
                        new_row = new_df[new_df["firebase_key"] == key].squeeze()

                        # Comparamos los valores excepto firebase_key
                        if not old_row.drop(labels=["firebase_key"]).equals(new_row.drop(labels=["firebase_key"])):
                            clean = row_to_clean_dict(new_row)
                            data = transform_module_input(clean)
                            update_module_to_db(modules_selected_course, key, data)

                            st.success(f"Modulo con ID {key} actualizado.")
                            st.session_state.modules_df_by_course[modules_selected_course] = new_df.copy()
                            st.session_state.editor_key += 1
                            time.sleep(1)
                            st.rerun()

                    # 🗑️ Detectar y eliminar filas eliminadas   
                    deleted_keys = old_keys - new_keys
                    for key in deleted_keys:
                        try:
                            delete_module_from_db(modules_selected_course, key)   
                            # print(f"Nuevo DataFrame: {new_df[new_df["firebase_key"] != key]}")   
                            new_df = new_df[new_df["firebase_key"] != key]
                            st.session_state.modules_df_by_course[modules_selected_course] = new_df.copy()                     
                            st.success(f"Módulo con ID {key} eliminado de la base de datos.")
                            st.session_state.editor_key += 1
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar el módulo con ID {key}: {str(e)}")
                    
    else:
        st.info("No hay módulos disponibles. Por favor, agregue módulos.") # Keep this message
except Exception as e:
    st.error(f"Error al cargar o procesar los módulos: {str(e)}")