git pull
source /home/ilanaa_soft/usekudibackend/venv/bin/activate
pip install -r requirements.txt
sh run_migrations.sh
sudo systemctl daemon-reload
sudo systemctl restart fastapi.service
sudo service nginx restart
