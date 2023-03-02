#!/bin/sh
gunicorn --worker-class eventlet -w 1 'apis.api:start_prod()' --timeout 120 --threads 1 -b 0.0.0.0:10009