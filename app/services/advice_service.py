from datetime import timedelta, datetime
from typing import Optional, List

from chromadb.utils import embedding_functions
from langchain_openai import OpenAIEmbeddings
from langchain.chains.llm import LLMChain
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_community.vectorstores import Chroma
from requests import Session
from langchain_openai import ChatOpenAI
import re
from langchain.memory import ConversationBufferMemory
from langchain_postgres import PGVector
from langchain_openai import OpenAIEmbeddings
from langchain.prompts.prompt import PromptTemplate
from sqlalchemy import text
from langchain.agents import initialize_agent, Tool

from app.data.account import TransactionOut
from app.data.user import UserOut
from app.database.index import engine
from app.models.account import Account
from app.models.user import User
import os
from dotenv import load_dotenv

from app.services.transaction_service import TransactionService
from app.util.chroma_db import get_chroma_db

load_dotenv(override=True)


class AdviceService:

    def __init__(self, db_session: Session):
        self.db = db_session
        self.pgurl = os.getenv("PG_URL")
        self.ai_key = os.getenv('CHAT_GPT_KEY')
        self.redis = os.getenv("REDIS_URL")
        self.chroma_client = get_chroma_db()
        self.user = None
        self.transaction_service = TransactionService(db_session=db_session)
        self.N = 10
        self.llm = ChatOpenAI(api_key=self.ai_key, temperature=0, model="gpt-4o-mini")

    def process(self, user: UserOut, question: str) -> str:

        try:
            self.user = user
            chat_history = RedisChatMessageHistory(
                session_id=f"user_{user.id}",  # This is the actual key in Redis
                url=self.redis
            )
            memory = ConversationBufferMemory(memory_key="chat_history", chat_memory=chat_history, return_messages=True)

            sql_tool = Tool(
                name="SQL Query Tool",
                func=lambda q: self.generate_sql_chains(q, table_info="data_view", user=user),
                description="Use this tool to query the SQL database when the question is about structured data. Always return transactions as a numbered list even if it's one. Always default to the Current Year"
            )
            semantic_tool = Tool(
                name="Semantic Transaction Search",
                func=lambda q: self.semantic_search_metadata(q),
                description="Use this for finding transactions by meaning, not exact keywords. Using the data_view table. Always return transactions as a numbered list even if it's one. Always default to the Current Year",
            )

            tools = [semantic_tool, sql_tool]

            agent = initialize_agent(tools, self.llm, memory=memory, agent="zero-shot-react-description", verbose=True,
                                     max_iterations=10)
            response = agent.run(question)

            return str(response)
        except Exception as e:
            print(e)
            return "Something went wrong"

    def get_collection(self):
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.ai_key,
            model_name="text-embedding-3-small"
        )
        collection = self.chroma_client.get_or_create_collection(name="chat_engine", embedding_function=openai_ef)
        return collection

    def index_documents(self, transactions: List[TransactionOut], user: UserOut):
        collection = self.get_collection()
        for transaction in transactions:
            existing = collection.get(
                where={
                    "$and": [
                        {"user_id": {"$eq": user.id}},
                        {"transaction_id": {"$eq": transaction.id}}
                    ]
                }
            )

            if existing and len(existing["ids"]) > 0:
                continue

            transaction_data = (
                f"Transaction ID : {transaction.transaction_id}, Date: {transaction.date}, Transaction Type: {transaction.transaction_type}, Amount: {transaction.account.currency} {transaction.amount}, "
                f"Description: {transaction.description}, Category Name: {transaction.category.name},"
                f"Category Description: {transaction.category.description}")

            collection.add(
                documents=[transaction_data],
                ids=[f"{transaction.id}"],
                metadatas=[{"user_id": f"user_{user.id}", "transaction_id": transaction.id}],
            )

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

    def semantic_search_metadata(self, query):
        index_document = False
        if index_document:
            today = datetime.today()
            start_of_last_week = today - timedelta(days=300)
            end_date = today
            user_transactions = self.transaction_service.get_transactions(user_id=self.user.id,
                                                                          start_date=start_of_last_week,
                                                                          end_date=end_date, limit=10000)
            self.index_documents(user_transactions, self.user)

        openai_ef = OpenAIEmbeddings(
            api_key=self.ai_key,
            model="text-embedding-3-small"
        )
        vectorstore = Chroma(
            client=self.chroma_client,
            collection_name="chat_engine",
            embedding_function=openai_ef
        )
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

        return retriever.invoke(query)

    def generate_sql_chains(self, question: str, table_info: str, user: UserOut) -> str:

        custom_prompt = PromptTemplate(
            input_variables=["input", "table_info", "user_id"],
            template=

            """
                You are an expert PostgreSQL SQL generator for a financial assistant.  
                You must generate exactly one valid PostgreSQL SELECT statement — no explanations, no markdown, no comments.  
                
                RULES:  
                1. You may only query from the SQL view named {table_info}.  
                   - Do NOT query any other table or view, directly or indirectly.  
                   - Do NOT alias it to another table name unless necessary for the query to work.  
                2. Only use columns from {table_info}.  
                3. If the question requests an aggregate (SUM, COUNT, AVG), generate the correct aggregation query.  
                4. Always filter results by `user_id = {user_id}`.  
                5. Never return ID columns — return their descriptive equivalents (e.g., return `category_name` instead of `category_id`).  
                6. For string searches, use `ILIKE` with `%` wildcards (e.g., `ILIKE '%term%'`) for case-insensitive matches.  
                7. Always use the Currency in the transaction_currency or Default to Naira
                8. If no date range is specified, default to transactions from the CURRENT year.
                9. Return only syntactically correct SQL for PostgreSQL.  
                
                {table_info} schema:  
                - user_id (integer)  
                - user_username (string)  
                - user_mobile (string)  
                - user_email (string)  
                - user_fullname (string)  
                - user_firstname (string)  
                - user_lastname (string)  
                - user_is_active (bool)  
                - user_is_superuser (bool)  
                - user_created_at (datetime)  
                - user_updated_at (datetime)  
                - bank_id (int)  
                - bank_name (string)  
                - account_id (int)  
                - account_name (string)  
                - account_bank_id (int)  
                - account_number (int)  
                - account_active (bool)  
                - account_type (string)  
                - category_name (string) — name of the transaction category(food, pos, transfers, transport)
                - category_description (string) — description of the transaction category  
                - transaction_currency (string)  
                - transaction_date (datetime)  
                - transaction_amount (float)  
                - transaction_type (string: debit or credit) Do not pass any filter that's not debit or credit here always use category_name for transaction category.
                - transaction_description (string) — use ILIKE here  
                - transaction_created_at (datetime)  
                - transaction_updated_at (datetime)  
                
                
                INPUT:  
                Question: {question}  
                
                OUTPUT:  
                SQL Query:

            """,
        )

        sql_chain = LLMChain(llm=self.llm, prompt=custom_prompt)
        raw_sql = sql_chain.run({"question": question, "table_info": table_info, "user_id": user.id})
        sql = self.clean_sql(raw_sql)
        print(sql + " ssssss")
        if not self.is_safe_select(sql):
            return "Refusing to execute SQL: not allowed or not a SELECT/ WITH statement."

        res = self.db.execute(text(sql))
        keys = res.keys()  # column names
        rows = res.fetchall()  # list of Row objects

        if not rows:
            return "No rows returned."

            # format as a small table string (first N rows)
        header = " | ".join(keys)
        lines = [header, "-" * len(header)]
        for r in rows[:self.N]:
            # r is a Row; convert each col to string
            lines.append(" | ".join("" if v is None else str(v) for v in r))
        if len(rows) > self.N:
            lines.append(f"... {len(rows)} rows total (showing first {self.N})")
        return "\n".join(lines)

    def clean_sql(self, raw_sql: str) -> str:
        s = re.sub(r"```(?:sql)?", "", raw_sql, flags=re.IGNORECASE)
        s = s.replace("`", "")
        return s.strip()

    def is_safe_select(self, sql: str) -> bool:
        """Basic safety: allow only SELECT/ WITH at the start; disallow DML/DDL keywords."""
        s = sql.strip().lower()
        # must start with or select
        if not re.match(r'^(with|select)\b', s):
            return False
        # disallow dangerous keywords
        forbidden = ["insert", "update", "delete", "drop", "alter", "create", "truncate", ";--"]
        for kw in forbidden:
            if re.search(r'\b' + re.escape(kw) + r'\b', s):
                return False
        return True

    def add_user_filter(self, sql: str, user_id: Optional[int] = None) -> str:
        """Append user_id filter safely. user_id can be int or list of ints."""
        if user_id is None:
            return sql
        # support single int or iterable
        if isinstance(user_id, (list, tuple)):
            ids = ", ".join(str(int(i)) for i in user_id)
            clause = f"user_id IN ({ids})"
        else:
            clause = f"user_id = {int(user_id)}"

        if re.search(r'\bwhere\b', sql, flags=re.IGNORECASE):
            sql = re.sub(r';\s*$', '', sql) + f" AND {clause};"
        else:
            sql = re.sub(r';\s*$', '', sql) + f" WHERE {clause};"
        return sql
