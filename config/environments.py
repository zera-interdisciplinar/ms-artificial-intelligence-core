"""
Starts the environment variables for the application according to the .env file in the root directory of the project.
If a variable is not found in the .env file, it will be initialized with the default value defined in this file.
Uses the class Environments to define the environment variables and their default values.
"""

from dotenv import load_dotenv
from logger.logger import Logger
import os

load_dotenv()
myLogger = Logger()
myLogger.Info("Loading environment variables from .env file")

class Environments:
    """Class that defines the environment variables and their default values."""

    # Environment
    APP_ENV: str
    APP_PORT: str
    APP_HOST: str

    # APIs
    GEMINI_API_KEY: str | None
    GROQ_API_KEY: str | None

    # Database
    MONGO_URI: str
    MONGO_DB_NAME: str
    MONGO_USERNAME: str | None
    MONGO_PASSWORD: str | None

    # Session memory (per-thread MemorySaver cache)
    SESSION_TTL_SECONDS: int
    SESSION_HISTORY_LIMIT: int

    # FAQ
    FAQ_PDF_PATH: str

    # predict_model MCP (sdk-ml-failure-predictor, via Kong gateway)
    PREDICT_MODEL_MCP_URL: str | None

    # Supabase Storage
    SUPABASE_URL: str | None
    SUPABASE_SERVICE_ROLE_KEY: str | None
    SUPABASE_BUCKET_NAME: str | None

    def __init__(self) -> None:
        myLogger.Info("Initializing environment variables with default values")

        #Environment
        self.APP_ENV = os.getenv("APP_ENV", "DEV")
        self.APP_PORT = os.getenv("APP_PORT", "8000")
        self.APP_HOST = os.getenv("APP_HOST", "0.0.0.0")

        # APIs
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.GROQ_API_KEY = os.getenv("GROQ_API_KEY")

        # Database
        self.MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "ms-artificial-intelligence-core")
        self.MONGO_USERNAME = os.getenv("MONGO_USERNAME")
        self.MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")

        # Session memory (per-thread MemorySaver cache)
        self.SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "18000"))
        self.SESSION_HISTORY_LIMIT = int(os.getenv("SESSION_HISTORY_LIMIT", "50"))

        # FAQ
        self.FAQ_PDF_PATH = os.getenv("FAQ_PDF_PATH", "multi_agent/agents/data/faq.pdf")

        # predict_model MCP (sdk-ml-failure-predictor, via Kong gateway)
        self.PREDICT_MODEL_MCP_URL = os.getenv("PREDICT_MODEL_MCP_URL")

        # Supabase Storage
        self.SUPABASE_URL = os.getenv("SUPABASE_URL")
        self.SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.SUPABASE_BUCKET_NAME = os.getenv("SUPABASE_BUCKET_NAME")