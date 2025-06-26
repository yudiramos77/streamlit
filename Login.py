import streamlit as st
import pyrebase
from config import auth, db
from datetime import datetime, timedelta



# Initialize session state for login if not already present
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.email = None
    st.session_state.user = None # To store the full user object from Firebase
    st.session_state.user_token = None # To store Firebase token
    st.session_state.token_expires_at = None # To store the token's expiration time
    st.session_state.admin = False

def login_user(email, password):
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        st.session_state.logged_in = True
        st.session_state.email = user['email']
        st.session_state.user = user # Store the full user object
        st.session_state.user_token = user['idToken'] # Store the token

        # Calculate and store the token's exact expiration time
        login_time = datetime.now()
        token_lifetime = timedelta(seconds=int(user['expiresIn']))
        st.session_state.token_expires_at = login_time + token_lifetime

        if 'admin' in email.lower():
            st.session_state.admin = True
        else:
            st.session_state.admin = False
        st.cache_data.clear()
        st.rerun()
    except Exception as e: # Catch generic Firebase errors or others
        st.error(f"Error de inicio de sesión: Usuario o contraseña incorrectos.")
        # st.error(f"AQUÍ ESTÁ EL ERROR REAL: {e}") # UNCOMMENT THIS LINE
        # st.error(f"TIPO DE ERROR: {type(e)}") # ALSO ADD THIS LINE

def logout_user():
    st.session_state.logged_in = False
    st.session_state.email = None
    st.session_state.user_token = None
    st.session_state.clear()
    # Potentially clear other session state variables related to the user
    st.rerun()

# --- Page Logic ---
if not st.session_state.logged_in:



    col1, col2, col3 = st.columns([1, 3, 1]) # Adjust ratios here for different widths
        
    with col2:
        with st.form("login_form"):
            st.header("🎓 ITI Admin")
            st.info("Por favor, inicie sesión para continuar.")
            email = st.text_input("Correo Electrónico", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_password")
            submitted = st.form_submit_button("Iniciar Sesión", type="primary")

        if submitted:
            if email and password:
                if '@' not in email:
                    email += '@iti.edu'
                login_user(email, password)
            else:
                st.warning("Por favor, ingrese su correo y contraseña.")
    
    # Hide sidebar when not logged in if desired (more complex, requires st_pages or similar)
    # For now, Streamlit will show 'index' in the sidebar.

else:
    user_name = "Usuario"
    if st.session_state.get('email'):
        try:
            name_part = st.session_state.email.split('@')[0]
            user_name = name_part.capitalize()
        except Exception:
            pass # Keep 'Usuario' if email format is unexpected

    st.sidebar.title(f"Bienvenido, {user_name}")
    if st.session_state.get('email'): # Check if email exists before writing
        st.sidebar.write(st.session_state.email)
    if st.sidebar.button("Cerrar Sesión"):
        logout_user()
    
    st.title("🎓 Sistema de Gestión Estudiantil")
    if st.session_state.admin:
        st.write("### ¡Bienvenido Admin!")
    else:
        st.write("### ¡Bienvenido!")
    st.write("Seleccione una opción del menú lateral para continuar.")
    st.info("Recuerde que todas las operaciones se guardan automáticamente en la base de datos.")