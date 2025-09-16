from typing import Optional, List

from pydantic import BaseModel, EmailStr


class AnalysisRequest(BaseModel):
    observatory_id: int
    graph_host: str


class FaceRequest(BaseModel):
    live_image: str
    to_image: str

class StateResponse(BaseModel):
    state: str
    onboarded: bool
    message: str

class AIMessageResponse(BaseModel):
    message : str