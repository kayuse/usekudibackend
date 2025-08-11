from typing import Optional

from langchain.chains.llm import LLMChain
from langchain_community.chat_message_histories import RedisChatMessageHistory
from requests import Session
from langchain_openai import ChatOpenAI
import re
from langchain.memory import ConversationBufferMemory
from langchain_postgres import PGVector
from langchain_openai import OpenAIEmbeddings
from langchain.prompts.prompt import PromptTemplate
from sqlalchemy import text
from langchain.agents import initialize_agent, Tool
from app.database.index import engine
from app.models.account import Account
from app.models.user import User
import os
from dotenv import load_dotenv

load_dotenv(override=True)


class AdviceService:

    def __init__(self, db_session: Session):
        self.db = db_session
        self.pgurl = os.getenv("PG_URL")
        self.ai_key = os.getenv('CHAT_GPT_KEY')
        self.redis = os.getenv("REDIS_URL")
        self.N = 10
        self.llm = ChatOpenAI(api_key=self.ai_key, temperature=0, model="gpt-4o-mini")

    def process(self, user: User, question: str) -> str:

        try:
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
                func=lambda q: self.semantic_search_metadata,
                description="Use this for finding transactions by meaning, not exact keywords. Using the data_view table. Always return transactions as a numbered list even if it's one. Always default to the Current Year",
            )

            tools = [semantic_tool, sql_tool]

            agent = initialize_agent(tools, self.llm, memory=memory, agent="zero-shot-react-description", verbose=True,
                                     max_iterations=8)
            response = agent.run(question)

            return str(response)
        except Exception as e:
            print(e)
            return "Something went wrong"

    def semantic_search_metadata(self, query):
        embeddings = OpenAIEmbeddings(api_key=self.ai_key, model="text-embedding-ada-002")

        vectorstore = PGVector(connection=engine, embeddings=embeddings, collection_name="data_view")
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

        docs = retriever.get_relevant_documents(query)
        return [
            {
                "id": doc.metadata["transaction_id"],
                "description": doc.page_content,
                "amount": doc.metadata["amount"],
                "date": doc.metadata["transaction_date"]
            }
            for doc in docs
        ]

    def generate_sql_chains(self, question: str, table_info: str, user: User) -> str:

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
                - category_name (string) — name of the transaction category pass transaction_type here....
                - category_description (string) — description of the transaction category  
                - transaction_currency (string)  
                - transaction_date (datetime)  
                - transaction_amount (float)  
                - transaction_type (string: debit or credit) Do not pass any filter that's not debit or credit here always use category_name
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
