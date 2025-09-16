from typing import List

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from langchain.chains.llm import LLMChain
from langchain.output_parsers import ResponseSchema, StructuredOutputParser
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from openai import OpenAI

from app.data.account import TransactionOut
from app.data.transaction_insight import Insights, Insight
from app.data.user import UserOut
from app.models.account import TransactionInsight
from app.services.transaction_service import TransactionService
from app.util.chroma_db import get_chroma_db
import os

load_dotenv(override=True)


class TransactionAIService:
    def __init__(self, db_session=Session):
        self.db_session = db_session
        self.transaction_service = TransactionService(db_session=db_session)
        self.client = get_chroma_db()
        self.api_key = os.getenv('CHAT_GPT_KEY')
        self.insight_days = os.getenv('INSIGHT_DAYS',300)
        self.openai_client = OpenAI(api_key=os.getenv('CHAT_GPT_KEY'))

    def get_collection(self):
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.api_key,
            model_name="text-embedding-3-small"
        )
        collection = self.client.get_collection(name="transactions_insights", embedded=openai_ef)
        return collection

    def documents(self, transactions: List[TransactionOut], user: UserOut):
        insights = []
        collection = self.get_collection()
        for transaction in transactions:
            search_results = collection.query(
                n_results=1,
                where={
                    "user_id": user.id,
                    "transaction_id": transaction.id
                }
            )

            if not search_results["documents"] or len(search_results["documents"][0]) == 0:
                continue

            transaction_data = (
                f"Transaction ID : {transaction.transaction_id}, Date: {transaction.date}, Transaction Type: {transaction.transaction_type}, Amount: {transaction.amount}, "
                f"Description: {transaction.description}, Category Name: {transaction.category.name} "
                f"Category Description: {transaction.category.description}")

            collection.add_transaction(
                document=[transaction_data],
                id=[transaction.id],
                metadata=[{"user_id": f"user_{user.id}", "transaction_id": transaction.id}],
            )

        transaction_document = collection.query(
            n_results=1,
            where={
                "user_id": user.id
            }
        )

    def generate_insights(self, user: UserOut):
        today = datetime.today()
        start_of_last_week = today - timedelta(days=self.insight_days)
        end_date = today
        transactions = self.transaction_service.get_transactions(user_id=user.id, start_date=start_of_last_week,
                                                                 end_date=end_date, limit=10000)
        documents = []
        for transaction in transactions:
            if transaction.category_id is None:
                continue

            transaction_data = (
                f"Transaction ID : {transaction.transaction_id}, Date: {transaction.date}, Transaction Type: {transaction.transaction_type}, Amount: {transaction.account.currency} {transaction.amount}, "
                f"Description: {transaction.description}, Category Name: {transaction.category.name},"
                f"Category Description: {transaction.category.description}")
            documents.append(transaction_data)


        parser = PydanticOutputParser(pydantic_object=Insights)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["transaction_documents"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                        You are a financial assistant that analyzes transaction data. 
                        Your goal is to provide clear, personalized insights from a list of transactions. 
                        Always be concise, use simple language, and make the insights actionable.
                        
                        Here is a list of transactions:
                        
                        {transaction_documents}
                        
                        Based on this data, generate insights including but not limited to:
                        - Total income (credits) and total expenses (debits)
                        - Biggest spending categories or merchants
                        - Any unusual or large transactions
                        - Spending vs saving balance
                        - Suggestions for better financial health
                        
                        You may also add any other useful observations, such as:
                        - Spending trends over time
                        - Recurring payments or subscriptions
                        - Changes compared to previous periods
                        - Savings opportunities
                        - Risky or suspicious transactions
                        
                        Important output rules:
                        - Each insight must be a JSON object with the following fields:
                          - title (short headline of the insight)
                          - description (short explanation in simple language)
                          - priority (one of: "low", "medium", "high")
                          - type (one of: "recommendation", "alert", "forecast", "spending trend")
                          - action (nullable string, an optional next step for the user, can be null)
                        - Do not add explanations, comments, or any text outside the JSON.
                        - Use only the same currency shown in the transaction documents (e.g., ₦ for Naira).
                        - Do not convert to USD ($) or any other currency.
                        - Return the result strictly as a JSON list of insights using this format:
                        {format_instructions}
                        Each element MUST be an object with exactly these keys: 
                            - "title" (string)
                            - "description" (string)
                            - "priority" (one of "low", "medium", "high")
                            - "type" (one of "recommendation", "alert", "forecast", "spending trend")
                            - "action" (string or null)
                """)

        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, openai_api_key=self.api_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"transaction_documents": documents})
        print(response['text'].root)
        data: List[Insight] = response["text"].root

        self.db_session.query(TransactionInsight).filter(TransactionInsight.user_id == user.id).update(
            {"is_latest": False})
        self.db_session.commit()

        insights = [TransactionInsight(user_id=user.id, title=record.title, priority=record.priority,
                                       insight=record.description, insight_type=record.type,
                                       is_latest=True) for record in data]
        self.db_session.bulk_save_objects(insights)
        self.db_session.commit()
        return data
