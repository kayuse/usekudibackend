from sqlalchemy import Column, Integer, String, Boolean, Double, func, DateTime, ForeignKey, Text
from enum import IntEnum

from sqlalchemy.orm import relationship

from ..database.index import Base


class FaceRequests(Base):
    __tablename__ = "face_requests"

    id = Column(Integer, primary_key=True)
    blink_image = Column(String)
    smile_image = Column(String)
    base_image = Column(Text)
    blink_score = Column(Double, nullable=True)
    blink_score_cosine = Column(Double, nullable=True)
    smile_score = Column(Double, nullable=True)
    smile_score_cosine = Column(Double, nullable=True)
    smile_spoof_score = Column(Double, nullable=True)
    blink_spoof_score = Column(Double, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    application_id = Column(Integer, ForeignKey("applications.id"))
    # application = relationship("Application", back_populates='face_requests')


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    key = Column(String)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    active = Column(Boolean, default=False)
