import chromadb


def get_chroma_db():
    client = chromadb.PersistentClient(path="./chroma_db")
    return client