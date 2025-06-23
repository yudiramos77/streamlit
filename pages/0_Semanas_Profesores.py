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
# --- Database Operations ---
def load_breaks():
    """Load breaks from Firebase and return as a list of dictionaries with calculated end date."""
    try:
        breaks_ref = db.child("breaks").get()
        if not breaks_ref.val():
            return []
        
        breaks_list = []
        for break_id, break_data in breaks_ref.val().items():
            if break_data and isinstance(break_data, dict):
                start_date_str = break_data.get('start_date', '')
                duration_weeks = int(break_data.get('duration_weeks', 1))
                
                # Calculate end date
                try:
                    start_date = pd.to_datetime(start_date_str)
                    end_date = start_date + pd.DateOffset(weeks=duration_weeks) - pd.DateOffset(days=1)
                    end_date_str = end_date.strftime('%Y-%m-%d')
                except:
                    end_date_str = ''
                
                breaks_list.append({
                    'Nombre': break_data.get('name', 'Sin nombre'),
                    'Inicio': start_date_str,
                    'Duración (semanas)': duration_weeks,
                    'Fin': end_date_str
                })
        return breaks_list
    except Exception as e:
        st.error(f"Error cargando las semanas de descanso: {e}")
        return []

# --- Main UI ---

st.info("Notifique al administrador si hay un error en las fechas.")
# Load and display breaks
breaks = load_breaks()

if not breaks:
    st.info("No hay semanas de descanso configuradas.")
else:
    # Convert to DataFrame for better display
    import pandas as pd
    df = pd.DataFrame(breaks)
    
    # Ensure dates are in the correct format for display
    for col in ['Inicio', 'Fin']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%m/%d/%Y')
    
    # Display the table without index
    st.dataframe(
        df[['Nombre', 'Inicio', 'Duración (semanas)', 'Fin']],
        hide_index=True,
        use_container_width=True
    )