#!/bin/sh
set -e
cd $SNAP
exec $SNAP/bin/gunicorn --log-level debug --workers 3 --bind 0.0.0.0:5000 app:app
