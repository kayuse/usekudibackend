git pull
alembic upgrade head
sudo systemctl daemon-reload
sudo systemctl restart fastapi.service
sudo service nginx restart
