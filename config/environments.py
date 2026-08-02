"""
Starts the environment variables for the application according to the .env file in the root directory of the project.
If a variable is not found in the .env file, it will be initialized with the default value defined in this file.
Uses the class Environments to define the environment variables and their default values.
"""

from dotenv import load_dotenv
from logger.logger import logger
import os

load_dotenv()
myLogger = logger()
myLogger.Info("Loading environment variables from .env file")

class Environments:
    """Class that defines the environment variables and their default values."""
    
    def __init__(self):
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
        self.MONGO_USERNAME = os.getenv("MONGO_USERNAME", "root")
        self.MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
        
        # FAQ
        self.FAQ_PDF_PATH = os.getenv("FAQ_PDF_PATH", "multi_agent/agents/data/faq.pdf")