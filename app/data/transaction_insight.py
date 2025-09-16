from pydantic import BaseModel, RootModel
from typing import Optional, List


class Insight(BaseModel):
    title: str
    description: str
    priority: str
    type: str
    action: Optional[str] = None


class Insights(RootModel[List[Insight]]):
    pass


class ChatCreate(BaseModel):
    text: str
