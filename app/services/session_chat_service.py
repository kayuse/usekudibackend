import traceback
from datetime import datetime, timedelta
from typing import List, Optional

from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from langchain.agents import initialize_agent
from langchain.chains.llm import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain_chroma import Chroma
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.messages import SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import Tool, tool, StructuredTool
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.data.account import TransactionCategoryOut
from app.data.session import SessionAccountOut, SessionTransactionOut
from app.models.session import Session as SessionModel, SessionTransaction, SessionAccount
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.routers import transaction
from app.services.session_advice_service import SessionAdviceService
from app.services.session_service import SessionService
from app.services.session_transaction_service import SessionTransactionService
from app.services.transaction_service import TransactionService
from app.util.chroma_db import get_chroma_db

import os
import re

load_dotenv(override=True)


class SessionChatService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.pgurl = os.getenv("PG_URL")
        self.ai_key = os.getenv('CHAT_GPT_KEY')
        self.redis = os.getenv("REDIS_URL")
        self.chroma_client = get_chroma_db()
        self.table_info = "session_data_view"
        self.session_model: SessionModel = None
        self.session_transaction_key = 'sessions_transactions_{}'
        self.transaction_service = SessionTransactionService(db=db_session)
        self.session_advice_service = SessionAdviceService(db_session=db_session)
        self.N = 10
        self.llm = ChatOpenAI(api_key=self.ai_key, temperature=0, model="gpt-4o-mini")

    def process(self, session_id: str, question: str) -> str:

        try:
            self.session_model = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()

            chat_history = RedisChatMessageHistory(
                session_id=f"session_{self.session_model.identifier}",  # This is the actual key in Redis
                url=self.redis
            )
            memory = ConversationBufferMemory(memory_key="chat_history", chat_memory=chat_history, return_messages=True)
            if not self.session_model.indexed:
                self.index_transactions(self.session_model)

            tools = self.get_tools()

            agent = initialize_agent(tools, self.llm, memory=memory,
                                     agent="openai-functions", verbose=True,
                                     system_message=self.get_system_context(), max_iterations=10)

            response = agent.run(question)

            return str(response)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return "Something went wrong"

    def get_system_context(self):
        system_context = (
            "You are a financial AI assistant. "
            "When the user asks for transactions by date, always default to the current year "
            "if no date range is provided. "
            "Use today’s date to determine the current year."
        )
        return system_context

    def get_tools(self):
        sql_tool = StructuredTool.from_function(
            name="sql_query_tool",
            func=lambda q: self.generate_sql_chains(q),
            description=(
                "Use this tool to generate and execute SQL queries on structured financial data "
                "from the 'session_data_view'. "
                "Use it when the user's question involves numbers, summaries, balances, totals, "
                "categories, dates, or filtering transactions. "
                "Always include only transactions that belong to the current session (using session_id). "
                "Default to transactions from the current year if no date range is given. "
                "Return results as a clearly numbered list, even if there's only one transaction."
            )
        )
        get_accounts_tool = StructuredTool.from_function(
            func=self.get_accounts,
            name="get_accounts",
            description=(
                "Use this tool to list all user accounts available in the current session. "
                "It returns a list of accounts with their IDs, names, currencies, and types. "
                "This tool is useful when you need to find the correct account_id before calling 'get_balance'."
            ),
        )

        semantic_tool = StructuredTool.from_function(
            name="semantic_search",
            func=lambda q: self.semantic_search_metadata(q),
            description=(
                "Use this tool to find transactions based on meaning or intent, not exact keywords. "
                "Best for natural-language searches like 'money I sent to my sister' or "
                "'POS payments at restaurants'. "
                "This tool searches through transaction descriptions, categories, and related metadata "
                "in the current session. "
                "Always return transactions as a numbered list, even if only one match is found."

            )
        )
        balance_tool = StructuredTool.from_function(
            func=self.get_balance,
            name="get_balance",  # ✅ VALID name
            description=(
                "Use this tool to retrieve the current balance of a specific account. "
                "It requires an 'account_id' parameter, which can be obtained by first calling 'get_accounts'. "
                "Always ensure that the correct account ID is provided before calling this tool. "
                "The response includes the account balance, currency, and account name."
            ),
        )
        top_beneficiaries_tool = StructuredTool.from_function(
            func=self.get_top_beneficiaries,
            name="get_top_beneficiaries",
            description=(
                "Use this tool to get the top beneficiaries (people or accounts) "
                "a customer has sent money to, based on the number or total amount of debit transactions. "
                "Useful for summarizing spending habits or identifying frequent recipients."
            ),
        )
        income_category_tool = StructuredTool.from_function(
            func=self.get_income_categories,
            name="get_income_categories",
            description=(
                "Retrieves all income categories and their total credited amounts for the given accounts."
                "You must provide the list of account_ids belonging to the current session."
                "Use this when the user asks where their money comes from, how much they earned, or requests a breakdown of income sources by category."
                "Returns each income category with its total credited amount."
            ),
        )
        expense_category_tool = StructuredTool.from_function(
            func=self.get_expense_categories,
            name="get_expense_categories",
            description=(
                "Retrieves all expense categories and their total debited amounts for the given accounts."
                "You must provide the list of account_ids belonging to the current session."
                "Use this when the user asks how they spend their money, what they spent the most on, or requests a breakdown of expenses by category."
                "Returns each expense category with its total debited amount"
            ),
        )
        category_tool = StructuredTool.from_function(
            func=self.get_categories,
            name="get_categories",
            description=(
                "Retrieve the list of all available transaction categories in the system."
                "Each category includes its category_id, category_name, and a short description."
                "Use this tool when you need to:"
                "Display or list all categories to the user."
                "Match a transaction or spending to a known category."
                "Find the correct category ID before filtering transactions by category."
                "This tool does not return transactions — only category information."
            )
        )

        get_transaction_by_category_tool = StructuredTool.from_function(
            func=self.get_transaction_by_category,
            name="get_transaction_by_category",
            description=(
                "Retrieve all transactions under a specific category using the category ID. "
                "If the category ID is unknown, call the get_categories tool first to get available categories."
            )
        )
        get_transactions_by_insights = StructuredTool.from_function(
            func=self.get_insights,
            name="get_insights",
            description=(
                "Retrieve financial insights for the current session using the Session ID. Make Sure you fetch the Session ID from the get_session tool first."
                "Use this tool to get personalized financial insights based on the user's transaction history and spending patterns."
            )
        )

        get_session = StructuredTool.from_function(
            func=self.get_session,
            name="get_session",
            description=(
                "Retrieve details about the current session"
                "Use this tool to get information such as session id, name, email, overall assessment, processing status, and customer type."
            )
        )

        get_transactions_by_date_range_tool = StructuredTool.from_function(
            func=self.get_transactions_by_date_range,
            name="get_transactions_by_date_range",
            description=(
                "Retrieve all transactions for the given account IDs between a specified start and end date. If the user does not provide a date range, use this year 2025. "
                "Always use the current year when generating start_date and end_date for transactions."
                "Use this to list transactions within a date range, showing both credits and debits."
                "If no date range is provided, default to the current calendar year (e.g., 2025-01-01 to 2025-12-31)."
            )
        )
        get_category_transactions_by_date_range_tool = StructuredTool.from_function(
            func=self.get_category_transactions_by_date_range,
            name="get_category_transactions_by_date_range",
            description=(
                "Retrieve and group transactions by category within a specific date range. If the user does not provide a date range, use this year 2025. "
                "Always use the current year when generating start_date and end_date for transactions."
                "Use this to summarize total spending or income by category for the selected period, optionally filtered by transaction type (credit or debit)."
                "If no date range is provided, default to the current calendar year (e.g., 2025-01-01 to 2025-12-31)."
            )
        )

        tools = [sql_tool, semantic_tool, balance_tool, get_accounts_tool, top_beneficiaries_tool, income_category_tool,
                 expense_category_tool, category_tool, get_transaction_by_category_tool,
                 get_transactions_by_date_range_tool, get_category_transactions_by_date_range_tool,
                 get_transactions_by_insights, get_session]

        return tools

    def get_collection(self, db_name):
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.ai_key,
            model_name="text-embedding-3-large"
        )
        collection = self.chroma_client.get_or_create_collection(name=db_name, embedding_function=openai_ef)
        print("Collection {} created".format(collection.name))
        return collection

    def index_transactions(self, record: SessionModel):
        print("To Index Session Transaction {}".format(record.id))
        accounts = self.db.query(SessionAccount).filter(
            SessionAccount.session_id == self.session_model.id).all()

        account_ids = [account.id for account in accounts]
        transactions = (
            self.db.query(SessionTransaction)
            .filter(
                SessionTransaction.account_id.in_(account_ids),
                SessionTransaction.category_id.isnot(None)
            )
            .all()
        )
        print("Account IDs: {} to Index".format(account_ids))

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
                {"session_id": f"{record.id}",
                 "transaction_id": transaction.id,
                 "description": f"{transaction.description}",
                 "amount": float(transaction.amount),
                 "transaction_date": f"{transaction.date}",
                 "currency": transaction.session_account.currency,
                 "account_name": transaction.session_account.account_name,
                 "category_name": transaction.category.name,
                 "transaction_type": transaction.transaction_type, }
                for transaction in document_transactions],
        )
        self.session_model.indexed = True
        self.db.commit()
        return True

    def semantic_search_metadata(self, query: str):
        openai_ef = OpenAIEmbeddings(
            api_key=self.ai_key,
            model="text-embedding-3-large"  # higher quality
        )

        vectorstore = Chroma(
            client=self.chroma_client,
            collection_name=self.session_transaction_key.format(self.session_model.identifier),
            embedding_function=openai_ef
        )

        retriever = vectorstore.as_retriever(
            search_kwargs={
                "k": 10,
                # "where": {"session_id": self.session_model.id}  # ✅ Filter to current session
            }
        )

        results = retriever.get_relevant_documents(query)
        return results

    def get_accounts(self):
        """
        Retrieve all accounts associated with the current session or user.
        Returns a list of accounts with their IDs, names, and currencies.
        """
        print("Getting Accounts {}".format(self.session_model.id))
        accounts = self.transaction_service.get_accounts(session_id=self.session_model.id)

        if not accounts:
            return "No accounts found for this Session."

        return [
            {
                "accountId": account.id,
                "accountName": account.account_name,
                "currency": account.currency or "NGN",
                "balance": account.current_balance,
                "bank": account.bank.bank_name,
            }
            for account in accounts
        ]

    def get_balance(self, account_id: int) -> str:
        """Get the current account balance for a given account ID."""
        # Example logic — you could call your DB or API here
        balance = self.transaction_service.get_balance(account_id)
        if balance is None:
            return f"No account found with ID {account_id}."
        return balance

    def get_session(self):

        return {
            "session_id": self.session_model.id,
            "session_identifier": self.session_model.identifier,
            "session_name": self.session_model.name,
            "session_email": self.session_model.email,
            "session_overall_assessment_title": self.session_model.overall_assessment_title,
            "session_overall_assessment": self.session_model.overall_assessment,
            "session_processing_status": self.session_model.processing_status,
            "session_customer_type": self.session_model.customer_type,
            "insights": self.get_insights(session_id=self.session_model.id),
            "swot_analysis": self.get_swot(session_id=self.session_model.id),
        }

    def get_top_beneficiaries(self):
        beneficiaries = self.session_advice_service.get_session_beneficiaries(session_id=self.session_model.id)
        if not beneficiaries:
            return "No beneficiaries found."

        return [
            {
                "beneficiary": beneficiary.beneficiary,
                "amount": float(beneficiary.total_amount),
                "transaction_count": beneficiary.transaction_count
            }
            for beneficiary in beneficiaries
        ]

    def get_income_categories(self, account_ids: list[int]):
        categories: list[TransactionCategoryOut] = self.transaction_service.get_income_by_category(account_ids)
        if not categories:
            return "No categories found."
        return [
            {
                "category": category.category_name,
                "amount": category.amount,
                "category_id": category.category_id,
            }
            for category in categories
        ]

    def get_expense_categories(self, account_ids: list[int]):
        categories: list[TransactionCategoryOut] = self.transaction_service.get_expenses_by_category(account_ids)
        if not categories:
            return []
        return [
            {
                "category": category.category_name,
                "amount": category.amount,
                "category_id": category.category_id
            }
            for category in categories
        ]

    def get_categories(self):
        categories = self.transaction_service.get_categories()
        return [
            {
                "category": category.name,
                "category_id": category.id,
                "description": category.description
            }
            for category in categories
        ]

    def get_transaction_by_category(self, category_id: int) -> list[dict]:
        accounts = self.get_accounts()
        account_ids = [account['accountId'] for account in accounts]
        transactions = self.transaction_service.get_transaction_by_category(category_id, account_ids)
        if not transactions:
            return []
        return [
            {
                "transaction_id": t.transaction_id,
                "amount": t.amount,
                "description": t.description,
                "Currency": t.currency,
                "transaction_date": t.date,
                "category_id": t.category_id,
                "category_name": t.category.name,
            }
            for t in transactions
        ]

    def get_insights(self, session_id: int) -> list[dict]:
        insights = self.session_advice_service.get_insights(session_id=session_id)
        if not insights:
            return []
        return [
            {
                "title": insight.title,
                "priority": insight.priority,
                "insight_type": insight.insight_type,
                "insight": insight.insight,
            }
            for insight in insights
        ]

    def get_swot(self, session_id: int) -> list[dict]:
        swots = self.session_advice_service.get_swot(session_id=session_id)
        if not swots:
            return []
        return [
            {
                "analysis": swot.analysis,
                "swot_type": swot.swot_type,
            }
            for swot in swots
        ]

    def get_transactions_by_date_range(self, account_ids: list[int], start_date: str, end_date: str) -> list[dict]:
        transactions = self.transaction_service.get_transactions_by_date_range(account_ids, start_date, end_date)
        if not transactions:
            return []
        return [
            {
                "transaction_id": t.transaction_id,
                "amount": t.amount,
                "transaction_date": t.date,
                "currency":t.currency,
                "transaction_type": t.transaction_type,
                "category_id": t.category_id,
                "category_name": t.category.name,
            }
            for t in transactions[:50]
        ]

    def get_category_transactions_by_date_range(self, account_ids: list[int], start_date: str, end_date: str) -> list[
        dict]:
        categories = self.transaction_service.get_category_transactions_by_date_range(account_ids, start_date, end_date)
        if not categories:
            return []
        return [
            {
                "category": category.category_name,
                "amount": category.amount,
                "category_id": category.category_id
            }
            for category in categories
        ]

    def generate_sql_chains(self, question: str) -> str:
        table_info = self.table_info
        custom_prompt = PromptTemplate(
            input_variables=["question", "table_info", "session_id"],
            template=

            """
                You are an expert PostgreSQL SQL generator for a financial assistant.  
                You must generate exactly one valid PostgreSQL SELECT statement — no explanations, 
                no markdown, no comments.  
                
                The Name of the Table is {table_info} 
                And the schema is :  
                - session_id (integer)  
                - session_identifier (string)  
                - session_name (string)  
                - session_email (string)  
                - session_overall_assessment_title (string)  
                - session_overall_assessment (string)  
                - session_processing_status (string)  
                - session_customer_type (string)  
                - bank_id (int)  
                - bank_name (string)  
                - bank_code (string)
                - account_id (int)  
                - account_name (string)  
                - account_bank_id (int)  
                - account_number (int)  
                - account_active (bool)  
                - account_current_balance (float)  
                - account_type (string)  
                - category_id (string) - The Id of the Category
                - category_name (string) — name of the transaction category(food, pos, transfers, transport)
                - category_description (string) — description of the transaction category  
                - transaction_currency (string)  
                - transaction_date (datetime)  
                - transaction_amount (float)  
                - transaction_type (string: debit or credit) Do not pass any filter that's not debit or credit here always use category_name for transaction category.
                - transaction_description (string) — use ILIKE here  
                - transaction_created_at (datetime)  
                - transaction_updated_at (datetime)  
                
                RULES:  
                1. You may only query from the SQL view named {table_info}.  
                   - Do NOT query any other table or view, directly or indirectly.  
                   - Do NOT alias it to another table name unless necessary for the query to work.  
                2. Only use columns from {table_info}.  
                3. If the question requests an aggregate (SUM, COUNT, AVG), generate the correct aggregation query.  
                4. Always filter results by `session_id = {session_id}`.  
                5. Never return ID columns — return their descriptive equivalents (e.g., return `category_name` instead of `category_id`).  
                6. For string searches, use `ILIKE` with `%` wildcards (e.g., `ILIKE '%term%'`) for case-insensitive matches.  
                7. Always use the Currency in the transaction_currency or Default to Naira
                8. If no date range is specified, default to transactions from the CURRENT year.
                9. Return only syntactically correct SQL for PostgreSQL.  
                10. Only use the Columns from the Schema below 
                11. Always filter results by `session_id = {session_id}`.
                12. Always include `WHERE session_id = {session_id}` in every query, even if other filters are applied.
                
                EXAMPLE:
                Question: "Show all debit POS transactions this year"
                Output:
                SELECT category_name, transaction_description, transaction_amount, transaction_currency, transaction_date
                FROM {table_info}
                WHERE session_id = 12345
                  AND transaction_type = 'debit'
                  AND category_name ILIKE '%pos%'
                  AND EXTRACT(YEAR FROM transaction_date) = EXTRACT(YEAR FROM CURRENT_DATE);
                  
                INPUT:  
                Question: {question}  

                OUTPUT:  
                SQL Query:

            """,
        )

        sql_chain = LLMChain(llm=self.llm, prompt=custom_prompt)
        raw_sql = sql_chain.run({"question": question, "table_info": table_info, "session_id": self.session_model.id})
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

    def add_session_filter(self, sql: str, session_id: Optional[int] = None) -> str:
        """Append user_id filter safely. user_id can be int or list of ints."""
        if session_id is None:
            return sql
        # support single int or iterable
        if isinstance(session_id, (list, tuple)):
            ids = ", ".join(str(int(i)) for i in session_id)
            clause = f"session_id IN ({ids})"
        else:
            clause = f"session_id = {int(session_id)}"

        if re.search(r'\bwhere\b', sql, flags=re.IGNORECASE):
            sql = re.sub(r';\s*$', '', sql) + f" AND {clause};"
        else:
            sql = re.sub(r';\s*$', '', sql) + f" WHERE {clause};"
        return sql
