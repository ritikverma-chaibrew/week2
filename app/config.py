from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "touchgrass"
    llm_call_gap_seconds: int = 0  # pause between successful LLM calls on Google AI Studio (0 = back-to-back)
    llm_retry_seconds: int = 30  # after a failed call on Google AI Studio wait attempt x this (30 s, 60 s, 90 s)
    min_images: int = 5
    max_images: int = 10
    max_upload_bytes: int = 8_000_000
    image_ttl_seconds: int = 86400


settings = Settings()
