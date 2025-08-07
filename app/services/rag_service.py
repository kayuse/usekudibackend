class RAGService:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    async def add_document(self, document):
        """
        Add a document to the vector store.
        """
        await self.vector_store.add_document(document)

    async def query(self, query_text):
        """
        Query the vector store and return relevant documents.
        """
        return await self.vector_store.query(query_text)

    async def delete_document(self, document_id):
        """
        Delete a document from the vector store by its ID.
        """
        await self.vector_store.delete_document(document_id)