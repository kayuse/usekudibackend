import asyncio
from datetime import timedelta, datetime
from typing import Optional, List

import pandas as pd
from chromadb.utils import embedding_functions
from langchain.chains.llm import LLMChain
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_community.vectorstores import Chroma
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from pandas import DataFrame
from sklearn.cluster import KMeans
import numpy as np
from langchain_openai import OpenAIEmbeddings
from requests import session

from app.data.session import SessionTransactionOut
from app.data.transaction_insight import OverallAssessment, ClusteredTransactionNames, TransactionBeneficiary, \
    TransactionBeneficial
from app.models.session import Session as SessionModel, SessionTransaction, SessionAccount, SessionBeneficiary
from langchain.prompts.prompt import PromptTemplate
from sqlalchemy import text
from langchain.agents import initialize_agent, Tool
from sqlalchemy.orm import Session

from app.data.account import TransactionOut
from app.data.user import UserOut
import os
from dotenv import load_dotenv

from app.services.transaction_service import TransactionService
from app.util.chroma_db import get_chroma_db

load_dotenv(override=True)


class SessionAdviceService:

    def __init__(self, db_session: Session):
        self.db = db_session
        self.ai_key = os.getenv('CHAT_GPT_KEY')
        self.redis = os.getenv("REDIS_URL")
        self.chroma_client = get_chroma_db()
        self.session_transaction_key = 'sessions_transactions_{}'
        self.user = None
        self.p2p_category_id = os.getenv('PEER_TO_PEER_CATEGORY_ID')
        self.N = 10
        self.llm = ChatOpenAI(api_key=self.ai_key, temperature=0, model="gpt-4o-mini")

    def save_top_beneficiaries(self, session_record: SessionModel,
                               transaction_benefices: List[TransactionBeneficial]) -> bool:
        """
        transactions: list of dicts or objects with fields
        - transaction_type
        - description
        - amount
        """

        records = []

        for tx in transaction_benefices:
            # Only include money you SEND (debits/transfers)
            records.append({
                "beneficiary": tx.name,
                "amount": float(tx.amount),
            })

        # Convert to DataFrame
        df = pd.DataFrame(records)

        if df.empty:
            return False

        # Aggregate total amount & transaction count
        agg = (
            df.groupby("beneficiary", as_index=False)
            .agg(total_amount=("amount", "sum"), tx_count=("amount", "size"))
            .sort_values("total_amount", ascending=False)
        )

        # Get top 5
        top5 = agg.head(100)
        data = []
        for _, row in top5.iterrows():
            beneficiary = SessionBeneficiary(
                session_id=session_record.id,
                beneficiary=row['beneficiary'],
                total_amount=row['total_amount'],
                transaction_count=row['tx_count']
            )
            data.append(beneficiary)

        self.db.bulk_save_objects(data)
        self.db.commit()
        return True

    def get_recurring_expenses(self, session_id: str) -> list[dict]:
        """
        Detect recurring expenses from a list of transaction objects.
        Includes frequency detection (daily, weekly, monthly, etc.)
        """

        records = []
        session_record: SessionModel = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
        accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_record.id).all()
        account_ids = [account.id for account in accounts]
        transactions: List[SessionTransaction] = self.db.query(SessionTransaction).filter(
            SessionTransaction.account_id.in_(account_ids)).all()
        if len(transactions) == 0:
            return False
        for tx in transactions:
            records.append({
                "transaction_type": tx.transaction_type,
                "description": tx.description.strip() if tx.description else "Unknown",
                "amount": float(tx.amount),
                "date": pd.to_datetime(tx.date)
            })

        df = pd.DataFrame(records)
        df = df[df["transaction_type"].isin(["debit", "transfer"])]

        if df.empty:
            return pd.DataFrame(
                columns=["description", "amount_rounded", "tx_count", "first_date", "last_date", "avg_amount",
                         "frequency"])

        df["amount_rounded"] = df["amount"].round(-2)

        recurring = (
            df.groupby(["description", "amount_rounded"])
            .agg(
                tx_count=("amount", "size"),
                first_date=("date", "min"),
                last_date=("date", "max"),
                avg_amount=("amount", "mean"),
                dates=("date", lambda x: sorted(list(x)))
            )
            .reset_index()
        )

        recurring = recurring[recurring["tx_count"] >= 3]

        # Detect frequency
        def detect_frequency(dates):
            if len(dates) < 2:
                return "unknown"
            gaps = pd.Series(dates).diff().dt.days.dropna()
            avg_gap = gaps.mean()

            if avg_gap <= 2:
                return "daily"
            elif avg_gap <= 10:
                return "weekly"
            elif avg_gap <= 40:
                return "monthly"
            elif avg_gap <= 100:
                return "quarterly"
            else:
                return "irregular"

        recurring["frequency"] = recurring["dates"].apply(detect_frequency)
        recurring.drop(columns=["dates"], inplace=True)

        data = recurring.sort_values("tx_count", ascending=False)
        response = []
        for index, row in data.iterrows():
            response.append({
                "description": row['description'],
                "amount_rounded": row['amount_rounded'],
                "tx_count": row['tx_count'],
                "first_date": row['first_date'],
                "last_date": row['last_date'],
                "avg_amount": row['avg_amount'],
                "frequency": row['frequency']
            })

        return response

    def get_top_transfer_beneficiaries(self, session_id: str):
        session_record: SessionModel = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()

        collection = self.get_collection(self.session_transaction_key.format(session_record.identifier))
        results = collection.get(where=
        {"$and": [
            {"transaction_type": {"$eq": "Debit"}},
            {"category_id": {"$eq": 4}}
        ]
        }, include=["embeddings", "metadatas", "documents"])
        similarity_details = self.get_to_exclude_similarity(session_id, session_record.name)
        filtered = [
            (doc, meta, emb)
            for doc, meta, emb in zip(
                results["documents"], results["metadatas"], results["embeddings"]
            )
            if meta["description"] not in similarity_details  # you can make this semantic later
        ]

        if not filtered:
            print("⚠️ No transactions left after filtering")
            return pd.DataFrame()
        print(filtered[0][0])
        # --- Step 5: Convert to DataFrame ---
        df = pd.DataFrame(
            [
                {
                    **meta,  # expand metadata into columns
                    "description": doc,
                    "embedding": emb,
                }
                for doc, meta, emb in filtered
            ]
        )

        # --- Step 6: Run KMeans clustering ---
        X = np.vstack(df["embedding"].values)  # embeddings into 2D array
        kmeans = KMeans(n_clusters=20, random_state=42)
        labels = kmeans.fit_predict(X)
        df["cluster"] = labels

        # Option A: Representative name = first description in cluster

        agg = (
            df.groupby("description", as_index=False)
            .agg(total_amount=("amount", "sum"), tx_count=("amount", "size"))
            .sort_values("total_amount", ascending=False)
        )

        top5 = agg.head(5)

        for _, row in top5.iterrows():
            # Just use the description directly
            transaction_descriptions = [row["description"]]
            response = self.get_cluster_name(transaction_descriptions)
            print(f"Beneficiary: {row['description']} → {response}")

        return True

    async def process_top_beneficiaries(self, session_id: str):
        async def handle_transaction(transaction: SessionTransaction):
            try:
                response = self.detect_beneficiary(session_record.name, transaction)
                print(response)
                if response.is_self:
                    return None
                return TransactionBeneficial(name=response.name, amount=transaction.amount)
            except:
                return None

        records = []
        session_record: SessionModel = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
        accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_record.id).all()
        account_ids = [account.id for account in accounts]
        transactions: List[SessionTransaction] = self.db.query(SessionTransaction).filter(
            SessionTransaction.account_id.in_(
                account_ids), SessionTransaction.category_id == self.p2p_category_id,
                              SessionTransaction.transaction_type == 'debit').all()

        results = await asyncio.gather(
            *(handle_transaction(tx) for tx in transactions),
            return_exceptions=False
        )
        transaction_beneficials: List[TransactionBeneficial] = [r for r in results if r]
        self.save_top_beneficiaries(session_record, transaction_beneficials)

    def get_to_exclude_similarity(self, session_id, name_to_exclude) -> set:
        ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.ai_key,
            model_name="text-embedding-3-small"
        )

        # Step 1: Get embedding of the name you want to exclude
        target_embedding = ef([name_to_exclude])[0]
        collection = self.get_collection(self.session_transaction_key.format(session_id))
        results_to_fetch = 2500
        if collection.count() < results_to_fetch:
            results_to_fetch = collection.count()
        similar_results = self.get_collection(self.session_transaction_key.format(session_id)).query(
            query_embeddings=[target_embedding],
            n_results=results_to_fetch,  # fetch top 10 similar
            include=["metadatas", "documents", 'embeddings', "distances"]
        )
        to_exclude = set()
        for meta, dist in zip(similar_results["metadatas"][0], similar_results["distances"][0]):
            if dist < 1:  # adjust threshold (0.0 = identical, 1.0 = very different)
                to_exclude.add(meta["description"])

        return to_exclude

    def get_collection(self, db_name):
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.ai_key,
            model_name="text-embedding-3-small"
        )
        collection = self.chroma_client.get_or_create_collection(name=db_name, embedding_function=openai_ef)
        print("Collection {} created".format(collection.name))
        return collection

    def index_transactions(self, record: SessionModel, transactions: List[SessionTransaction]):
        collection = self.get_collection(self.session_transaction_key.format(record.identifier))
        document_transactions = []
        for transaction in transactions:
            existing = collection.get(
                where={
                    "$and": [
                        {"session_id": {"$eq": record.id}},
                        {"transaction_id": {"$eq": transaction.id}}
                    ]
                }
            )

            if existing and len(existing["ids"]) > 0:
                continue

            document_transactions.append(transaction)

        collection.add(
            documents=[SessionAdviceService.get_description_data(t) for t in document_transactions],
            ids=[f"{t.id}" for t in document_transactions],
            metadatas=[
                {"session_id": f"{record.identifier}", "transaction_id": transaction.id, "description":
                    f"{transaction.description}", "amount": float(transaction.amount),
                 "account_name": transaction.session_account.account_name,
                 "category_id": transaction.category.id,
                 "category_name": transaction.category.name, "transaction_type": transaction.transaction_type, }
                for transaction in document_transactions],
        )
        return True

    def get_transaction_data(self, transaction: SessionTransaction):
        return (
            f"Transaction ID : {transaction.transaction_id}, Date: {transaction.date}, Transaction Type: {transaction.transaction_type}, Amount: {transaction.session_account.currency} {transaction.amount}, "
            f"Description: {transaction.description}, Category Name: {transaction.category.name},"
            f"Category Description: {transaction.category.description}")

    def get_cluster_name(self, names: list[str]):

        parser = PydanticOutputParser(pydantic_object=ClusteredTransactionNames)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["names"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                    You are a financial assistant that analyzes transaction data.  
                    Your goal is to provide a clear and meaningful summary for a cluster of related transactions.  
                    Always be concise, use simple language, and make the insights actionable.  
                    
                    Here are the clustered transaction descriptions:  
                    {names}  
                    
                    Your Task:  
                    - Identify the overall theme or purpose in these transactions.  
                    - Generate a short "name" that captures the essence of the cluster.  
                    - Write a "description" that explains what these transactions are about in simple terms.  
                    - If multiple beneficiaries are involved, summarize the common purpose (e.g., family support, business payments, utility bills).  
                    - Do NOT just repeat one beneficiary’s name unless they clearly dominate all the transactions.  
                    
                    Important Output Rules:  
                    - The "name" should be a short label (e.g., "Family Support Transfers", "Regular Bill Payments", "Work-Related Expenses").  
                    - The "description" should summarize what these transactions are about in plain words.  
                    - Focus on summarizing the group as a whole.  
                    
                    {format_instructions}  
                    
                    - Always return ONLY a JSON object with exactly these two fields:  
                      "name": "string"  
                      "description": "string"  
                    - Do not include any other fields.

                     """)
        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"names": names})
        data = response["text"]

        return data

    def detect_beneficiary(self, name: str, transaction: SessionTransaction) -> TransactionBeneficiary:

        parser = PydanticOutputParser(pydantic_object=TransactionBeneficiary)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["description"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                        You are a financial assistant that analyzes transaction data.
                        Your goal is to identify who the money was sent to.
                        
                        Here is the transaction narration/description:
                        {description}
                        
                        Here is the account owner’s name:
                        {name}
                        
                        Your Task:
                        
                        Identify the beneficiary (the recipient of the funds) from the narration.
                        
                        If the beneficiary is the same person as the account owner (or a close variation of their name), set "self": true.
                        
                        Otherwise, set "self": false.
                        
                        Important Output Rules:
                        
                        Always return ONLY a JSON object with exactly these two fields:
  
                          "name": "string",
                          "is_self": boolean

                     """)
        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"description": transaction.description, "name": name})
        data: TransactionBeneficiary = response["text"]

        return data

    @staticmethod
    def get_description_data(transaction: SessionTransaction):
        return (f"Transaction: {transaction.description}. "
                f"Category: {transaction.category.name}. "
                f"Type: {transaction.transaction_type}. "
                f"Amount: {transaction.amount} {transaction.session_account.currency}. "
                f"Account: {transaction.session_account.account_name}.")

    def get_documents(self, query: str, user: UserOut):
        collection = self.get_collection()
        transaction_documents = collection.query(
            query=query,
            n_results=10,
            where={
                "user_id": user.id
            }
        )
        return transaction_documents

    def get_session_beneficiaries(self, session_id: int) -> list[SessionBeneficiary]:
        beneficiaries = self.db.query(SessionBeneficiary).filter(SessionBeneficiary.session_id == session_id).all()
        return beneficiaries
