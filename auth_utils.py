# auth_utils.py

import streamlit as st
import datetime
import functools

def smart_refresh_token():
    """
    Checks if the user's token is about to expire and refreshes it only if needed.
    This is the core logic that checks the timer.
    """
    if 'user' not in st.session_state or not st.session_state.user:
        return False

    if datetime.datetime.now() >= st.session_state.token_expires_at - datetime.timedelta(seconds=60):
        try:
            refreshed_user = st.session_state.user.refresh(st.session_state.user['refreshToken'])
            st.session_state.user = refreshed_user
            st.session_state.user_token = refreshed_user['idToken']
            login_time = datetime.datetime.now()
            token_lifetime = datetime.timedelta(seconds=int(refreshed_user['expiresIn']))
            st.session_state.token_expires_at = login_time + token_lifetime
        except Exception as e:
            st.error("Your session has expired. Please log in again.")
            st.session_state.clear() # Force a full logout on refresh failure
            st.rerun()
            return False
            
    return True

def require_auth(func):
    """
    A decorator that checks for a valid auth token before running a function.
    If the token is invalid or expired, it stops execution and warns the user.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not st.session_state.get('logged_in'):
            st.warning("Please log in to perform this action.")
            return None # Or return a default value appropriate for the wrapped function
        
        if smart_refresh_token():
            # If token is valid or refreshed, run the original function
            return func(*args, **kwargs)
        else:
            # If token refresh fails, do not run the function
            return None # Or return a default value
            
    return wrapper