"""
Production configuration for NovaGuard Android Analysis API
"""

import os
import logging
from typing import List, Optional
from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application
    app_name: str = "NovaGuard Android Analysis API"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "production"  # development, staging, production
    
    # API Configuration
    api_prefix: str = "/api/v1"
    docs_url: Optional[str] = "/docs"
    redoc_url: Optional[str] = "/redoc"
    openapi_url: str = "/openapi.json"
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False
    
    # Analysis Engine Configuration
    max_analysis_workers: int = 4
    analysis_timeout: int = 300  # seconds
    max_concurrent_analyses: int = 10
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_files_per_project: int = 1000
    
    # Database Configuration
    database_url: str = "sqlite:///./novaguard.db"
    database_echo: bool = False
    database_pool_size: int = 20
    database_max_overflow: int = 30
    
    # Redis Configuration (for caching and task queue)
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    redis_ssl: bool = False
    
    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: Optional[str] = None
    log_rotation: str = "midnight"
    log_retention: int = 30  # days
    
    # Security Configuration
    secret_key: str = "your-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 100
    
    # Monitoring and Health
    health_check_interval: int = 30  # seconds
    metrics_enabled: bool = True
    prometheus_metrics: bool = False
    
    # File Storage
    upload_dir: str = "./uploads"
    temp_dir: str = "./temp"
    cleanup_temp_files: bool = True
    temp_file_ttl: int = 3600  # seconds
    
    # LLM Integration (for future use)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    openai_max_tokens: int = 4000
    openai_temperature: float = 0.1
    
    # External Services
    github_integration: bool = False
    gitlab_integration: bool = False
    bitbucket_integration: bool = False
    
    # Notification Configuration
    email_notifications: bool = False
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_tls: bool = True
    
    # Webhook Configuration
    webhook_secret: Optional[str] = None
    webhook_timeout: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @validator("cors_origins", pre=True)
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    @validator("log_level")
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    @validator("environment")
    def validate_environment(cls, v):
        valid_envs = ["development", "staging", "production"]
        if v not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v


# Create global settings instance
settings = Settings()


def setup_logging():
    """Setup logging configuration based on settings."""
    
    # Configure logging level
    log_level = getattr(logging, settings.log_level)
    
    # Create formatter
    formatter = logging.Formatter(settings.log_format)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if settings.log_file:
        from logging.handlers import TimedRotatingFileHandler
        
        os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
        
        file_handler = TimedRotatingFileHandler(
            settings.log_file,
            when=settings.log_rotation,
            backupCount=settings.log_retention
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Configure specific loggers
    if settings.environment == "production":
        # Reduce noise from external libraries in production
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    logging.info(f"Logging configured for {settings.environment} environment")


def get_database_url() -> str:
    """Get database URL based on environment."""
    if settings.environment == "testing":
        return "sqlite:///:memory:"
    return settings.database_url


def get_cors_config() -> dict:
    """Get CORS configuration."""
    return {
        "allow_origins": settings.cors_origins,
        "allow_credentials": settings.cors_allow_credentials,
        "allow_methods": settings.cors_allow_methods,
        "allow_headers": settings.cors_allow_headers,
    }


def get_analysis_engine_config() -> dict:
    """Get analysis engine configuration."""
    return {
        "max_workers": settings.max_analysis_workers,
        "timeout": settings.analysis_timeout,
        "max_concurrent": settings.max_concurrent_analyses,
        "max_file_size": settings.max_file_size,
        "max_files": settings.max_files_per_project,
    }


def ensure_directories():
    """Ensure required directories exist."""
    directories = [
        settings.upload_dir,
        settings.temp_dir,
    ]
    
    if settings.log_file:
        directories.append(os.path.dirname(settings.log_file))
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logging.info(f"Ensured directory exists: {directory}")


# Environment-specific configurations
DEVELOPMENT_CONFIG = {
    "debug": True,
    "reload": True,
    "log_level": "DEBUG",
    "cors_origins": ["http://localhost:3000", "http://localhost:8080"],
    "database_echo": True,
}

STAGING_CONFIG = {
    "debug": False,
    "reload": False,
    "log_level": "INFO",
    "cors_origins": ["https://staging.novaguard.com"],
    "database_echo": False,
}

PRODUCTION_CONFIG = {
    "debug": False,
    "reload": False,
    "log_level": "WARNING",
    "docs_url": None,  # Disable docs in production
    "redoc_url": None,
    "database_echo": False,
    "metrics_enabled": True,
    "prometheus_metrics": True,
}


def apply_environment_config():
    """Apply environment-specific configuration overrides."""
    config_map = {
        "development": DEVELOPMENT_CONFIG,
        "staging": STAGING_CONFIG,
        "production": PRODUCTION_CONFIG,
    }
    
    env_config = config_map.get(settings.environment, {})
    
    for key, value in env_config.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    logging.info(f"Applied {settings.environment} configuration")


# Initialize configuration
if __name__ != "__main__":
    apply_environment_config()
    setup_logging()
    ensure_directories() 