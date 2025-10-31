import asyncio
from typing import List

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import time
from dateutil.relativedelta import relativedelta
from collections import defaultdict

from dotenv import load_dotenv
from sqlalchemy import text, select, func, cast
import numpy as np
import statistics as stats

from app.data.account import TransactionCategoryOut, TransactionWeekCategoryOut, WeeklyTrend
from app.data.session import Statement, IncomeFlowOut, IncomeCategoryOut, RiskOut, TransactionDataOut, \
    FinancialProfileDataIn, SpendingProfileOut, SessionTransactionOut, SessionAccountOut, SessionBeneficiaryOut
from app.models.account import Category, Account, CurrencyExchangeRate, Currency
from app.models.session import SessionAccount, SessionTransaction, Session as SessionModel, SessionBeneficiary

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

    async def categorize_session_transactions(self, session_id: int) -> bool:
        try:
            # Step 1: Fetch accounts and transactions synchronously (SQLAlchemy ORM)
            accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_id).all()
            account_ids = [account.id for account in accounts]

            transactions = (
                self.db.query(SessionTransaction)
                .filter(
                    SessionTransaction.account_id.in_(account_ids),
                    SessionTransaction.category_id.is_(None)
                )
                .all()
            )

            print(f"Found {len(transactions)} transactions to categorize.")

            if not transactions:
                print("No transactions to categorize.")
                return True

            categories = self.db.query(Category).all()

            # Step 2: Define async categorization tasks
            async def categorize_one(transaction):
                try:
                    print(f"Categorizing transaction: {transaction.id} - {transaction.description}")
                    cat_id = self.ai_service.categorize_session_transaction(transaction, categories)
                    return transaction.id, cat_id
                except Exception as e:
                    print(f"Error categorizing transaction {transaction.id}: {e}")
                    return transaction.id, None

            # Step 3: Run all categorization concurrently
            results = await asyncio.gather(*(categorize_one(t) for t in transactions))

            # Step 4: Bulk update in one DB transaction
            updated_count = 0
            for txn_id, category_id in results:
                if category_id:
                    transaction = next((t for t in transactions if t.id == txn_id), None)
                    if transaction:
                        transaction.category_id = category_id
                        updated_count += 1

            if updated_count > 0:
                self.db.commit()
                print(f"Updated {updated_count} transactions.")

            return True

        except Exception as e:
            print(f"Error categorizing transactions: {e}")
            self.db.rollback()
            return False

    def process_transaction_statements(self, account_id: int, statement: Statement) -> bool:
        print(
            f"Processing transaction statements for account: {account_id}, With statements {len(statement.transactions)} ")
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

    def convert_transaction_currency_if_needed(self, accounts: List[SessionAccountOut]) -> str:
        default_currency = accounts[0].currency if accounts and accounts[0].currency else 'USD'
        should_convert = False
        for account in accounts:
            if account.currency != default_currency:
                default_currency = 'USD'
                should_convert = True

        if not should_convert:
            return default_currency

        for account in accounts:

            if account.currency == 'USD':
                continue
            account.balance = self.convert_amount(account.balance, account.currency, 'USD')
            account.currency = 'USD'
            transactions = self.db.query(SessionTransaction).filter(
                SessionTransaction.account_id.in_([account.id])).all()
            for transaction in transactions:
                transaction.amount = self.convert_amount(transaction.amount, account.currency, 'USD')
                transaction.currency = 'USD'
            self.db.commit()

        return default_currency

    def convert_amount(self, amount: float, from_currency: str, to_currency: str) -> float:
        from_currency_id = self.db.query(Currency).filter(Currency.code == from_currency).first().id
        to_currency_id = self.db.query(Currency).filter(Currency.code == to_currency).first().id
        print(f"Converting {amount} from {from_currency} {from_currency_id} to {to_currency} {to_currency_id}")

        conversion_rate = self.db.query(CurrencyExchangeRate).filter(
            CurrencyExchangeRate.from_currency_id == to_currency_id,
            CurrencyExchangeRate.to_currency_id == from_currency_id,
        ).first().exchange_rate
        if conversion_rate is None:
            return amount
        print(f"Conversion rate: {conversion_rate}")
        converted_amount = float(amount / conversion_rate)
        print(f"Converted amount: {converted_amount}")
        return converted_amount

    def get_income_flow(self, session_id: str) -> IncomeFlowOut:

        session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()

        if not session:
            raise ValueError(f"Session with ID {session_id} not found.")
        session_accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session.id).all()
        account_ids = [a.id for a in session_accounts]
        closing_balance = sum(a.current_balance for a in session_accounts)
        transactions = self.db.query(SessionTransaction).filter(SessionTransaction.account_id.in_(account_ids)).all()
        print(f"Found {len(transactions)} transactions to get income flow.")
        inflows = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'credit')

        outflows = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'debit')

        net_income = inflows - outflows

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
        if income <= 0:
            income = 1
        ratio = (expenses / income) * 100
        return min(ratio, 200.0)

    def get_savings_ratio(self, session_id: str) -> float:
        transaction_data = self.get_transactions_from_sessions(session_id)
        transactions = transaction_data.transactions
        savings = sum(t.amount for t in transactions if t.category_id == self.savings_category_id)
        income = sum(t.amount for t in transactions if t.transaction_type.strip().lower() == 'credit')
        if income <= 0:
            income = 1
        ratio = (savings / income) * 100
        return min(ratio, 100.0)

    def budget_conscious_ration(self, session_id: str) -> float:
        transaction_data = self.get_transactions_from_sessions(session_id)
        volatility = self.get_volatility_risk(transaction_data.transactions)
        return max(0, min(100, (1 - volatility) * 100))

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
        try:
            print(f"Getting risk data for: {session_id}")
            transaction_data = self.get_transactions_from_sessions(session_id)
            print(f"Found {len(transaction_data.transactions)} transactions to get risk data.")
            print(f"Found {len(transaction_data.accounts)} accounts to get risk data.")
            session_accounts = transaction_data.accounts
            transactions = transaction_data.transactions
            if len(transactions) <= 0:
                return RiskOut(volatility_risk=0, concentration_risk=0, expense_risk=0, liquidity_risk=0)

            account_ids: list[int] = [a.id for a in session_accounts]

            closing_balance = sum(a.current_balance for a in session_accounts)

            start_date = transactions[0].date
            end_date = transactions[-1].date

            difference = end_date - start_date

            average_daily_outflow = self.get_income_flow(
                session_id).outflow / difference.days if difference.days > 0 else 1
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
        except Exception as e:
            print(e)

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

    def get_income_by_category_by_week(self, account_ids: list[int]) -> list[TransactionWeekCategoryOut]:
        six_day_interval = text("INTERVAL '6 days'")
        week_start = func.date_trunc('week', SessionTransaction.date).label('week_start')
        week_end = (func.date_trunc('week', SessionTransaction.date) + six_day_interval).label(
            'week_end')

        stmt = (
            select(
                week_start,
                week_end,
                Category.name.label('category_name'),
                Category.id.label('category_id'),
                func.sum(SessionTransaction.amount).label("total_amount")
            )
            .join(SessionTransaction.category)
            .where(
                func.lower(func.trim(SessionTransaction.transaction_type)) == 'credit',
                SessionTransaction.account_id.in_(account_ids)
            )
            .group_by(week_start, week_end, Category.id, Category.name)
            .order_by(week_start)
        )

        results = self.db.execute(stmt).all()

        # Group results by week
        weekly_data = defaultdict(list)
        week_dates = {}

        for row in results:
            week_key = row.week_start.strftime("%Y-%m-%d")
            category = TransactionCategoryOut(
                category_id=row.category_id,
                category_name=row.category_name,
                amount=float(row.total_amount)
            )
            weekly_data[week_key].append(category)
            week_dates[week_key] = row.week_end.strftime("%Y-%m-%d")

        # Convert grouped dict to list
        data = [
            TransactionWeekCategoryOut(
                week_starting=week_start,
                week_ending=week_dates[week_start],
                categories=categories
            )
            # {
            #     "week_start": week_start,
            #     "week_end": week_dates[week_start],
            #     "categories": categories
            # }
            for week_start, categories in weekly_data.items()
        ]

        print(f"Found {len(data)} weeks of income summary.")
        return data

    def get_expense_by_category_by_week(self, account_ids: list[int]) -> list[TransactionWeekCategoryOut]:
        six_day_interval = text("INTERVAL '6 days'")
        week_start = func.date_trunc('week', SessionTransaction.date).label('week_start')
        week_end = (func.date_trunc('week', SessionTransaction.date) + six_day_interval).label(
            'week_end')

        stmt = (
            select(
                week_start,
                week_end,
                Category.name.label('category_name'),
                Category.id.label('category_id'),
                func.sum(SessionTransaction.amount).label("total_amount")
            )
            .join(SessionTransaction.category)
            .where(
                func.lower(func.trim(SessionTransaction.transaction_type)) == 'debit',
                SessionTransaction.account_id.in_(account_ids)
            )
            .group_by(week_start, week_end, Category.id, Category.name)
            .order_by(week_start)
        )

        results = self.db.execute(stmt).all()

        # Group results by week
        weekly_data = defaultdict(list)
        week_dates = {}

        for row in results:
            week_key = row.week_start.strftime("%Y-%m-%d")
            category = TransactionCategoryOut(
                category_id=row.category_id,
                category_name=row.category_name,
                amount=float(row.total_amount)
            )
            weekly_data[week_key].append(category)
            week_dates[week_key] = row.week_end.strftime("%Y-%m-%d")

        # Convert grouped dict to list
        data = [
            TransactionWeekCategoryOut(
                week_starting=week_start,
                week_ending=week_dates[week_start],
                categories=categories
            )
            for week_start, categories in weekly_data.items()
        ]

        print(f"Found {len(data)} weeks of income summary.")
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

    def calculate_weekly_trend(self, session_id: str) -> WeeklyTrend:

        session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
        accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_record.id).all()
        account_ids = [account.id for account in accounts]

        income_trend = self.get_income_by_category_by_week(account_ids)
        expense_trend = self.get_expense_by_category_by_week(account_ids)

        return WeeklyTrend(income_trend=income_trend, expense_trend=expense_trend)

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
        total_weight = sum(weights)
        if total_weight == 0:
            total_weight = 1

        normalized_weights = [w / total_weight for w in weights]
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
        if len(transaction_amounts) == 0:
            return 0.0
        sd_spending = float(np.std(transaction_amounts))
        average_spending: float = stats.mean(transaction_amounts)
        if average_spending == 0:
            return 0.0

        volatility_risk = sd_spending / average_spending
        print("Volatility Risk is: {}".format(volatility_risk))
        scaled_risk = np.log1p(volatility_risk) / np.log1p(10)  # normalize roughly to 0–1 range
        scaled_risk = min(scaled_risk, 1)
        return scaled_risk

    def calculate_financial_position(self, session_id: str) -> FinancialProfileDataIn:
        income_flow = self.get_income_flow(session_id)
        print("Income Flow is: {}".format(income_flow))
        spending_profile = SpendingProfileOut(
            spending_ratio=self.get_spending_ratio(session_id),
            savings_ratio=self.get_savings_ratio(session_id),
            budget_conscious=self.budget_conscious_ration(session_id)
        )
        print("Spending Profile is: {}".format(spending_profile))
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

    def get_balance(self, account_id: int) -> str | None:
        print("Getting balance for account {}".format(account_id))
        account = self.db.query(SessionAccount).filter(SessionAccount.id == account_id).first()
        if account is None:
            return None
        return f"Balance: {account.current_balance} Currency {account.currency}"

    def get_accounts(self, session_id: int) -> list[SessionAccount]:
        accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_id).all()
        return accounts

    def get_categories(self):
        categories = self.db.query(Category).all()
        return categories

    def get_transaction_by_category(self, category_id: int, account_ids: list[int]) -> list[SessionTransactionOut]:
        transactions = self.db.query(SessionTransaction).filter(SessionTransaction.account_id.in_(account_ids),
                                                                SessionTransaction.category_id == category_id).all()
        return [SessionTransactionOut.from_orm(transaction) for transaction in transactions]

    def get_transactions_by_date_range(self, account_ids: list[int], start_date: str, end_date: str) -> list[
        SessionTransactionOut]:
        transactions = self.db.query(SessionTransaction).filter(
            SessionTransaction.account_id.in_(account_ids),
            SessionTransaction.date >= start_date,
            SessionTransaction.date <= end_date).all()
        return [SessionTransactionOut.from_orm(transaction) for transaction in transactions]

    def get_category_transactions_by_date_range(self, account_ids: list[int], start_date: str, end_date: str,
                                                ) -> list[TransactionCategoryOut]:

        stmt = (
            select(
                Category.id.label('category_id'),
                Category.name.label('category_name'),
                Category.icon.label('category_icon'),
                func.sum(SessionTransaction.amount).label("total_amount")
            )
            .join(SessionTransaction.category)
            .where(
                # transaction_type_stmt,
                SessionTransaction.account_id.in_(account_ids),
                SessionTransaction.date >= start_date,
                SessionTransaction.date <= end_date

            )
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

    def get_beneficiaries(self, session_id: str) -> list[SessionBeneficiaryOut]:
        session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
        beneficiaries = self.db.query(SessionBeneficiary).filter(
            SessionBeneficiary.session_id == session_record.id).all()

        return [SessionBeneficiaryOut.model_validate(b) for b in beneficiaries]

    def get_transfers(self, session_id: str, limit: int = 10) -> list[SessionTransactionOut]:
        session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
        accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_record.id).all()
        account_ids = [account.id for account in accounts]

        transactions = self.db.query(SessionTransaction).filter(
            SessionTransaction.account_id.in_(account_ids),
            func.lower(func.trim(SessionTransaction.transaction_type)) == 'debit'
        ).all()

        return [SessionTransactionOut.model_validate(t) for t in
                sorted(transactions, key=lambda x: x.amount, reverse=True)[:limit]]

    def get_recurring_payments(self, session_id: str, limit: int = 10) -> list[SessionTransactionOut]:
        session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
        beneficiary = self.db.query(SessionModel).filter(SessionModel.session_id == session_record.id).all()

        transactions = self.db.query(SessionTransaction).filter(
            SessionTransaction.account_id.in_(account_ids),
            func.lower(func.trim(SessionTransaction.transaction_type)) == 'debit'
        ).all()

        description_counts = defaultdict(int)
        for t in transactions:
            description_counts[t.description] += 1

        recurring_descriptions = {desc for desc, count in description_counts.items() if count > 1}

        recurring_transactions = [t for t in transactions if t.description in recurring_descriptions]

        return [SessionTransactionOut.model_validate(t) for t in
                sorted(recurring_transactions, key=lambda x: x.amount, reverse=True)[:limit]]
