"""
Initialization file for the MongoDB integration module for the entrypoint of the. This module is responsible for setting up the connection to the MongoDB database using the environment variables defined in the config/environments.py file.
"""

from pymongo import MongoClient
from config.environments import Environments
from logger.logger import logger

myLogger = logger()

class Repository:
    """Class that defines the MongoDB repository for the ms-artificial-intelligence-core service."""
    
    def __init__(self, envs: Environments):
        myLogger.Info("Initializing MongoDB repository with environment variables")
        
        self.client = MongoClient(envs.MONGO_URI, username=envs.MONGO_USERNAME, password=envs.MONGO_PASSWORD)
        self.db = self.client[envs.MONGO_DB_NAME]
