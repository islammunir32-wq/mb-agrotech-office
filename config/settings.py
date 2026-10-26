import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
DATA = BASE_DIR / 'data'
DATA.mkdir(exist_ok=True)
keyfile = DATA / 'session-key'
if not keyfile.exists():
    import secrets
    keyfile.write_text(secrets.token_urlsafe(64))
    keyfile.chmod(0o600)
SECRET_KEY = os.environ.get('APP_SECRET_KEY') or keyfile.read_text()
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'office']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME': DATA / 'office.sqlite3','OPTIONS':{'timeout':30,'transaction_mode':'IMMEDIATE'}}}
TIME_ZONE = 'Asia/Dhaka'
USE_TZ = True
LANGUAGE_CODE = 'bn'
STATIC_URL = '/static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
