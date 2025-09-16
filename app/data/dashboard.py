from pydantic import BaseModel


class DashboardBalanceOut(BaseModel):
    total_balance: float
    outflow: float

class SpendingInsightOut(BaseModel):
    outflow: float
    outflow_last_month: float
    daily_average_in: float
    daily_average_out: float
    weekly_average_in: float
    weekly_average_out: float