git pull
pip install -r requirements.txt
sh /home/ilanaa_soft/usekudibackend/run_migration.sh
sudo systemctl daemon-reload
sudo systemctl restart fastapi.service
sudo service nginx restart
