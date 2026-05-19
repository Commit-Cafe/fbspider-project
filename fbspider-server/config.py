import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

MONGO_URI = os.environ.get('MONGO_URI', '')
MONGO_DB = os.environ.get('MONGO_DB', 'plat')
SECRET_KEY = os.environ.get('SECRET_KEY', '')

if not MONGO_URI:
    raise RuntimeError("MONGO_URI must be set in environment or .env file")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in environment or .env file")

ACCOUNT_DSL_CALLBACK_URL = os.environ.get('ACCOUNT_DSL_CALLBACK_URL', '')
ACCOUNT_DSL_CALLBACK_SECRET = os.environ.get('ACCOUNT_DSL_CALLBACK_SECRET', '')
ACCOUNT_DSL_CALLBACK_ENABLED = os.environ.get('ACCOUNT_DSL_CALLBACK_ENABLED', '1')
ACCOUNT_DSL_CALLBACK_BATCH_SIZE = int(os.environ.get('ACCOUNT_DSL_CALLBACK_BATCH_SIZE', '200'))
ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES = int(os.environ.get('ACCOUNT_DSL_CALLBACK_INTERVAL_MINUTES', '10'))
ACCOUNT_DSL_STARTUP_REFRESH_WAIT_SECONDS = int(os.environ.get('ACCOUNT_DSL_STARTUP_REFRESH_WAIT_SECONDS', '20'))
ACCOUNT_DSL_CALLBACK_LOG_FULL = os.environ.get('ACCOUNT_DSL_CALLBACK_LOG_FULL', '1')
ACCOUNT_DSL_CALLBACK_LOG_DIR = os.environ.get('ACCOUNT_DSL_CALLBACK_LOG_DIR', os.path.join(BASE_DIR, 'callback_logs'))

MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', '')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', '')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', '')
MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'ad-creatives')
MINIO_SECURE = os.environ.get('MINIO_SECURE', '0') == '1'
MINIO_PUBLIC_URL = os.environ.get('MINIO_PUBLIC_URL', '')

CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:5173,http://localhost:7151,http://47.131.62.227:7151')

CURRENCY_OFFSETS = {
    'BIF': 1, 'CLP': 1, 'COP': 1, 'CRC': 1, 'CVE': 1, 'DJF': 1,
    'GNF': 1, 'HUF': 1, 'IDR': 1, 'ISK': 1, 'JPY': 1, 'KMF': 1,
    'KRW': 1, 'PYG': 1, 'RWF': 1, 'TWD': 1, 'UGX': 1, 'VND': 1,
    'VUV': 1, 'XAF': 1, 'XOF': 1, 'XPF': 1,
    'MGA': 5, 'MRO': 5,
}
