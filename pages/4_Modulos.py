import streamlit as st
import pandas as pd
import datetime
import time
import math
import uuid
from config import setup_page, db
from utils import set_last_updated  
from utils import load_modules

# --- Page Setup and Login Check ---
setup_page("Gestión de Módulos")
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()


def invalidate_cache_and_rerun():
    """Invalida el DataFrame en caché y vuelve a ejecutar la aplicación."""
    if 'modules_df' in st.session_state:
        del st.session_state.modules_df
    st.rerun()

def highlight_current_module(row):
    today = datetime.date.today()
    try:
        start_date = datetime.datetime.strptime(row['Inicio'], '%m/%d/%Y').date()
        end_date = datetime.datetime.strptime(row['Fin'], '%m/%d/%Y').date()
        if start_date <= today <= end_date:
            return ['background-color: #e6f7ff'] * len(row)
    except:
        pass
    return [''] * len(row)

# --- MAIN APP LOGIC ---
user_email = st.session_state.get('email')

if 'modules_df' not in st.session_state:
    st.session_state.modules_df = None

# --- MOSTRAR/EDITAR MÓDULOS EXISTENTES ---
st.divider()
if user_email:
    # st.button("Limpiar Caché", on_click=invalidate_cache_and_rerun)

    print("user_email", user_email)
    print("modules_df", st.session_state.modules_df)

    # Cargar desde la base de datos si el caché está vacío
    if 'modules_df' not in st.session_state or st.session_state.modules_df is None or st.session_state.modules_df.empty:
        with st.spinner("Cargando módulos..."):
            st.session_state.modules_df = load_modules(user_email)
            print("----modules_df recargado", st.session_state.modules_df)
    else:
        print("Caché no está vacío", st.session_state.modules_df)
    
    modules_df = st.session_state.modules_df

    if modules_df is not None and modules_df.empty:
        st.info("No hay módulos existentes. Contacte con el administrador.")
    else:
        st.subheader("Módulos")
        st.info("Los módulos se muestran en orden cronológico, con el módulo actual destacado.")
        modules_df = modules_df.rename(columns={
            'name': 'Nombre', 
            'description': 'Descripción', 
            'credits': 'Orden', 
            'duration_weeks': 'Duración (Semanas)', 
            'fecha_inicio_1': 'Inicio',
            'fecha_fin_1': 'Fin'})
        modules_df = modules_df[['Nombre', 'Descripción', 'Orden', 'Duración (Semanas)', 'Inicio', 'Fin']]
        # Convert 'Inicio' and 'Fin' to datetime
        modules_df['Inicio'] = pd.to_datetime(modules_df['Inicio'], format='%Y-%m-%d', errors='coerce')
        modules_df['Fin'] = pd.to_datetime(modules_df['Fin'], format='%Y-%m-%d', errors='coerce')

        # Sort by actual datetime
        modules_df = modules_df.sort_values('Inicio')

        # Format as strings for display (after sorting)
        for col in ['Inicio', 'Fin']:
            if col in modules_df.columns:
                modules_df[col] = modules_df[col].apply(lambda x: x.strftime('%m/%d/%Y') if pd.notna(x) else '')

        # Ensure correct types for other columns
        modules_df['Orden'] = modules_df['Orden'].astype(int)
        modules_df['Duración (Semanas)'] = modules_df['Duración (Semanas)'].astype(int)

        column_properties = {
            'Duración (Semanas)': 'width: 80px;',  # Adjust the width as needed
            'Orden': 'width: 60px;'  # Also making Orden narrower for consistency
        }

        styled_df = modules_df.style.apply(highlight_current_module, axis=1)
        st.dataframe(styled_df, hide_index=True, use_container_width=True)
        
        # # --- Automatic Recalculation Logic ---
        # breaks_data = load_breaks_from_db()
        # breaks = parse_breaks(breaks_data)
        # today = datetime.date.today()

        # # Find the current module's info (only for Cycle 1)
        # current_module_start, current_module_order, current_module_name = \
        #     find_current_module_info(modules_df, today)

        # recalculate_needed = False
        # recalculation_reason = ""

        # # Get the currently stored dates from modules_df for comparison later
        # current_dates_df = modules_df[['firebase_key', 'fecha_inicio_1', 'fecha_fin_1']].copy()
        # # Convert to string to avoid issues with NaT vs None in comparison
        # for col in ['fecha_inicio_1', 'fecha_fin_1']:
        #     current_dates_df[col] = current_dates_df[col].astype(str)

        # pivot_order_for_calc = None
        # pivot_start_date_for_calc = None

        # if current_module_start:
        #     # If a current module is found, use its start date and order as the pivot
        #     pivot_start_date_for_calc = current_module_start
        #     pivot_order_for_calc = current_module_order
        #     recalculate_needed = True
        #     recalculation_reason = f"El cronograma se está recalculando automáticamente basado en el módulo actual: '{current_module_name}' (Orden {current_module_order}) que inició el {current_module_start.strftime('%Y-%m-%d')}."
        # elif not modules_df.empty:
        #     # If there are modules but none are 'current' today,
        #     # assume the module with the lowest 'credits' order starts today as the pivot.
        #     pivot_order_for_calc = modules_df['credits'].min()
        #     pivot_start_date_for_calc = today # Starts from today
            
        #     # Ensure selected_module_order_for_calculation has a valid name for the message
        #     if not modules_df.empty and pivot_order_for_calc in modules_df['credits'].values:
        #         first_module_name = modules_df[modules_df['credits'] == pivot_order_for_calc]['name'].iloc[0]
        #     else:
        #         first_module_name = "el Módulo 1" # Fallback if module name not found (e.g., no modules or first module order is not 1)

        #     recalculate_needed = True
        #     recalculation_reason = f"No se detectó un módulo activo hoy. Recalculando el cronograma asumiendo que {first_module_name} (Orden {pivot_order_for_calc}) comienza hoy."
        # else:
        #     # No modules exist, no recalculation needed yet.
        #     recalculate_needed = False

        # if recalculate_needed:
        #     st.info(recalculation_reason, icon="ℹ️")
        #     with st.spinner("Calculando nuevo cronograma..."):
        #         modules_list_for_calc = modules_df.to_dict('records')

        #         # Call the refactored recalculate_full_schedule
        #         updated_modules_with_dates_list = recalculate_full_schedule(
        #             modules_list_for_calc,
        #             breaks,
        #             current_module_pivot_order=pivot_order_for_calc,
        #             current_module_pivot_start_date=pivot_start_date_for_calc
        #         )
                
        #         # Convert the calculated list back to a DataFrame for comparison
        #         calculated_df_temp = pd.DataFrame(updated_modules_with_dates_list)
        #         calculated_df_compare = calculated_df_temp[['firebase_key', 'fecha_inicio_1', 'fecha_fin_1']].copy()
        #         for col in ['fecha_inicio_1', 'fecha_fin_1']:
        #             calculated_df_compare[col] = calculated_df_compare[col].astype(str)
                
        #         # Merge with current_dates_df to compare dates for the same firebase_key
        #         merged_df = pd.merge(current_dates_df, calculated_df_compare, on='firebase_key', suffixes=('_current', '_calc'), how='left')
                
        #         # Identify if any date column has changed
        #         dates_have_changed = False
        #         for col_name in ['fecha_inicio_1', 'fecha_fin_1']:
        #             # Compare if there are any differences
        #             # Use .fillna('') to treat NaN/None/NaT consistently as empty string for comparison
        #             if not merged_df[f"{col_name}_current"].fillna('').equals(merged_df[f"{col_name}_calc"].fillna('')):
        #                 dates_have_changed = True
        #                 break

        #         if dates_have_changed:
        #             update_payload = {}
        #             for mod in updated_modules_with_dates_list:
        #                 firebase_key = mod.get('firebase_key')
        #                 if firebase_key:
        #                     mod_to_save = {key: value for key, value in mod.items() if key != 'Eliminar' and pd.notna(value)}
        #                     update_payload[firebase_key] = mod_to_save

        #             if update_payload:
        #                 try:
        #                     user_path = user_email.replace('.', ',')
        #                     db.child("modules").child(user_path).update(update_payload)
        #                     st.success("¡Cronograma recalculado y guardado exitosamente!")
        #                     time.sleep(1)
        #                     invalidate_cache_and_rerun() # Rerun to display updated data
        #                 except Exception as e:
        #                     st.error(f"Error al guardar el cronograma actualizado: {e}")
        #             else:
        #                 st.warning("No se encontraron módulos con fechas para actualizar.")
        #         else:
        #             st.info("Las fechas ya están actualizadas. No se requiere guardar el cronograma.")
        
        # st.subheader("Módulos Existentes y Planificación")

        # # --- FUNCIÓN PARA GUARDAR MÓDULOS ACTUALIZADOS ---
        # # def save_updated_modules(updated_df):
        # #     try:
        # #         update_payload = {}
        # #         for _, row in updated_df.iterrows():
        # #             if pd.notna(row.get('firebase_key')):
        # #                 mod_updates = row.drop('Eliminar', errors='ignore').to_dict()
                        
        # #                 clean_updates = {}
        # #                 for k, v in mod_updates.items():
        # #                     if v is None or pd.isna(v) or k == 'firebase_key':
        # #                         continue
                                
        # #                     if hasattr(v, 'item'): # Convert numpy types to Python native types
        # #                         v = v.item()
                                
        # #                     if isinstance(v, (datetime.date, datetime.datetime)): # Convert date objects to ISO format strings
        # #                         v = v.isoformat()
                                
        # #                     clean_updates[k] = v
                                
        # #                 if clean_updates:  # Solo agregar si hay actualizaciones
        # #                     update_payload[row['firebase_key']] = clean_updates
                
        # #         if update_payload:
        # #             user_path = user_email.replace('.', ',')
        # #             db.child("modules").child(user_path).update(update_payload)
        # #             set_last_updated('modules', user_email)
        # #             return True, "¡Cambios guardados exitosamente!"
        # #         return False, "No hay cambios para guardar."
        # #     except Exception as e:
        # #         import traceback
        # #         return False, f"Error al guardar cambios: {str(e)}\n{traceback.format_exc()}"

        # # --- EDITOR DE DATOS (Definido antes de cualquier lógica que use su salida) ---
        # df_to_edit = modules_df.copy()
        
        # # Define the date columns directly with the desired names (only one cycle)
        # date_columns = ['fecha_inicio_1', 'fecha_fin_1']
        
        # # Convertir las columnas de fecha a tipo datetime.date para el data_editor (ya se hizo en load_modules, pero es una doble verificación)
        # for col in date_columns:
        #     if col in df_to_edit.columns:
        #         try:
        #             df_to_edit[col] = pd.to_datetime(df_to_edit[col], errors='coerce').dt.date
        #         except Exception as e:
        #             st.error(f"Error al convertir la columna {col} a fecha para visualización: {str(e)}")
        # df_to_edit['Eliminar'] = False
        
        # # Configuración de columnas en el orden solicitado (solo un ciclo)
        # column_config = {
        #     "Eliminar": st.column_config.CheckboxColumn("Borrar", help="Seleccione para eliminar", default=False, width="small"),
        #     "name": st.column_config.TextColumn("Nombre del Módulo", required=True),
        #     "duration_weeks": st.column_config.NumberColumn("Semanas", format="%d", min_value=1, required=True, width="small"),
        #     "credits": st.column_config.NumberColumn("Orden", format="%d", min_value=1, required=True, width="small"),
        #     "fecha_inicio_1": st.column_config.DateColumn("Fecha Inicio", format="MM/DD/YYYY", disabled=True),
        #     "fecha_fin_1": st.column_config.DateColumn("Fecha Fin", format="MM/DD/YYYY", disabled=True),
        #     "module_id": None, "firebase_key": None, "description": None, "created_at": None, "updated_at": None,
        # }
        
        # # Ordenar las columnas según el orden deseado (solo un ciclo)
        # column_order = [
        #     "Eliminar", 
        #     "name", 
        #     "duration_weeks", 
        #     "credits", 
        #     "fecha_inicio_1", 
        #     "fecha_fin_1"
        # ]
        
        # # Asegurarse de que solo se incluyan las columnas que existen en el DataFrame
        # column_order = [col for col in column_order if col in df_to_edit.columns]
        
        # # Reordenar el DataFrame
        # df_to_edit = df_to_edit[column_order + [col for col in df_to_edit.columns if col not in column_order]]
        
        # # Esta es la única fuente de verdad. Siempre es un DataFrame.
        # # Usando num_rows="fixed" para evitar añadir nuevas filas
        # edited_df = st.data_editor(
        #     df_to_edit,
        #     column_config=column_config,
        #     hide_index=True,
        #     num_rows="fixed",
        #     key="modules_editor_main",
        #     use_container_width=True,
        # )
        
        # # Verificar cambios y eliminaciones
        # has_changes = not edited_df.equals(df_to_edit)
        # rows_to_delete = edited_df[edited_df['Eliminar'] == True]
        # has_deletions = not rows_to_delete.empty

        # # Crear columnas para botones
        # col1, col2 = st.columns([1, 3])
        
        # # Botón "Guardar Cambios"
        # if has_changes:
        #     with col1:
        #         if st.button("💾 Guardar Cambios", type="primary"):
        #             success, message = save_updated_modules(edited_df)
        #             if success:
        #                 st.success(message)
        #                 invalidate_cache_and_rerun()
        #             else:
        #                 st.error(message)
            
        # # Botón "Confirmar Eliminación"
        # if has_deletions:
        #     with col2:
        #         if st.button("🗑️ Confirmar Eliminación"):
        #             keys_to_delete = rows_to_delete['firebase_key'].tolist()
        #             deleted_count = 0
        #             with st.spinner("Eliminando módulos..."):
        #                 for key in keys_to_delete:
        #                     if delete_module_from_db(user_email, key):
        #                         deleted_count += 1
                    
        #             st.success(f"{deleted_count} módulo(s) eliminados. Se recalculará el cronograma automáticamente.")
        #             invalidate_cache_and_rerun()
        
        # # Mensajes de estado
        # if has_changes:
        #     st.warning("Tiene cambios sin guardar. Haga clic en 'Guardar Cambios' para guardar sus modificaciones.")
        # elif has_deletions:
        #     st.warning("Ha marcado módulos para eliminar. La eliminación es permanente.")
        # else:
        #     st.info("Realice cambios en la tabla y haga clic en 'Guardar Cambios' para guardar.")

        # # --- Se elimina la UI de Recalculación Manual ---
        # st.info("El cronograma de módulos se recalcula automáticamente al cargar la página o al agregar/eliminar módulos, basándose en la fecha actual y el módulo activo.", icon="💡")


else:
    st.error("Error de sesión: No se pudo obtener el email del usuario.")
