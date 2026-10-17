from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from script.index_faq import main


def _envs() -> MagicMock:
    envs = MagicMock()
    envs.FAQ_PDF_PATH = "local/faq.pdf"
    envs.QDRANT_CLUSTER_URL = "https://qdrant.example"
    envs.QDRANT_API_KEY = "key"
    envs.QDRANT_COLLECTION = "faq"
    envs.GEMINI_API_KEY = "gemini"
    return envs


class TestIndexFaq:
    def test_deletes_existing_collection_then_adds_chunks(self):
        client = MagicMock()
        client.collection_exists.return_value = True
        embeddings = MagicMock()
        embeddings.embed_query.return_value = [0.0] * 8
        store = MagicMock()
        chunks = [Document(page_content="a"), Document(page_content="b")]
        splitter = MagicMock()
        splitter.split_documents.return_value = chunks

        with (
            patch("script.index_faq.Environments", return_value=_envs()),
            patch("script.index_faq.Logger"),
            patch("script.index_faq.PyPDFLoader"),
            patch("script.index_faq.RecursiveCharacterTextSplitter", return_value=splitter),
            patch("script.index_faq.GoogleGenerativeAIEmbeddings", return_value=embeddings),
            patch("script.index_faq.QdrantClient", return_value=client),
            patch("script.index_faq.QdrantVectorStore", return_value=store),
        ):
            main(["--path", "local/faq.pdf"])

        client.delete_collection.assert_called_once_with("faq")
        client.create_collection.assert_called_once()
        store.add_documents.assert_called_once_with(chunks)

    def test_skips_delete_when_collection_is_missing(self):
        client = MagicMock()
        client.collection_exists.return_value = False
        embeddings = MagicMock()
        embeddings.embed_query.return_value = [0.0] * 8
        splitter = MagicMock()
        splitter.split_documents.return_value = []

        with (
            patch("script.index_faq.Environments", return_value=_envs()),
            patch("script.index_faq.Logger"),
            patch("script.index_faq.PyPDFLoader"),
            patch("script.index_faq.RecursiveCharacterTextSplitter", return_value=splitter),
            patch("script.index_faq.GoogleGenerativeAIEmbeddings", return_value=embeddings),
            patch("script.index_faq.QdrantClient", return_value=client),
            patch("script.index_faq.QdrantVectorStore", return_value=MagicMock()),
        ):
            main(["--path", "local/faq.pdf"])

        client.delete_collection.assert_not_called()
        client.create_collection.assert_called_once()
