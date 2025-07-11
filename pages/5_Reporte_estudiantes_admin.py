import streamlit as st
import pandas as pd
import datetime
import locale
import altair as alt
import urllib.parse
from config import setup_page
from utils import (
    load_students,
    get_module_on_date, get_highest_module_credit, get_last_updated,
    get_module_name_by_id, load_modules, highlight_style
)
from utils_admin import admin_get_student_group_emails, admin_load_students

# --- Login Check ---
if not st.session_state.get('logged_in', False):
    st.error("Debe iniciar sesión para acceder a esta página.")
    st.info("Por favor, regrese a la página principal para iniciar sesión.")
    st.stop()
# --- End Login Check ---

setup_page("Reporte de Estudiantes Admin")

# Module section

# if 'modules_df' not in st.session_state:
#     st.session_state.modules_df = None

if 'modules_df_by_course' not in st.session_state:
    st.session_state.modules_df_by_course = {} # This will store DataFrames per course

if 'current_module_id_for_today' not in st.session_state:
    st.session_state.current_module_id_for_today = None

st.subheader(" Seleccionar Curso")


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
        "Seleccione el Curso para el reporte de estudiantes:",
        options=full_emails_for_options,
        format_func=lambda x: course_options[x]['label'],
        index=0,
        key="course_selector" # Added key for consistency
    )
    # Student section
    students_last_updated = get_last_updated('students',modules_selected_course)
    df_loaded, _ = admin_load_students(modules_selected_course, students_last_updated)
    # df_loaded = admin_load_students(modules_selected_course)
    # print("\n\ndf_loaded\n", df_loaded)

    if df_loaded is None or df_loaded.empty:
        st.info("No hay estudiantes registrados.")
    else:
        # Clean and format the data
        if 'ciclo' in df_loaded.columns:
            df_loaded = df_loaded.drop(columns=['ciclo'])
        
        # Format date columns
        date_columns = ['fecha_inicio', 'fecha_fin']
        for col in date_columns:
            if col in df_loaded.columns:
                df_loaded[col] = pd.to_datetime(df_loaded[col], errors='coerce').dt.strftime('%m/%d/%Y')
        
        # Select and order columns to display
        display_columns = ['nombre', 'email', 'telefono', 'modulo', 'fecha_inicio','modulo_fin_name', 'fecha_fin', 'modulo_fin_id' ]
        display_columns = [col for col in display_columns if col in df_loaded.columns]
        
        # Rename columns for display
        column_names = {
            'nombre': 'Nombre',
            'email': 'Correo Electrónico',
            'telefono': 'Teléfono',
            'modulo': 'Módulo (ID)',
            'modulo_nombre': 'Módulo',
            'fecha_inicio': 'Fecha de Inicio',
            'fecha_fin': 'Fecha de Finalización',
            'modulo_fin_name': 'Módulo (Final)',
            }

        if 'current_module_id_for_today' in st.session_state and st.session_state.current_module_id_for_today is None:
            print("\n\nst.session_state.get('email')\n", modules_selected_course)
            result = get_module_on_date(modules_selected_course)
            print("\n\nresult\n", result)
            if result and 'module_id' in result:
                st.session_state.current_module_id_for_today = result['firebase_key']
                print("\n\ncurrent_module_id_for_today\n", result['firebase_key'])
            # else:
            #     st.warning("No se encontró un módulo activo para hoy.")

        current_module_id = st.session_state.get('current_module_id_for_today')

        print("\n\ncurrent_module_id\n", current_module_id)
        total_students = len(df_loaded)
        # print("total_students", total_students)

        df_loaded['_fecha_inicio_dt'] = pd.to_datetime(df_loaded['fecha_inicio']).dt.date
        df_loaded['_fecha_fin_dt'] = pd.to_datetime(df_loaded['fecha_fin']).dt.date

        # Then create formatted versions for display
        # df_loaded['fecha_inicio'] = df_loaded['_fecha_inicio_dt'].apply(lambda x: x.strftime('%m/%d/%Y'))
        # df_loaded['fecha_fin'] = df_loaded['_fecha_fin_dt'].apply(lambda x: x.strftime('%m/%d/%Y'))

        df_loaded['fecha_fin'] = df_loaded['_fecha_fin_dt'].apply(
            lambda x: x.strftime('%m/%d/%Y') if pd.notna(x) else ''
        )

        df_loaded['fecha_inicio'] = df_loaded['_fecha_inicio_dt'].apply(
            lambda x: x.strftime('%m/%d/%Y') if pd.notna(x) else ''
        )

        missing_end_date_mask = (df_loaded['fecha_fin'] == '') & (df_loaded['_fecha_fin_dt'].isna())

        if missing_end_date_mask.any():
            st.error("No se encontraron fechas de finalización en algunos Estudiantes. Esto es seguramente un error a la hora de cargar los estudiantes.")
            st.stop()
            
           


        today = datetime.date.today()
        students_in_module = len(df_loaded[
            (df_loaded['_fecha_inicio_dt'] <= today) &
            (df_loaded['_fecha_fin_dt'] >= today)
        ])
        # print("students_in_module", students_in_module)

        students_not_in_module = total_students - students_in_module
        # print("students_not_in_module", students_not_in_module)

        students_in_last_module = len(df_loaded[
            (df_loaded['_fecha_fin_dt'] <= today)
        ])

        last_module_students = df_loaded[
            (df_loaded['_fecha_inicio_dt'] <= today) &
            (df_loaded['_fecha_fin_dt'] >= today) &
            (df_loaded['_fecha_fin_dt'] == df_loaded.groupby('email')['_fecha_fin_dt'].transform('max'))
        ]
        df_loaded['En Ultimo Módulo'] = df_loaded['email'].apply(
            lambda x: 'Sí' if x in last_module_students['email'].unique() else 'No'
        )

        today = pd.to_datetime(today)
        df_loaded['_fecha_inicio_dt'] = pd.to_datetime(df_loaded['_fecha_inicio_dt'])
        df_loaded['_fecha_fin_dt'] = pd.to_datetime(df_loaded['_fecha_fin_dt'])


        students_in_last_module = len(df_loaded[
            (df_loaded['_fecha_inicio_dt'] <= today) &
            (df_loaded['_fecha_fin_dt'] >= today) &
            (df_loaded['modulo_fin_id'] == current_module_id)
        ])
        # print("students_in_last_module", students_in_last_module)


        students_finished = len(df_loaded[
            (df_loaded['_fecha_fin_dt'] <= today)
        ])
        # print("students_finished", students_finished)


        # ------ Highlight current module section ------
        # This section will highlight the current module in the DataFrame
        # Assuming df_loaded is your initial DataFrame and is already loaded
        

        # 1. Define all columns you need, including the one for logic
        # Using a single DataFrame is simpler than maintaining two.
        internal_columns = [
            'nombre', 'email', 'telefono', 'modulo', 'fecha_inicio', 
            'modulo_fin_name', 'fecha_fin', 'modulo_fin_id'
        ]
        df = df_loaded[internal_columns].copy()

        # 2. Create communication links
        default_message = "Hola, me comunico desde el instituto. ¿Cómo estás?"
        default_subject = "De Interamerican Technical Institute"
        
        def create_whatsapp_link(phone: str, message: str) -> str:
            if pd.isna(phone) or str(phone).strip() == 'nan':
                return ""
            phone = ''.join(filter(str.isdigit, str(phone)))
            encoded_message = urllib.parse.quote(message)
            return f"https://wa.me/{phone}?text={encoded_message}"  

        def create_teams_link(email: str, message: str) -> str:
            if pd.isna(email) or not str(email).strip():
                return ""
            encoded_message = urllib.parse.quote(message)
            return f"https://teams.microsoft.com/l/chat/0/0?users={email}&message={encoded_message}"  

        def create_email_link(email: str, message: str) -> str:
            if pd.isna(email) or not str(email).strip():
                return ""
            to = urllib.parse.quote(email)
            subj = urllib.parse.quote(default_subject)
            body = urllib.parse.quote(message)
            return f"https://outlook.office.com/mail/deeplink/compose?to={to}&subject={subj}&body={body}"
        
        # Ensure phone numbers are strings and clean them
        df['telefono'] = df['telefono'].astype(str).str.strip()
        
        # Create communication links
        df['whatsapp_link'] = df['telefono'].apply(create_whatsapp_link, message=default_message)
        df['teams_link'] = df['email'].apply(create_teams_link, message=default_message)
        df['email_link'] = df['email'].apply(create_email_link, message=default_message)

        # 2. Rename columns for user-friendly display
        # Note: We don't rename 'modulo_fin_id' so we can easily reference it later.
        column_renames = {
            'nombre': 'Nombre',
            'email': 'Correo Electrónico',
            'telefono': 'Teléfono',
            'modulo': 'Módulo (ID)',
            'fecha_inicio': 'Fecha de Inicio',
            'fecha_fin': 'Fecha de Finalización',
            'modulo_fin_name': 'Módulo (Final)',
            'whatsapp_link': 'WhatsApp',
            'teams_link': 'Microsoft Teams',
            'email_link': 'Email',
            'modulo_fin_id': 'modulo_fin_id'  # Will be hidden but needed for filtering
        }
        df_renamed = df.rename(columns=column_renames)

        def highlight_row_warning(row):
            """
            Highlights a row in yellow if it's the current module and has already started.
            """
            try:
                is_current_module = row.get('modulo_fin_id') == current_module_id
                is_module_started = False
                start_date_val = row.get('Fecha de Inicio')

                if pd.notna(start_date_val):
                    try:
                        start_date = pd.to_datetime(start_date_val).date()
                        is_module_started = start_date <= datetime.date.today()
                    except (ValueError, TypeError):
                        is_module_started = False
                
                if is_current_module and is_module_started:

                    return [highlight_style('warning') for _ in row]

            except Exception as e:
                print(f"Error processing row in highlight_function: {row.to_dict()}")
                print(f"Error was: {e}")

            return ['' for _ in row]

        def highlight_row_error(row):
            """
            Highlights a row in red if fecha_fin is in the past.
            """
            try:
                # Asegúrate de que la columna exista y no sea nula antes de comparar
                end_date_val = row.get('Fecha de Finalización') # <--- CORREGIDO
                fecha_fin_in_past = False
                if pd.notna(end_date_val):
                    # Convierte a fecha para una comparación segura
                    end_date = pd.to_datetime(end_date_val).date()
                    fecha_fin_in_past = end_date < datetime.date.today()
                
                if fecha_fin_in_past:
                    return [highlight_style('error') for _ in row]

            except Exception as e:
                print(f"Error processing row in highlight_function: {row.to_dict()}")
                print(f"Error was: {e}")

            return ['' for _ in row]

        def highlight_row_success(row):
            """
            Highlights a row in green if fecha_inicio is in the future.
            """
            try:
                # Asegúrate de que la columna exista y no sea nula antes de comparar
                start_date_val = row.get('Fecha de Inicio') # <--- CORREGIDO
                fecha_inicio_in_future = False
                if pd.notna(start_date_val):
                    # Convierte a fecha para una comparación segura
                    start_date = pd.to_datetime(start_date_val).date()
                    fecha_inicio_in_future = start_date > datetime.date.today()
                
                if fecha_inicio_in_future:
                    return [highlight_style('success') for _ in row]

            except Exception as e:
                print(f"Error processing row in highlight_function: {row.to_dict()}")
                print(f"Error was: {e}")

            return ['' for _ in row]

        # Sort the DataFrame by 'Fecha de Inicio'
        df_renamed = df_renamed.sort_values(by='Fecha de Inicio', ascending=False)   

        # 4. Decide whether to apply styling
        if current_module_id:
            # Apply the style to the renamed DataFrame
            df_to_show = df_renamed.style.apply(highlight_row_warning, axis=1).apply(highlight_row_error, axis=1).apply(highlight_row_success, axis=1)
        else:
            # If no ID is set, just use the regular DataFrame
            df_to_show = df_renamed

        
        st.subheader("📜 Reporte de Estudiantes")

        # Metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total", total_students, border=True)
        with col2:
            st.metric("En Curso", students_in_module, border=True)
        with col3:
            st.metric("Último Módulo", students_in_last_module, border=True)
        with col4:
            st.metric("Graduados", students_finished, border=True)
        with col5:
            st.metric("No comenzado", students_not_in_module - students_finished, border=True)




    # 5. Display the DataFrame and hide the column
        st.dataframe(
            df_to_show,
            hide_index=True,
            use_container_width=True,
            column_config={
                # Setting a column's configuration to None completely removes it from display.
                "modulo_fin_id": None,
                # Your other column configurations for renaming headers remain the same
                "Nombre": "Estudiante",
                "Correo Electrónico": "Email",
                "Teléfono": "Teléfono",
                "Módulo (ID)": "Módulo (Inicio)",
                "Fecha de Inicio": "Inicio",
                "Fecha de Finalización": "Fin",
                "Módulo (Final)": "Módulo (Final)",
                "Email": st.column_config.LinkColumn("Email", display_text="📧"),
                "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="💬"),
                "Microsoft Teams": st.column_config.LinkColumn("Teams", display_text="💻")  
            }
        )
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.warning("Último módulo")
        with col2:
            st.error("Graduados")
        with col3:
            st.success("No han empezado")

        # st.info("Por favor, seleccione un módulo para ver los estudiantes.")
        # st.warning("Por favor, seleccione un módulo para ver los estudiantes.")
        # st.success("Por favor, seleccione un módulo para ver los estudiantes.")
        st.subheader("📊 Flujo de estudiantes activos por mes")
        
        meses_es = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        # Copia y formatea fechas
        students = df_renamed.copy()
        students['Fecha de Inicio'] = pd.to_datetime(students['Fecha de Inicio'])
        students['Fecha de Finalización'] = pd.to_datetime(students['Fecha de Finalización'])

        # Rango mensual para analizar
        min_date = students['Fecha de Inicio'].min()
        max_date = students['Fecha de Finalización'].max()
        monthly_range = pd.date_range(min_date, max_date, freq='MS')

        # Calcular estudiantes activos por mes
        active_per_month = []
        for date in monthly_range:
            activos = students[
                (students['Fecha de Inicio'] <= date) &
                ((students['Fecha de Finalización'].isna()) | (students['Fecha de Finalización'] >= date))
            ]
            active_per_month.append({
                'Mes': date,
                'Activos': len(activos),
                'Etiqueta': meses_es[date.month] + ' ' + date.strftime('%Y')
            })

        active_df = pd.DataFrame(active_per_month)

        hoy = pd.to_datetime(datetime.datetime.today().replace(day=1))
        # Grafico de estudiantes activos por mes
        # 🔴 Línea vertical con tooltip de "Mes actual"
        linea_actual = alt.Chart(pd.DataFrame({'Mes': [hoy], 'label': ['Mes actual']})).mark_rule(
            color='red',
            strokeDash=[5, 5],
            size=2
        ).encode(
            x='Mes:T',
            tooltip=alt.Tooltip('label:N', title='')
        )

        # 🔵 Punto del pico máximo
        pico = active_df.loc[active_df['Activos'].idxmax()]
        pico_df = pd.DataFrame([pico])

        pico_max = alt.Chart(pico_df).mark_point(
            shape='triangle-up',
            size=100,
            color='orange'
        ).encode(
            x='Mes:T',
            y='Activos:Q',
            tooltip=[
                alt.Tooltip('Etiqueta:N', title='Mes pico'),
                alt.Tooltip('Activos:Q', title='Máximo de Activos')
            ]
        )

        # 📈 Línea de evolución mensual
        chart = alt.Chart(active_df).mark_line(point=True, color="#1f77b4").encode(
            x=alt.X('Mes:T', title='Mes'),
            y=alt.Y('Activos:Q', title='Estudiantes activos'),
            tooltip=[
                alt.Tooltip('Etiqueta:N', title='Mes'),
                alt.Tooltip('Activos:Q')
            ]
        ).properties(
            width='container',
            height=400,
            title='Estudiantes activos por mes'
        )

        # Mostrar gráfico combinado
        st.altair_chart(chart + linea_actual + pico_max, use_container_width=True)
       

        # ----------------------------------------
        # 📋 Ingresos y Egresos por mes (tabla y barra)
        # ----------------------------------------
        st.subheader("📋 Ingresos y egresos por mes")

        # Agrupar ingresos
        students['Mes_Inicio'] = students['Fecha de Inicio'].dt.to_period('M').dt.to_timestamp()
        entradas = students.groupby('Mes_Inicio').size().reset_index(name='Ingresos')

        # Agrupar egresos
        students['Mes_Fin'] = students['Fecha de Finalización'].dt.to_period('M').dt.to_timestamp()
        salidas = students.groupby('Mes_Fin').size().reset_index(name='Egresos')

        # Combinar tabla
        ingresos_egresos = pd.merge(
            entradas.rename(columns={'Mes_Inicio': 'Mes'}),
            salidas.rename(columns={'Mes_Fin': 'Mes'}),
            on='Mes',
            how='outer'
        ).fillna(0).sort_values('Mes')

        # Convertir a enteros y usar Mes como índice
        ingresos_egresos[['Ingresos', 'Egresos']] = ingresos_egresos[['Ingresos', 'Egresos']].astype(int)
        ingresos_egresos.set_index('Mes', inplace=True)

        # 1. Filtrar para mostrar solo meses con actividad
        #    Nos quedamos solo con las filas donde 'Ingresos' o 'Egresos' sea mayor que 0.
        ingresos_egresos_filtrado = ingresos_egresos.query("Ingresos > 0 or Egresos > 0")

        # 2. Preparar los datos para el gráfico (formato largo)
        #    Altair funciona mejor cuando los datos están en un formato "largo".
        #    Convertimos las columnas 'Ingresos' y 'Egresos' en filas.
        datos_grafico = pd.melt(
            ingresos_egresos_filtrado.reset_index(),
            id_vars=['Mes'],
            value_vars=['Ingresos', 'Egresos'],
            var_name='Tipo de Movimiento', # Nueva columna: 'Ingresos' o 'Egresos'
            value_name='Cantidad'          # Nueva columna: el valor numérico
        )

        datos_grafico['Mes_Esp'] = datos_grafico['Mes'].apply(lambda d: f"{meses_es[d.month]} {d.year}")

        # 3. Crear el gráfico con Altair
        chart = alt.Chart(datos_grafico).mark_bar(size=30).encode(
            x=alt.X('Mes:T', title='Mes', axis=alt.Axis(format='%b %Y')),
            y=alt.Y('Cantidad:Q', title='Número de Estudiantes'),
            color=alt.Color(
                'Tipo de Movimiento:N',
                title="Tipo de Movimiento",
                scale=alt.Scale(
                    domain=['Ingresos', 'Egresos'],
                    range=['#1f77b4', '#d62728']
                ),
                legend=alt.Legend(
                    orient='bottom',
                    direction='horizontal',
                    titleFontSize=12,
                    labelFontSize=11,
                    symbolSize=150,
                    padding=10
                )
            ),
            tooltip=[
                alt.Tooltip('Mes:T', title='Mes', format='%B %Y'),
                alt.Tooltip('Cantidad:Q', title='Cantidad'),
                alt.Tooltip('Tipo de Movimiento:N', title='Tipo')
            ]
        ).properties(
            title='Ingresos y Egresos Mensuales'
        )

        # 4. Mostrar el gráfico en Streamlit
        #    - Usamos st.altair_chart en lugar de st.bar_chart.
        #    - Por defecto, los gráficos de Altair no tienen zoom, cumpliendo ese requisito.
        st.altair_chart(chart, use_container_width=True)
else:
    st.warning("No se encontraron cursos disponibles.")
    modules_selected_course = None # Ensure it's explicitly None if no courses