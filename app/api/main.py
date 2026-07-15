"""FastAPI application entrypoint for the Zera ms-artificial-intelligence-core service."""

from fastapi import FastAPI, APIRouter
from logger.logger import logger
from config.environments import Environments
from pymongo import MongoClient
from _internal.mongo.setup import Repository

myLogger = logger()
myLogger.Info("Booting up ms-artificial-intelligence-core service")

envs = Environments()

# Open a new connection to the MongoDB database using the environment variables
repository = Repository(envs)

