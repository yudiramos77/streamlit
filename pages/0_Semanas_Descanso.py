import streamlit as st
import pandas as pd
import datetime
# Assuming 'config' module has 'setup_page' and 'db' (Firebase instance)
from config import setup_page, db 
from utils import date_format
from utils_admin import load_breaks

# --- Page Setup and Login Check ---
setup_page("Semanas de Descanso")
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()

# --- Database Operations ---



def save_break(break_id, break_data):
    """
    Saves a single break record to the Firebase Realtime Database.
    'break_id' is the unique key, 'break_data' is a dictionary of the break's attributes.
    """
    try:
        # Create a fresh reference to the specific break using its ID
        break_ref = db.child("breaks").child(break_id)
        break_ref.set(break_data, token=st.session_state.user_token) # Set (create or overwrite) the data
        return True
    except Exception as e:
        st.error(f"Error al guardar la semana de descanso: {e}")
        return False

# --- UI Components ---

def display_breaks_table(breaks_data):
    """
    Displays the loaded breaks data in a Streamlit dataframe.
    Calculates the 'Fecha Fin' dynamically for display.
    """
    if not breaks_data:
        st.info("No hay semanas de descanso configuradas.")
        return []
    
    breaks_list = []
    for break_id, break_info in breaks_data.items():
        if isinstance(break_info, dict):
            start_date_str = break_info.get('start_date')
            start_date = None
            try:
                # Attempt to parse start_date from ISO format string
                if start_date_str:
                    start_date = datetime.datetime.fromisoformat(start_date_str).date()
            except ValueError:
                st.warning(f"Formato de fecha inválido para el ID '{break_id}': '{start_date_str}'. Se ignorará esta entrada o se mostrará como 'N/A'.")
                # start_date remains None, handled below
            
            duration_weeks = break_info.get('duration_weeks', 1)
            
            # Calculate end_date (Sunday of the last week) only if start_date was successfully parsed
            end_date = (start_date + datetime.timedelta(days=(7 * duration_weeks) - 1)) if start_date else None
            
            breaks_list.append({
                'ID': break_id,
                'Eliminar': False,  # Add checkbox column
                'Nombre': break_info.get('name', ''),
                'Duración (semanas)': duration_weeks,
                'Fecha Inicio': date_format(start_date, "%Y/%m/%d") if start_date else 'N/A',
                'Fecha Fin': date_format(end_date, "%Y/%m/%d") if end_date else 'N/A',
                'start_date_obj': start_date  # Store as date object for sorting
            })
    
    if not breaks_list:
        st.info("No hay semanas de descanso configuradas.")
        return []
    
    # Sort by start date (most recent first)
    breaks_list.sort(key=lambda x: x['start_date_obj'] or datetime.date.min, reverse=True)
    
    # Create DataFrame
    df = pd.DataFrame(breaks_list)
    
    # Reorder columns for display - 'Semanas' before 'Inicio'
    column_order = ['Eliminar', 'Nombre', 'Duración (semanas)', 'Fecha Inicio', 'Fecha Fin', 'ID']
    df = df[[col for col in column_order if col in df.columns]]
    
    # Display the DataFrame with checkboxes
    edited_df = st.data_editor(
        df,
        column_config={
            'Eliminar': st.column_config.CheckboxColumn(
                "Eliminar",
                help="Seleccione para eliminar",
                default=False,
                width="small",
                pinned=True
            ),
            'ID': None,  # Hide the internal ID column
            'Nombre': 'Nombre',
            'Fecha Inicio': 'Inicio',
            'Fecha Fin': 'Fin',
            'Duración (semanas)': 'Semanas',
            'start_date_obj': None  # Hide the sort helper column
        },
        hide_index=True,
        use_container_width=True,
        disabled=['ID', 'Nombre', 'Fecha Inicio', 'Duración (semanas)', 'Fecha Fin']
    )
    
    # Check for breaks selected for deletion
    if 'delete_breaks' not in st.session_state:
        st.session_state.delete_breaks = False
    
    # Show delete button if any breaks are selected
    breaks_to_delete = edited_df[edited_df['Eliminar']]
    if not breaks_to_delete.empty:
        st.warning(f"Se eliminarán {len(breaks_to_delete)} semana(s) de descanso. Esta acción no se puede deshacer.")
        
        if st.button("⚠️ Confirmar eliminación"):
            success_count = 0
            for _, row in breaks_to_delete.iterrows():
                try:
                    # Create a fresh reference for each deletion to avoid path issues
                    db.child("breaks").child(row['ID']).remove(token=st.session_state.user_token)
                    success_count += 1
                except Exception as e:
                    st.error(f"Error al eliminar la semana de descanso '{row['Nombre']}': {str(e)}")
            
            if success_count > 0:
                st.success(f"Se eliminaron {success_count} semana(s) de descanso correctamente.")
                st.rerun()
    
    return breaks_list

