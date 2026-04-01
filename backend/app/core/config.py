import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
ADMIN_SETUP_CODE: str = os.getenv("ADMIN_SETUP_CODE", "")
RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
