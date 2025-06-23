import streamlit as st
import pyrebase
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Firebase configuration
firebaseConfig = {
    "apiKey": st.secrets["firebase"]["apiKey"],
    "databaseURL": st.secrets["firebase"]["databaseURL"],
    "authDomain": st.secrets["firebase"]["authDomain"],
    "projectId": st.secrets["firebase"]["projectId"],
    "storageBucket": st.secrets["firebase"]["storageBucket"],
    "messagingSenderId": st.secrets["firebase"]["messagingSenderId"],
    "appId": st.secrets["firebase"]["appId"],
    "measurementId": st.secrets["firebase"]["measurementId"]
}

# Initialize Firebase
firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()

@st.cache_data(ttl=300)

def check_auth():
    """Check if user is logged in, redirect to login if not"""
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.switch_page("Home.py")

def setup_page(title):
    """Common page setup with title."""
    st.set_page_config(page_title=title, layout="centered")
    st.title(title)
