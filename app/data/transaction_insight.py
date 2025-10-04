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


class TransactionSWOTInsight(BaseModel):
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]


class SavingsPotential(BaseModel):
    potential: str
    amount: float


class SavingsPotentials(RootModel[List[SavingsPotential]]):
    pass


class ChatCreate(BaseModel):
    text: str

class OverallAssessment(BaseModel):
    title: str
    assessment: str

class ClusteredTransactionNames(BaseModel):
    name: str
    description: str

class TransactionBeneficiary(BaseModel):
    name : str
    is_self : bool

class TransactionBeneficial(BaseModel):
    name: str
    amount: float