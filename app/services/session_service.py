from sqlalchemy.orm import Session


class SessionService:

    def __init__(self, db_session=Session):
        self.session = db_session

    def start(self, ):