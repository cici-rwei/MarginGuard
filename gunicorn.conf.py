"""Single-instance bounded WSGI service; access logs omit URLs and user data."""
import os

bind = '0.0.0.0:' + os.environ.get('PORT', '8000')
workers = 2
worker_class = 'sync'
timeout = 20
graceful_timeout = 10
keepalive = 2
limit_request_line = 2048
limit_request_fields = 40
limit_request_field_size = 4096
max_requests = 500
max_requests_jitter = 50
accesslog = '-'
# No URL/query, IP, user-agent, request headers, cookie or body.
access_log_format = '%(s)s %(M)sms'
errorlog = '-'
loglevel = 'warning'
capture_output = False
preload_app = False
