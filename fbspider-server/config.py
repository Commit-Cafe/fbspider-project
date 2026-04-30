import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://u_7x9k2m:L9%23mP2vQ5z%21@54.179.56.204:27017/plat?authSource=admin')
MONGO_DB = 'plat'
SECRET_KEY = 'fbhelper-local-dev-key'
ACCOUNT_DSL_CALLBACK_URL = os.environ.get('ACCOUNT_DSL_CALLBACK_URL', 'https://adpulse.biz/callback/account/dsl')
ACCOUNT_DSL_CALLBACK_SECRET = os.environ.get('ACCOUNT_DSL_CALLBACK_SECRET', 'acct_dsl_9Kf2mL7xQ1vR8nT4pZ6cH3sW5yB0dJ')
ACCOUNT_DSL_CALLBACK_ENABLED = os.environ.get('ACCOUNT_DSL_CALLBACK_ENABLED', '1')
ACCOUNT_DSL_CALLBACK_BATCH_SIZE = int(os.environ.get('ACCOUNT_DSL_CALLBACK_BATCH_SIZE', '200'))
ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES = int(os.environ.get('ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES', '10'))
ACCOUNT_DSL_STARTUP_REFRESH_WAIT_SECONDS = int(os.environ.get('ACCOUNT_DSL_STARTUP_REFRESH_WAIT_SECONDS', '20'))
ACCOUNT_DSL_CALLBACK_LOG_FULL = os.environ.get('ACCOUNT_DSL_CALLBACK_LOG_FULL', '1')
ACCOUNT_DSL_CALLBACK_LOG_DIR = os.environ.get('ACCOUNT_DSL_CALLBACK_LOG_DIR', os.path.join(BASE_DIR, 'callback_logs'))

# MinIO / S3-compatible object storage for ad creatives
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', '54.179.56.204:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'V9kL2mX5')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'J4hG7fD2sA9qW3eR5tY8uI1o')
MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'ad-creatives')
MINIO_SECURE = os.environ.get('MINIO_SECURE', '0') == '1'
MINIO_PUBLIC_URL = os.environ.get('MINIO_PUBLIC_URL', '')
