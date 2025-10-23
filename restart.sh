git pull
pip install -r requirements.txt
sh run_migrations.sh
sudo systemctl daemon-reload
sudo systemctl stop fastapi
sudo systemctl start fastapi
sudo systemctl enable fastapi
sudo systemctl status fastapi
sudo systemctl daemon-reload
sudo systemctl enable celery
sudo systemctl enable celery-beat
sudo systemctl start celery
sudo systemctl start celery-beat
