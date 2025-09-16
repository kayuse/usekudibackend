from datetime import datetime

from celery.beat import Service
from sqlalchemy.orm import Session
from sqlalchemy import text, select, func, and_

from app.data.account import BudgetCreate, BudgetOut, BudgetInsightOut
from app.data.user import UserOut
from app.models.account import Budget, Account, Category, Transaction


class BudgetService():
    def __init__(self, db_session=Session):
        if not db_session:
            raise ValueError("Database session is not initialized.")
        self.db = db_session

    def add_budget(self, budget_create: BudgetCreate, user: UserOut) -> BudgetOut:
        existing_budget = self.db.query(Budget).filter(Budget.category_id == budget_create.category_id,
                                                       Budget.user_id == user.id).first()
        if existing_budget:
            raise ValueError("Budget already exists.")

        budget = Budget(category_id=budget_create.category_id,
                        user_id=user.id,
                        name=budget_create.name,
                        amount=budget_create.amount)
        self.db.add(budget)
        self.db.commit()
        self.db.refresh(budget)
        return BudgetOut.from_orm(budget)

    def get_budget_insights(self, from_date: datetime, to_date: datetime, user: UserOut) -> list[BudgetInsightOut]:
        account_ids = self.db.query(Account.id).filter(Account.user_id == user.id).all()
        account_ids = [id for (id,) in account_ids]
        results = (
            self.db.query(
                Budget.name.label("budget_name"),
                Budget.amount.label("planned_amount"),
                func.coalesce(func.sum(Transaction.amount), 0).label("actual_amount"),
                (Budget.amount - func.coalesce(func.sum(Transaction.amount), 0)).label("variance")
            )
            .join(Category, Category.id == Budget.category_id)
            .outerjoin(
                Transaction,
                and_(
                    Transaction.category_id == Budget.category_id,
                    Transaction.transaction_type == "debit",
                    Transaction.account_id.in_(account_ids) ,
                    Transaction.date >= from_date,
                    Transaction.date <= to_date,
                    # filter by accounts
                )
            )
            .group_by(Budget.id, Budget.name, Budget.amount)
            .all()
        )
        insights : list[BudgetInsightOut] = []
        for result in results:
            insight = BudgetInsightOut(
                budget_name=result.budget_name,
                variance= result.variance,
                planned_amount=result.planned_amount,
                actual_amount=result.actual_amount
            )
            insights.append(insight)
        return insights

