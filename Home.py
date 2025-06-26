import streamlit as st

# Set page config
# st.set_page_config(
#     page_title="Sistema de Gestión Estudiantil",
#     page_icon="🎓",
#     layout="centered"
# )

# First, handle the case where the user is NOT logged in.
if not st.session_state.get("logged_in", False):
    pages = {
        "Inicio": [st.Page("Login.py", title="🔐 Login")],
    }
# If we are here, the user IS logged in. Now we check their role.
else:
    # Use a safe default of False for admin status
    if st.session_state.get("admin", False):
        # Define pages for Admin
        pages = {
            "Inicio": [st.Page("Login.py", title="🔐 Login")],
            "Admin": [
                st.Page("pages/1_Estudiantes_admin.py", title="🎓 Estudiantes"),
                st.Page("pages/2_Asistencia_admin.py", title="📅 Asistencia"),
                st.Page("pages/0_Semanas_Descanso.py", title="🌴 Vacaciones"),
                st.Page("pages/4_Modulos_admin.py", title="📚 Módulos")
            ],
            "Reportes": [
                st.Page("pages/6_Buscar_estudiantes_Admin.py", title="🔍 Buscar"),
                st.Page("pages/5_Reporte_estudiantes_admin.py", title="🎓 Estudiantes"),
                st.Page("pages/3_Reportes_admin.py", title="📅 Asistencia")
            ],
        }
    else:
        # Define pages for a regular, non-admin user
        pages = {
            "Inicio": [st.Page("Login.py", title="🔐 Login")],
            "Datos": [
                st.Page("pages/2_Asistencia.py", title="📅 Asistencia"),
                st.Page("pages/4_Modulos.py", title="📚 Módulos"),
                st.Page("pages/0_Semanas_Profesores.py", title="🌴 Vacaciones")
            ],
            "Reportes": [
                st.Page("pages/3_Reportes.py", title="📅 Asistencia"),
                st.Page("pages/5_Reporte_estudiantes.py", title="🎓 Estudiantes")
            ],
        }

pg = st.navigation(pages)
pg.run()



    # When logged in, pages from the 'pages' directory will appear in the sidebar.
    # Ensure those pages have a login check.


