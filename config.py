import os
from dotenv import load_dotenv

load_dotenv()


class BigTimeConfig:
    BASE_URL = "https://iq.bigtime.net/BigtimeData/api/v2"
    API_TOKEN = os.getenv("BIGTIME_API_TOKEN", "")
    FIRM_ID = os.getenv("BIGTIME_FIRM_ID", "")
    USERNAME = os.getenv("BIGTIME_USERNAME", "")
    PASSWORD = os.getenv("BIGTIME_PASSWORD", "")


class AzureConfig:
    TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
    CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
    OUTLOOK_USERS = [
        u.strip()
        for u in os.getenv("OUTLOOK_USERS", "").split(",")
        if u.strip()
    ]
