#!/bin/sh
set -e
mkdir -p $SNAP_COMMON/var/lib/nginx
exec $SNAP/usr/sbin/nginx -c $SNAP/etc/nginx/nginx.conf -g "daemon off;"
