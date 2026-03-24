from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    groq_api_key:           str
    openweather_api_key:    str
    twilio_account_sid:     str = ""
    twilio_auth_token:      str = ""
    twilio_whatsapp_from:   str = ""
    elevenlabs_api_key:     str = ""
    your_whatsapp_number:   str = ""
    lat:                    float = 31.1048
    lon:                    float = 77.1734
    city:                   str = "Shimla"
    db_path:                str = "data/sage.db"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()