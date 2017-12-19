#!/bin/sh

chown -R coffee:coffee db
chmod o-w db

export PYTHONUNBUFFERED=1

exec gunicorn -w 8 coffeebot:application -b 0.0.0.0:10000 -u coffee -g coffee --capture-output --timeout=45
