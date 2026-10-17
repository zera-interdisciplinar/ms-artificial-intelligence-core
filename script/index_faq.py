"""Recreate the FAQ Qdrant collection from a local PDF. Usage: python script/index_faq.py [--path PATH]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import SecretStr
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from config.environments import Environments
from logger.logger import Logger


def main(argv: list[str] | None = None) -> None:
    envs = Environments()
    parser = argparse.ArgumentParser(description="Replace the FAQ Qdrant collection from a PDF.")
    parser.add_argument("--path", default=envs.FAQ_PDF_PATH, help="Path to the FAQ PDF")
    args = parser.parse_args(argv)
    logger = Logger()

    if not envs.QDRANT_CLUSTER_URL or not envs.QDRANT_API_KEY:
        raise ValueError("QDRANT_CLUSTER_URL and QDRANT_API_KEY are required")
    collection = envs.QDRANT_COLLECTION

    logger.Info(f"Loading FAQ PDF: {args.path}")
    docs = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(
        PyPDFLoader(args.path).load()
    )
    logger.Info(f"Split into {len(docs)} chunks")

    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-2-preview",
        api_key=SecretStr(envs.GEMINI_API_KEY) if envs.GEMINI_API_KEY else None,
    )
    qdrant = QdrantClient(url=envs.QDRANT_CLUSTER_URL, api_key=envs.QDRANT_API_KEY)
    if qdrant.collection_exists(collection):
        logger.Info(f"Deleting existing collection {collection}")
        qdrant.delete_collection(collection)

    qdrant.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=len(embeddings.embed_query("x")), distance=Distance.COSINE),
    )
    QdrantVectorStore(client=qdrant, collection_name=collection, embedding=embeddings).add_documents(docs)
    logger.Info(f"Indexed {len(docs)} chunks into {collection}")


if __name__ == "__main__":
    main()
