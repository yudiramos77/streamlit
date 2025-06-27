import streamlit as st
import pandas as pd
import datetime
from config import setup_page

# Check for login status and valid session
if not st.session_state.get("logged_in") or "token_expires_at" not in st.session_state:
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Si el problema persiste, es posible que su sesión anterior haya caducado. Por favor, regrese a la página de Login y vuelva a iniciar sesión.")
    st.stop()

# initialize session state variables
if 'reverse_dates' not in st.session_state:
    st.session_state.reverse_dates = "No"
    print("DEBUG (Configuration.py): 'reverse_dates' initialized to False.")

if 'reverse_dates_value' not in st.session_state:
    st.session_state.reverse_dates_value = "No"
    print("DEBUG (Configuration.py): 'reverse_dates_value' initialized to False.")

if 'reverse_dates' in st.session_state:
    st.session_state.reverse_dates = st.session_state.reverse_dates_value
    print("DEBUG (Configuration.py): 'reverse_dates' already exists.", st.session_state.reverse_dates)

# --- Page Setup ---
setup_page("Configuración")

tab1, tab2 = st.tabs(["Modulos", "Notificaciones"])

with tab1:
    st.subheader("Calculo de Fechas")
    st.info("Por defecto se calculan las fechas de inicio y fin de los módulos basados en la fecha de inicio del curso y la duración del módulo a partir del módulo actual en curso. Si se selecciona la opción **'Calcular fechas de módulos hacia el pasado'**, se calcularán las fechas de inicio y fin de los módulos a partir del modulo actual pero hacia el pasado.")
    
    # The checkbox - uses the session state initialized in Login.py
    # st.input
    reverse_dates_value = st.selectbox(
        "Calcular fechas de módulos hacia el pasado",
        options=["No", "Sí"],
        key="reverse_dates_value"
    )

    

with tab2:
    st.subheader("Notificaciones")


# st.checkbox("¿Mostrar datos avanzados?", value=st.session_state.get("show_advanced", False), key="show_advanced")

# if st.session_state.show_advanced:
#     st.success("Se mostrarán los datos avanzados.")
# else:
#     st.info("Modo básico activado.")
# You can add this line for debugging to see the state in your terminal
st.write(f"Current state of reverse_dates: {st.session_state.get('reverse_dates')}")
