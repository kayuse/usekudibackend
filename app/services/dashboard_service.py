from typing import List

from dotenv import load_dotenv
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from app.data.account import AccountDetailsOut, TransactionOut, TransactionAverage
from app.data.user import UserOut
from app.models.account import Account
from app.models.user import User
from app.services.transaction_service import TransactionService
import os
load_dotenv(override=True)

class DashboardService:
    def __init__(self, db_session=Session):
        if not db_session:
            raise ValueError("Database session is not initialized.")
        self.db = db_session
        self.loan_category_id = os.getenv("„")
        self.transaction_service = TransactionService(db_session)

    def get_accounts(self, user: UserOut) -> List[AccountDetailsOut]:
        accounts = self.db.query(Account).filter(Account.user_id == user.id).filter(Account.active == True).all()
        result: List[AccountDetailsOut] = []
        for account in accounts:
            result.append(AccountDetailsOut(**account.__dict__))
        return result

    def get_outflow(self, user: UserOut) -> float:
        today = datetime.now()
        from_date = datetime(today.year, today.month, 1)  # first day of this month at 00:00
        to_date = today  # current datetime
        outflow = self.transaction_service.get_outflow(user.id, from_date, to_date)
        return outflow
    def get_total_spent_last_month(self, user: UserOut) -> float:
        today = datetime.now()

        # First day of this month
        first_day_this_month = datetime(today.year, today.month, 1)

        # Last day of last month = one second before first day of this month
        last_day_last_month = first_day_this_month - timedelta(seconds=1)

        # First day of last month
        first_day_last_month = datetime(last_day_last_month.year, last_day_last_month.month, 1)

        # Range
        from_date = first_day_last_month
        to_date = last_day_last_month

        outflow = self.transaction_service.get_outflow(user.id, from_date, to_date)
        return outflow


    def financial_health_score(self,transactions):
        income = sum(t.amount for t in transactions if t.transaction_type == "credit")
        expenses = sum(t.amount for t in transactions if t.transaction_type == "debit")
        debt_payment = sum(t.amount for t in transactions
                           if t.transaction_type == "debit" and t.category_id == 1)

        # Assume savings = income - expenses if not explicitly tagged
        savings = max(0, income - expenses)

        score = 0

        # Savings rate
        savings_rate = (savings / income) * 100 if income else 0
        if savings_rate >= 20:
            score += 30
        elif savings_rate >= 10:
            score += 15

        # Expense ratio
        expense_ratio = (expenses / income) * 100 if income else 0
        if expense_ratio <= 50:
            score += 20
        elif expense_ratio <= 70:
            score += 10

        # Debt-to-income
        dti = (debt_payment / income) * 100 if income else 0
        if dti <= 10:
            score += 20
        elif dti <= 30:
            score += 10

        # Emergency fund proxy (if savings >= 3x avg monthly expenses)
        months_covered = savings / (expenses / 3) if expenses else 0
        if months_covered >= 6:
            score += 20
        elif months_covered >= 3:
            score += 10

        # Bonus
        score += 5  # e.g., for consistency / positive trends

        return min(100, round(score))

    def get_daily_average(self, user: UserOut) -> TransactionAverage:
        today = datetime.now()
        from_date = datetime(today.year, today.month, 1)  # first day of this month at 00:00
        to_date = today  # current datetime

        return self.transaction_service.get_daily_average(user.id, from_date, to_date)

    def get_weekly_average(self, user: UserOut) -> TransactionAverage:
        today = datetime.now()
        from_date = datetime(today.year, today.month, 1)  # first day of this month at 00:00
        to_date = today  # current datetime
        return self.transaction_service.get_weekly_average(user.id, from_date, to_date)
