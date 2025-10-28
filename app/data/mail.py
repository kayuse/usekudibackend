from pydantic import BaseModel


class EmailTemplateData(BaseModel):
    to_email: str
    subject: str
    context: dict
    template_name: str