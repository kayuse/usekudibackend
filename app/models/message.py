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
    user = relationship(User, back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, content='{self.content}')>"