def add_break_form():
    """
    Displays inputs to add a new break.
    The 'Período' caption updates reactively with user input without a form.
    Returns dictionary of data if save button is pressed, otherwise None.
    """
    # Initialize default values for the input fields for consistent behavior
    default_name = ''
    default_start_date = datetime.date.today()
    default_duration_weeks = 1

    # Initialize session state for input fields if they don't exist
    if 'add_break_name' not in st.session_state:
        st.session_state.add_break_name = default_name
    if 'add_break_start_date' not in st.session_state:
        st.session_state.add_break_start_date = default_start_date
    if 'add_break_duration_weeks' not in st.session_state:
        st.session_state.add_break_duration_weeks = default_duration_weeks

    st.subheader("Agregar Semana de Descanso")
    
    # Single row with all inputs
    col1, col2, col3 = st.columns([2, 2, 1])
    
    # Text input for the break name
    name = col1.text_input(
        "Nombre de la Semana de Descanso",
        value=st.session_state.add_break_name,
        key="break_name_input"
    )
    
    # Adjust start date to be Monday if it's not already
    def get_next_monday(date):
        days_ahead = 0 - date.weekday()  # Monday is 0, Sunday is 6
        if days_ahead < 0:  # If today is not Monday
            days_ahead += 7  # Go to next Monday
        return date + datetime.timedelta(days=days_ahead)
    
    # Default to next Monday if no date is set
    default_date = get_next_monday(datetime.date.today())
    
    # Date input for the start date (always Monday)
    start_date = col2.date_input(
        "Fecha de Inicio",
        value=default_date if st.session_state.add_break_start_date.weekday() != 0 
              else st.session_state.add_break_start_date,
        key="break_start_date_input"
    )
    
    # Show warning if selected date is not Monday
    if start_date.weekday() != 0:  # 0 is Monday
        next_monday = get_next_monday(start_date)
        st.warning(f"La fecha de inicio debe ser un lunes. Se usará el lunes {next_monday.strftime('%Y-%m-%d')}.")
        start_date = next_monday
    
    # Number input for duration in weeks
    duration_weeks = col3.number_input(
        "Semanas",
        min_value=1,
        value=st.session_state.add_break_duration_weeks,
        step=1,
        key="break_duration_input"
    )
    
    # Calculate and display the date range dynamically.
    # A week is from Monday to Sunday (7 days total)
    end_date_display = start_date + datetime.timedelta(days=(7 * duration_weeks) - 1)  # Sunday of the last week
    st.caption(f"Período: {date_format(start_date, "%Y/%m/%d")} al {date_format(end_date_display, "%Y/%m/%d")} "
              f"({duration_weeks} semana{'s' if duration_weeks != 1 else ''})")
    
    # Regular Streamlit button for saving data.
    # This will trigger a re-run and the logic below.
    if st.button("Guardar Semana de Descanso", type="primary"):
        # Validate that start date is a Monday (0 = Monday, 6 = Sunday)
        if start_date.weekday() != 0:
            st.error("Error: La fecha de inicio debe ser un lunes.")
            st.warning(f"La fecha seleccionada ({start_date.strftime('%A %Y-%m-%d')}) no es un lunes. "
                     f"Por favor, seleccione un lunes como fecha de inicio.")
            return None
            
        if not name:
            st.error("El nombre es obligatorio.")
            return None 
        
        # Reset session state variables after successful submission.
        st.session_state.add_break_name = default_name
        st.session_state.add_break_start_date = default_start_date 
        st.session_state.add_break_duration_weeks = default_duration_weeks 

        # Return the data to be saved
        return {
            'name': name,
            'start_date': start_date.isoformat(),
            'duration_weeks': duration_weeks,
            'created_at': datetime.datetime.now().isoformat(),
            'created_by': st.session_state.get('email', 'system')
        }
    
    return None # Return None if the button has not been pressed

# --- Main App ---

def main():
    """
    Main function to run the Streamlit application for managing break weeks.
    Displays existing breaks, provides an area to add new ones, and a section to delete them.
    """
    st.info("Administre las semanas de descanso que se aplicarán a todos los módulos. Estas fechas se utilizarán para saltar días no hábiles en los cálculos de programación.", icon=":material/info:")
    
    # Add new break form at the top
    break_data = add_break_form()
    
    if break_data:
        # Generate a unique ID for the new break based on current timestamp
        break_id = f"break_{datetime.datetime.now().strftime('%Y%m%d%H%M%S_%f')}" # Added microsecond for more uniqueness
        
        # Save the new break to Firebase
        try:
            db.child("breaks").child(break_id).set(break_data, token=st.session_state.user_token)
            st.success("¡Semana de descanso agregada exitosamente!")
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar la semana de descanso: {str(e)}")
    
    st.markdown("---")
    
    # Load and display existing breaks
    breaks_data = load_breaks()
    display_breaks_table(breaks_data)

# Entry point of the Streamlit application
if __name__ == "__main__":
    main()
