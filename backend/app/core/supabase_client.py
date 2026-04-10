from supabase import create_client, Client
from app.core.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

# Admin client — uses service_role key, for admin operations (create users, manage data).
# This client must NEVER have sign_in_with_password() or set_session() called on it.
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Regular client — uses service_role key, used for table queries and user-context auth calls.
# sign_in_with_password() may be called on this client; it must never be used for auth.admin ops.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
