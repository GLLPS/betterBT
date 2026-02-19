import os
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key, default=""):
    """Get a config value from Streamlit secrets (cloud) or environment (.env local)."""
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


class BigTimeConfig:
    BASE_URL = "https://iq.bigtime.net/BigtimeData/api/v2"
    API_TOKEN = _get_secret("BIGTIME_API_TOKEN")
    FIRM_ID = _get_secret("BIGTIME_FIRM_ID")
    USERNAME = _get_secret("BIGTIME_USERNAME")
    PASSWORD = _get_secret("BIGTIME_PASSWORD")


class AzureConfig:
    TENANT_ID = _get_secret("AZURE_TENANT_ID")
    CLIENT_ID = _get_secret("AZURE_CLIENT_ID")
    CLIENT_SECRET = _get_secret("AZURE_CLIENT_SECRET")
    OUTLOOK_USERS = [
        u.strip()
        for u in _get_secret("OUTLOOK_USERS").split(",")
        if u.strip()
    ]
