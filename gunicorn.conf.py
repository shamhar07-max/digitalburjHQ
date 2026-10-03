import os
bind='0.0.0.0:'+os.environ.get('PORT','8080')
workers=int(os.environ.get('HQ_WORKERS','2'))
worker_class='gthread'
threads=4
timeout=60
graceful_timeout=30
keepalive=5
max_requests=1000
max_requests_jitter=100
preload_app=False
# No request paths/query strings in access logs (OAuth callback carries a code).
accesslog=None
errorlog='-'
capture_output=True
