import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 4
threads = 4
timeout = 120
worker_class = 'sync' 