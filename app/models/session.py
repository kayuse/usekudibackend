from enum import Enum
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, Integer, Boolean, Float, DateTime, func, Enum as SqlEnum, ForeignKey
from app.database.index import Base
from app.models.account import FetchMethod

from sqlalchemy.orm import relationship


class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False, unique=False)
    identifier = Column(String(500), nullable=False, unique=True)
    email = Column(String, nullable=False)
    processing_status = Column(String, nullable=True)
    customer_type = Column(String(50), nullable=True, default='individual')
    overall_assessment = Column(String, nullable=True)
    overall_assessment_title = Column(String, nullable=True)
    session_accounts = relationship("SessionAccount", back_populates="session")


class SessionAccount(Base):
    __tablename__ = 'session_accounts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String(100), nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    account_number = Column(String(50), nullable=False, unique=False)
    active = Column(Boolean, nullable=False, default=False)  # 1 for active, 0 for inactive
    account_type = Column(String, nullable=True, default=0.0)
    account_id = Column(String, nullable=True, default='',
                        unique=False)  # Mono account ID, can be null if not applicable
    current_balance = Column(Float, nullable=False, default=0.0)
    indexed = Column(Boolean, nullable=True, default=False)  # Indicates if the account has been indexed
    currency = Column(String(10), nullable=False, default="NGN")
    fetch_method = Column(String(10), nullable=False, default="api")
    bank = relationship("Bank", foreign_keys=[bank_id])
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)  # Assuming a User model exists
    session = relationship(Session, back_populates="session_accounts")  # Assuming a User model exists
    session_transactions = relationship("SessionTransaction", back_populates="session_account",
                                        cascade="all, delete-orphan")
    last_synced = Column(DateTime, nullable=True)  # Last time the account was synced
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Account(accountid={self.account_id}, account_name='{self.account_name}', account_number='{self.account_number}',bank='{self.bank_id}', active={self.active}, account_type='{self.account_type}', current_balance={self.current_balance}, currency='{self.currency}', fetch_method='{self.fetch_method}')>"


class SessionTransaction(Base):
    __tablename__ = 'session_transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("session_accounts.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)  # Optional category for the transaction
    transaction_id = Column(String(200), nullable=False, unique=False, default='')  # Mono transaction ID
    currency = Column(String(10), nullable=False, default="NGN")
    date = Column(DateTime, nullable=False, default=func.now())  # Transaction date
    balance_after_transaction = Column(Float, nullable=False, default=0.0)  # Balance after the transaction
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(50), nullable=False)  # e.g., 'credit', 'debit'
    description = Column(String(255), nullable=True)
    session_account = relationship(SessionAccount, back_populates="session_transactions")
    category = relationship("Category", backref="session_transactions", foreign_keys=[category_id])
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Transaction(transactionid={self.id}, accountid={self.account_id}, amount={self.amount}, transaction_type='{self.transaction_type}', date='{self.date}', balance_after_transaction='{self.balance_after_transaction}')>"


class SessionPayment(Base):
    __tablename__ = 'session_payments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False, unique=False)
    amount = Column(Float, nullable=False, default=0.0)


class SessionInsight(Base):
    __tablename__ = 'session_insights'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    title = Column(String(200), nullable=False)
    priority = Column(String, nullable=False)
    insight_type = Column(String, nullable=False)
    insight = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_latest = Column(Boolean, nullable=False, default=False)


Session.transaction_insights = relationship("SessionInsight", back_populates="session")
SessionInsight.session = relationship("Session", back_populates="session_insights")

class SessionSwot(Base):
    __tablename__ = 'session_swots'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    analysis = Column(String, nullable=False)
    swot_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

Session.swots = relationship("SessionSwot", back_populates="session")
SessionSwot.session = relationship("Session", back_populates="session_swots")


class SessionSavingsPotential(Base):
    __tablename__ = 'session_savings_potentials'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    amount = Column(Float, nullable=False)
    potential = Column(String, nullable=False)

Session.potentials = relationship("SessionSavingsPotential", back_populates="session")
SessionSavingsPotential.session = relationship("Session", back_populates="session_savings_potentials")

class SessionFinancialData(Base):
    __tablename__ = 'session_financial_data'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    liquidity_risk = Column(Float, nullable=False, default=0.0)
    concentration_risk = Column(Float, nullable=False, default=0.0)
    volatility_risk = Column(Float, nullable=False, default=0.0)
    expense_risk = Column(Float, nullable=False, default=0.0)
    income_flow = Column(Float, nullable=False, default=0.0)

