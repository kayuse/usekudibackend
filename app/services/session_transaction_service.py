from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import time
from dateutil.relativedelta import relativedelta

from dotenv import load_dotenv
from sqlalchemy import text, select, func, cast
import numpy as np
import statistics as stats

from app.data.account import TransactionCategoryOut
from app.data.session import Statement, IncomeFlowOut, IncomeCategoryOut, RiskOut, TransactionDataOut, \
    FinancialProfileDataIn, SpendingProfileOut, SessionTransactionOut, SessionAccountOut
from app.models.account import Category
from app.models.session import SessionAccount, SessionTransaction, Session as SessionModel

from app.services.ai_service import AIService
from app.services.mono_service import MonoService
import os

from app.services.session_ai_service import SessionAIService

load_dotenv(override=True)


class SessionTransactionService:
    def __init__(self, db: Session):
        self.db = db
        self.mono_service = MonoService()
        self.savings_category_id = int(os.getenv('SAVINGS_CATEGORY_ID'))
        self.session_ai_service = SessionAIService(self.db)
        self.ai_service = AIService(self.db)

    def index_transactions(self, account_id: int, start_from: datetime = None) -> bool:
        # Fetch the account from the database
        account = self.db.query(SessionAccount).filter(SessionAccount.id == account_id).first()
        if not account:
            print(f"Account with ID {account_id} not found.")
            return False
        # Fetch transactions from the Mono API
        start_from = start_from or datetime.now() - relativedelta(months=12)

        transactions_data = self.mono_service.get_transactions(start_date=start_from.strftime('%d-%m-%Y'),
                                                               end_date=datetime.now().strftime('%d-%m-%Y'),
                                                               account_id=account.account_id)
        if transactions_data is None:
            return False
        return self.upsert_transactions_from_mono(account_id, transactions_data)

    def upsert_transactions_from_mono(self, account_id: int, transactions_data: list[dict]) -> bool:
        """
        Upsert transactions from Mono API data into the database.
        :param account_id: ID of the account to associate transactions with.
        :param transactions_data: List of transaction data dictionaries from Mono API.
        :return: True if successful, False otherwise.
        """
        account = self.db.query(SessionAccount).filter(SessionAccount.id == account_id).first()
        if not account:
            print(f"Account with ID {account_id} not found.")
            return False
        if transactions_data is None:
            return False
        # Ensure transactions_data is a list
        if not isinstance(transactions_data, list):
            print("Transactions data is not a list.")
            return False
        print(f"Upserting transactions for account: {account.account_number}, "
              f"Number of transactions: {len(transactions_data)}")
        for transaction_data in transactions_data:

            existing_transaction = self.db.query(SessionTransaction).filter(
                SessionTransaction.transaction_id == transaction_data['id']).filter(
                SessionTransaction.account_id == account.id).first()
            print(f"Processing transaction ID: {transaction_data} for account: {account.account_number}")
            if existing_transaction:
                # Update existing transaction
                continue
            amount = abs((transaction_data.get('amount', 0.0) or 0.0) / 100)
            # Create a new transaction
            new_transaction = SessionTransaction(
                transaction_id=transaction_data['id'],
                account_id=account.id,
                amount=(transaction_data.get('amount', 0.0) or 0.0) / 100,
                currency=transaction_data.get('currency', 'NGN') or 'NGN',
                description=transaction_data.get('narration', ''),
                date=transaction_data['date'],
                balance_after_transaction=(transaction_data.get('balance') or 0.0) / 100,
                transaction_type=transaction_data.get('type', 'unknown') or 'unknown'
            )
            self.db.add(new_transaction)
            self.db.commit()
        account.last_synced = datetime.now()
        account.indexed = True
        self.db.commit()
        self.db.refresh(account)
        print(f"Upserted transactions for account: {account.account_number}")
        return True

    def categorize_transactions(self) -> bool:
        try:

            transactions = self.db.query(SessionTransaction).filter(SessionTransaction.category_id.is_(None)).all()
            print(f"Found {len(transactions)} transactions to categorize.")
            categories = self.db.query(Category).all()
            if not transactions:
                print("No transactions to categorize.")
                return True

            for transaction in transactions:
                # Here you would implement your logic to categorize the transaction
                # For example, you could use a machine learning model or a set of rules
                # For now, we'll just print the transaction
                print(f"Categorizing transaction: {transaction.id} - {transaction.description}")
                # Example categorization logic (to be replaced with actual logic)
                category_id = self.ai_service.categorize_session_transaction(transaction, categories)
                transaction.category_id = category_id
                self.db.commit()
                self.db.refresh(transaction)
                time.sleep(5)

            return True
        except Exception as e:
            print(f"Error categorizing transactions: {e}")
            return False

    def categorize_session_transactions(self, session_id : int) -> bool:
        try:

            accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_id).all()
            account_ids = [account.id for account in accounts]
            transactions = self.db.query(SessionTransaction).filter(SessionTransaction.account_id.in_(account_ids) & SessionTransaction.category_id.is_(None)).all()
            print(f"Found {len(transactions)} transactions to categorize.")
            categories = self.db.query(Category).all()
            if not transactions:
                print("No transactions to categorize.")
                return True

            for transaction in transactions:
                if transaction.category_id is not None:
                    continue
                print(f"Categorizing transaction: {transaction.id} - {transaction.description}")
                # Example categorization logic (to be replaced with actual logic)
                category_id = self.ai_service.categorize_session_transaction(transaction, categories)
                transaction.category_id = category_id
                self.db.commit()
                self.db.refresh(transaction)

            return True
        except Exception as e:
            print(f"Error categorizing transactions: {e}")
            return False
    def process_transaction_statements(self, account_id: int, statement: Statement) -> bool:
        print(f"Processing transaction statements for account: {account_id}, With statements {len(statement.transactions)} ")
        for transaction in statement.transactions:
            if (transaction.description is None or transaction.amount is None or transaction.transactionType
                    is None or transaction.amount is None or transaction.transactionDate is None):
                continue
            # transaction_date = datetime.strptime(transaction.transactionDate, "%Y-%m-%d %H:%M:%S")
            transaction = SessionTransaction(transaction_id=transaction.transactionId,
                                             account_id=account_id, currency=statement.accountCurrency,
                                             description=transaction.description,
                                             transaction_type=transaction.transactionType.lower(),
                                             amount=abs(transaction.amount), date=transaction.transactionDate,
                                             )
            self.db.add(transaction)

        self.db.commit()
        return True

    def get_income_flow(self, session_id: str) -> IncomeFlowOut:

        session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()

        if not session:
            raise ValueError(f"Session with ID {session_id} not found.")
        session_accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session.id).all()
        account_ids = [a.id for a in session_accounts]

        transactions = self.db.query(SessionTransaction).filter(SessionTransaction.account_id.in_(account_ids)).all()
        print(f"Found {len(transactions)} transactions to get income flow.")
        inflows = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'credit')

        outflows = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'debit')

        net_income = inflows - outflows

        closing_balance = sum(a.current_balance for a in session_accounts)

        return IncomeFlowOut(
            net_income=net_income,
            closing_balance=closing_balance,
            outflow=outflows,
            inflow=inflows
        )

    def get_spending_ratio(self, session_id: str) -> float:
        transaction_data = self.get_transactions_from_sessions(session_id)
        transactions = transaction_data.transactions
        expenses = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'debit')
        income = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'credit')
        return income / expenses

    def get_savings_ratio(self, session_id: str) -> float:
        transaction_data = self.get_transactions_from_sessions(session_id)
        transactions = transaction_data.transactions
        savings = sum(t.amount for t in transactions if t.category_id == self.savings_category_id)
        income = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'credit')
        return savings / income

    def budget_conscious_ration(self, session_id: str) -> float:
        transaction_data = self.get_transactions_from_sessions(session_id)
        volatility_risk = self.get_volatility_risk(transaction_data.transactions)
        return (1 - volatility_risk) * 100

    def get_transactions_from_sessions(self, session_id: str) -> TransactionDataOut:
        session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()

        if not session:
            raise ValueError(f"Session with ID {session_id} not found.")

        session_accounts = self.db.query(SessionAccount).filter(
            SessionAccount.session_id == session.id).all()

        account_ids: list[int] = [a.id for a in session_accounts]

        transactions = self.db.query(SessionTransaction).filter(
            SessionTransaction.account_id.in_(account_ids)).order_by(SessionTransaction.date.asc()).all()

        accounts_data: list[SessionAccountOut] = [SessionAccountOut.model_validate(account) for account in
                                                  session_accounts]

        transaction_data: list[SessionTransactionOut] = [SessionTransactionOut.model_validate(transaction) for
                                                         transaction in transactions]

        data = TransactionDataOut(
            transactions=transaction_data,
            accounts=accounts_data,
        )
        return data

    def get_risk_data(self, session_id: str) -> RiskOut:
        print(f"Getting risk data for: {session_id}")
        transaction_data = self.get_transactions_from_sessions(session_id)

        session_accounts = transaction_data.accounts
        transactions = transaction_data.transactions

        account_ids: list[int] = [a.id for a in session_accounts]

        closing_balance = sum(a.current_balance for a in session_accounts)

        start_date = transactions[0].date
        end_date = transactions[-1].date

        difference = end_date - start_date

        average_daily_outflow = self.get_income_flow(session_id).outflow / difference.days if difference.days > 0 else 1
        income_by_category = self.get_income_by_category(account_ids)

        liquidy_risk = float(closing_balance / average_daily_outflow)
        print(f"Liquidity Risk data for {session_id} is: {liquidy_risk}")

        concentration_risk = float(income_by_category[0].amount / sum(i.amount for i in income_by_category))

        expense_risk = self.calculate_expense_risk(transactions)

        volatility_risk = self.get_volatility_risk(transactions)

        return RiskOut(
            volatility_risk=volatility_risk,
            concentration_risk=concentration_risk,
            expense_risk=expense_risk,
            liquidity_risk=liquidy_risk)

    def get_income_by_category(self, account_ids: list[int]) -> list[TransactionCategoryOut]:
        stmt = (
            select(
                Category.id.label('category_id'),
                Category.name.label('category_name'),
                Category.icon.label('category_icon'),
                func.sum(SessionTransaction.amount).label("total_amount")
            )
            .join(SessionTransaction.category)
            .where(
                func.lower(func.trim(SessionTransaction.transaction_type)) == 'credit',
                SessionTransaction.account_id.in_(account_ids))
            .group_by(Category.id, Category.name, Category.icon)
        )
        results = self.db.execute(stmt).all()
        data: list[TransactionCategoryOut] = []
        print("Found {} transaction categories.".format(len(results)))
        for transaction in results:
            data.append(
                TransactionCategoryOut(
                    category_id=transaction.category_id,
                    category_name=transaction.category_name,
                    category_icon=transaction.category_icon,
                    amount=transaction.total_amount)
            )

        return data

    def get_expenses_by_category(self, account_ids: list[int]) -> list[TransactionCategoryOut]:
        stmt = (
            select(
                Category.id.label('category_id'),
                Category.name.label('category_name'),
                Category.icon.label('category_icon'),
                func.sum(SessionTransaction.amount).label("total_amount")
            )
            .join(SessionTransaction.category)
            .where(
                func.lower(func.trim(SessionTransaction.transaction_type)) == 'debit',
                SessionTransaction.account_id.in_(account_ids))
            .group_by(Category.id, Category.name, Category.icon)
        )
        results = self.db.execute(stmt).all()
        data: list[TransactionCategoryOut] = []
        print("Found {} transaction categories.".format(len(results)))
        for transaction in results:
            data.append(
                TransactionCategoryOut(
                    category_id=transaction.category_id,
                    category_name=transaction.category_name,
                    category_icon=transaction.category_icon,
                    amount=transaction.total_amount)
            )

        return data

    def calculate_expense_risk(self, transactions: list[SessionTransactionOut]) -> float:

        start_date = transactions[0].date
        end_date = transactions[-1].date

        delta = end_date - start_date
        weeks = delta.days // 7
        print("There are {} Weeks to calculate expense risk.".format(weeks))
        if weeks <= 0:
            return 0

        week_expenses = []
        for i in range(1, weeks + 1):

            weights = 10 * (i - 1)
            begin_at = start_date
            if i > 1:
                # pick the first date of the next week expense as the last date + 1
                begin_at = week_expenses[-1][1] + timedelta(days=1)

            end_date = begin_at + timedelta(days=7)

            total_amount_this_week = sum(i.amount for i in transactions if
                                         begin_at.date() <= i.date.date() <= end_date.date() and i.transaction_type.strip().lower() == 'debit')

            week_expenses.append((begin_at, end_date, total_amount_this_week, weights))
        risk_score_sum = 0

        weights = [expense[3] for expense in week_expenses]
        normalized_weights = [w / sum(weights) for w in weights]
        for index, expense in enumerate(week_expenses):

            if index <= 0:
                continue

            previous_week_expense = week_expenses[index - 1][2]
            current_week_expense = week_expenses[index][2]
            if previous_week_expense == 0:
                if current_week_expense == 0:
                    expense_growth = 0
                else:
                    expense_growth = 100
            elif current_week_expense == 0:
                expense_growth = 0
            else:
                expense_growth = ((current_week_expense - previous_week_expense) / previous_week_expense) * 100

            risk_score_sum += round(expense_growth, 2) * normalized_weights[index]

        expense_risk_score = risk_score_sum / weeks
        print("Expense Risk is: {}".format(expense_risk_score))
        return expense_risk_score

    def get_volatility_risk(self, transactions: list[SessionTransactionOut]) -> float:

        transaction_amounts = [transaction.amount for transaction in transactions if
                               transaction.transaction_type.strip().lower() == 'debit']

        sd_spending = float(np.std(transaction_amounts))
        average_spending: float = stats.mean(transaction_amounts)

        volatility_risk = sd_spending / average_spending
        print("Volatility Risk is: {}".format(volatility_risk))
        return volatility_risk

    def calculate_financial_position(self, session_id: str) -> FinancialProfileDataIn:
        income_flow = self.get_income_flow(session_id)
        spending_profile = SpendingProfileOut(
            spending_ratio=self.get_spending_ratio(session_id),
            savings_ratio=self.get_savings_ratio(session_id),
            budget_conscious=self.budget_conscious_ration(session_id)
        )
        transactions = self.get_transactions_from_sessions(session_id)
        print("Done with transactions to get transactions from sessions.")
        account_ids = [account.id for account in transactions.accounts]
        risk_data = self.get_risk_data(session_id)
        print("Risk data for session {}: {}".format(session_id, risk_data))
        return FinancialProfileDataIn(
            session_id=session_id,
            income_flow=income_flow,
            risk=risk_data,
            spending_profile=spending_profile,
            income_categories=self.get_income_by_category(account_ids),
            expense_categories=self.get_expenses_by_category(account_ids),
            transactions=transactions
        )
