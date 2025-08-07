from enum import Enum
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, Integer, Boolean, Float,DateTime, func,Enum as SqlEnum, ForeignKey
from app.database.index import Base
from app.models.user import User

from sqlalchemy.orm import relationship

class FetchMethod(Enum):
    SMS = "sms"
    EMAIL = "email"
    MONOAPI = "monoapi"

#crate a Bank model to represent the bank entity

class Bank(Base):
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_name = Column(String(100), nullable=False, unique=False)
    institution_id = Column(String(100), nullable=True, unique=True)  # Unique identifier for the bank
    bank_code = Column(String(10), nullable=True, unique=False)  # Unique code for the bank
    bank_account_type = Column(String(50), nullable=True)  # Type of bank account
    image_url = Column(String(1255), nullable=True)  # URL to the bank's logo or image
    active = Column(Boolean, nullable=True, default=False)  # 1 for active, 0 for inactive
    auth_method = Column(String(50), nullable=True, default="internet_banking")  # Authentication method used by the bank
    accounts = relationship("Account", back_populates="bank")

    def __repr__(self):
        return f"<Bank(bank_id={self.bank_id}, bank_name='{self.bank_name}')>"

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String(100), nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    account_number = Column(String(50), nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=False)  # 1 for active, 0 for inactive
    account_type = Column(String, nullable=True, default=0.0)
    account_id = Column(String, nullable=True, default = '', unique=False)  # Mono account ID, can be null if not applicable
    current_balance = Column(Float, nullable=False, default=0.0)
    indexed = Column(Boolean, nullable=True, default=False)  # Indicates if the account has been indexed
    currency = Column(String(10), nullable=False, default="NGN")
    fetch_method = Column(SqlEnum(FetchMethod), nullable=False)
    bank = relationship("Bank", back_populates="accounts", foreign_keys=[bank_id])
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Assuming a User model exists
    user = relationship(User, back_populates="accounts")  # Assuming a User model exists
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")
    last_synced = Column(DateTime, nullable=True)  # Last time the account was synced
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Account(accountid={self.account_id}, account_name='{self.account_name}', account_number='{self.account_number}',bank='{self.bank_id}', active={self.active}, account_type='{self.account_type}', current_balance={self.current_balance}, currency='{self.currency}', fetch_method='{self.fetch_method}')>"


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"  

#help me with a transaction model with a relationship to the account model
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer,  ForeignKey("accounts.id"),nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)  # Optional category for the transaction
    transaction_id = Column(String(200), nullable=False, unique=True, default='')  # Mono transaction ID
    currency = Column(String(10), nullable=False, default="NGN")
    date = Column(DateTime, nullable=False, default=func.now())  # Transaction date
    balance_after_transaction = Column(Float, nullable=False, default=0.0)  # Balance after the transaction
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(50), nullable=False)  # e.g., 'credit', 'debit'
    description = Column(String(255), nullable=True)
    account = relationship(Account, back_populates="transactions")
    category = relationship("Category", backref="transactions", foreign_keys=[category_id])
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    embedding = Column(Vector(1536))

    def __repr__(self):
        return f"<Transaction(transactionid={self.id}, accountid={self.account_id}, amount={self.amount}, transaction_type='{self.transaction_type}', date='{self.date}', balance_after_transaction='{self.balance_after_transaction}')>"

# Account.transactions = relationship("Transaction", order_by=Transaction.transactionid, back_populates="account")
# This code defines a Transaction model that has a many-to-one relationship with the Account model.