# import json
# import time
#
# from confluent_kafka import Producer
#
# from ..data.ai_models import AnalysisRequest
# from ..models.analysis import ProcessRequest, AnalysisStatusCode
# from sqlalchemy.orm import Session
# from dotenv import load_dotenv
# import os
#
#
# class CommunityService:
#     conf: dict
#     producer: Producer
#     KAFKA_COMMUNITY_TOPIC = ''
#
#     def __init__(self, db_session: Session = None):
#         self.db_session = db_session
#         load_dotenv()
#         self.KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
#         self.KAFKA_CLIENT_ID = os.getenv("KAFKA_CLIENT_ID")
#         self.KAFKA_COMMUNITY_TOPIC = os.getenv("KAFKA_COMMUNITY_TOPIC")
#         self.KAFKA_ETL = os.getenv('KAFKA_ETL')
#
#         self.conf = {
#             'bootstrap.servers': self.KAFKA_BOOTSTRAP_SERVERS,
#             'client.id': self.KAFKA_CLIENT_ID
#         }
#
#     def run_analysis(self, request: AnalysisRequest):
#         process = ProcessRequest(host=request.graph_host,
#                                  status=AnalysisStatusCode.PENDING,
#                                  observatory_id=request.observatory_id)
#         self.db_session.add(process)
#         self.db_session.commit()
#         self.db_session.refresh(process)
#         self.produce_to_kafka(process)
#         return process
#
#     def delivery_report(self, err, msg):
#         if err:
#             print(f"Message delivery failed: {err}")
#         else:
#             print(f"Message delivered to {msg.topic()} [{msg.partition()}]")
#
#     def produce_to_kafka(self, process: ProcessRequest):
#         self.producer = Producer(self.conf)
#
#         data = {
#             "id": process.id,
#             "host": process.host,
#             "observatory_id": process.observatory_id
#         }
#         self.producer.produce(topic=self.KAFKA_COMMUNITY_TOPIC, key="key" + str(time.time()), value=json.dumps(data),
#                               callback=self.delivery_report)
#         self.producer.flush()
#         return True
