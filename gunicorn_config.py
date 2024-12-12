import os

# Get port from environment variable or default to 10000
port = os.environ.get('PORT', '10000')

# Bind to the port
bind = f"0.0.0.0:{port}"

# Worker configuration
workers = 4
threads = 2
worker_class = 'sync'
worker_connections = 1000
timeout = 120

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info' 