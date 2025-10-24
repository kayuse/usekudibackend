git pull
pip install -r requirements.txt
sh run_migration.sh
sudo systemctl stop fastapi
sudo systemctl start fastapi
sudo systemctl stop celery
sudo systemctl start celery
sudo systemctl stop celery-beat
sudo systemctl start celery-beat
sudo systemctl status fastapi
sudo systemctl status celery
sudo systemctl status celery-beat
sudo systemctl daemon-reload
sudo service nginx restart
