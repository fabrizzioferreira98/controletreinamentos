"""
Gunicorn configuration for production execution.
Provides graceful shutdown and optimized worker lifecycle settings.
"""

import multiprocessing

# Network Bindings
bind = "0.0.0.0:8000"

# Workers Setup (Dynamic against CPU Cores)
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 4

# Reliability & Graceful Shutdown
timeout = 60
graceful_timeout = 30
keepalive = 5

# Logging & Monitoring
loglevel = "info"
accesslog = "-"  # stdout
errorlog = "-"   # stderr

# Limit payload sizes to prevent DDoS via large body
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

def worker_int(worker):
    """
    Hook to cleanly exit worker on SIGINT or SIGQUIT.
    Log application exit gracefully.
    """
    worker.log.info("Worker gracefully shutting down: %s", worker.pid)

def worker_abort(worker):
    """
    Hook to log when a worker forcefully aborted.
    """
    worker.log.error("Worker forcefully aborted: %s", worker.pid)
