git pull
pip install -r requirements.txt
sh run_migration.sh
sudo systemctl restart fastapi
sudo systemctl restart celery
sudo systemctl restart celery-beat
sudo systemctl daemon-reload
sudo service nginx restart
