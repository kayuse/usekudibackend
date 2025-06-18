from pydantic import BaseModel, EmailStr


class AnalysisRequest(BaseModel):
    observatory_id: int
    graph_host: str


class FaceRequest(BaseModel):
    live_image: str
    to_image: str
