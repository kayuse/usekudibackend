from mailtrap import MailtrapClient, Mail
from jinja2 import Environment, FileSystemLoader
import mailtrap as mt

import os
from dotenv import load_dotenv

from app.data.mail import EmailTemplateData

load_dotenv(override=True)


class EmailService:
    def __init__(self):
        self.templates = Environment(loader=FileSystemLoader("app/templates"))
        self.mailtrap = MailtrapClient(token=os.getenv("MAILTRAP_API_TOKEN"))
        self.sender = os.getenv("MAILTRAP_SENDER")

    def render_template(self, template_name, **kwargs):
        template = self.templates.get_template(template_name)
        return template.render(**kwargs)

    def send_templated_email(self, data: EmailTemplateData):
        html = self.render_template(data.template_name, **data.context)
        to_addresses = mt.Address(email=data.to_email)
        sender = mt.Address(email=self.sender, name='UseKudi Analysis Team')
        mail = Mail(
            to=[to_addresses],
            sender=sender,
            subject=data.subject,
            html=html,
            category="Welcome"
        )
        self.mailtrap.send(mail)
