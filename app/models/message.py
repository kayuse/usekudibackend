from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database.index import Base
from app.models.user import User


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(String, nullable=False, unique=False)
    response = Column(String, nullable=True, unique=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
User.messages = relationship("Message", back_populates="user")
Message.user = relationship("User", back_populates="messages")