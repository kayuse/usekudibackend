git pull
pip install -r requirements.txt
sh run_migrations.sh
sudo systemctl daemon-reload
sudo systemctl stop fastapi
sudo systemctl start fastapi
sudo systemctl enable fastapi
sudo systemctl status fastapi
