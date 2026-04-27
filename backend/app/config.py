import figenv


class csv:
    @staticmethod
    def _coerce(value):
        return [v.strip() for v in value.split(",") if v.strip()]


class Config(metaclass=figenv.MetaConfig):
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/northlanding"
    SECRET_KEY = "change-me"
    GOOGLE_CLIENT_ID = ""
    GOOGLE_CLIENT_SECRET = ""
    TWILIO_ACCOUNT_SID = ""
    TWILIO_AUTH_TOKEN = ""
    TWILIO_FROM_NUMBER = ""
    SUPABASE_URL = ""
    SUPABASE_SERVICE_KEY = ""
    SUPABASE_BUCKET = "disc-photos"
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = 60
    REFRESH_TOKEN_EXPIRE_DAYS = 30
    API_KEY_HMAC_SECRET = ""
    FRONTEND_URL = "http://localhost:5173"
    ADMIN_EMAILS: csv = ""  # coerced to [] when unset


settings = Config
