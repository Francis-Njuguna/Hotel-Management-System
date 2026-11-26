import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR.parent / '.env')


def csv(name, default=''):
    return [s.strip() for s in os.getenv(name, default).split(',') if s.strip()]


SECRET_KEY = os.getenv('HMS_SECRET_KEY', '')
if len(SECRET_KEY) < 32:
    raise ImproperlyConfigured('Set HMS_SECRET_KEY to a unique random secret of at least 32 characters.')
DEBUG = os.getenv('HMS_DEBUG', '0') == '1'
ALLOWED_HOSTS = csv('HMS_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = csv('HMS_CSRF_TRUSTED_ORIGINS')
CSRF_FAILURE_VIEW = 'apps.core.errors.csrf_failure'
PUBLIC_URL = os.getenv('HMS_PUBLIC_URL', 'http://127.0.0.1:5187').rstrip('/')
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
INSTALLED_APPS = ['django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions',
                  'django.contrib.staticfiles','django.contrib.postgres','rest_framework','drf_spectacular',
                  'apps.core.apps.CoreConfig','apps.lodging','apps.housekeeping','apps.restaurant','apps.billing','apps.parking']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware',
              'django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware',
              'django.contrib.auth.middleware.AuthenticationMiddleware','apps.core.middleware.SessionLifetimeMiddleware',
              'django.middleware.clickjacking.XFrameOptionsMiddleware']
DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('POSTGRES_DB','hotel_a'),
    'USER':os.getenv('POSTGRES_USER','hotel_a'),'PASSWORD':os.environ['POSTGRES_PASSWORD'],
    'HOST':os.getenv('POSTGRES_HOST','127.0.0.1'),'PORT':os.getenv('POSTGRES_PORT','5432'),
    'CONN_MAX_AGE':60,'CONN_HEALTH_CHECKS':True}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_TZ = True
USE_I18N = True
MEDIA_ROOT = Path(os.getenv('HMS_MEDIA_ROOT', BASE_DIR / 'media'))
MEDIA_URL = '/api/v1/media/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 1
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = os.getenv('HMS_SECURE_COOKIES', '0' if DEBUG else '1') == '1'
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 3600
SESSION_IDLE_SECONDS = 30 * 60
PASSWORD_RESET_TIMEOUT = 1800
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
if os.getenv('HMS_TRUST_PROXY') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if os.getenv('HMS_HTTPS') == '1':
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','APP_DIRS':True,'OPTIONS':{}}]
AUTH_PASSWORD_VALIDATORS = [{'NAME':f'django.contrib.auth.password_validation.{n}'} for n in
    ('UserAttributeSimilarityValidator','MinimumLengthValidator','CommonPasswordValidator','NumericPasswordValidator')]
EMAIL_HOST = os.getenv('HMS_EMAIL_HOST','')
EMAIL_PORT = int(os.getenv('HMS_EMAIL_PORT','587'))
EMAIL_HOST_USER = os.getenv('HMS_EMAIL_USER','')
EMAIL_HOST_PASSWORD = os.getenv('HMS_EMAIL_PASSWORD','')
EMAIL_USE_TLS = os.getenv('HMS_EMAIL_TLS','1') == '1'
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv('HMS_EMAIL_FROM') or 'hotel-a@localhost'
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
if DEBUG and not EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = BASE_DIR.parent / '.local' / 'outbox'
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES':['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_SCHEMA_CLASS':'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES':['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PAGINATION_CLASS':'apps.core.pagination.StaffPagination',
    'DEFAULT_FILTER_BACKENDS':['rest_framework.filters.SearchFilter'],
    'DEFAULT_THROTTLE_RATES':{'login':'10/min','reset':'10/min','verify_email':'10/min'},
    'NUM_PROXIES':int(os.getenv('HMS_NUM_PROXIES','0')),
    'EXCEPTION_HANDLER':'apps.core.api.error_response',
    'TEST_REQUEST_DEFAULT_FORMAT':'json',
}
SPECTACULAR_SETTINGS = {'TITLE':'Hotel A staff API','DESCRIPTION':'Versioned, permission-scoped hotel operations. Amounts are fixed-precision KES.',
                        'VERSION':'1.0','SERVE_INCLUDE_SCHEMA':False,'SERVE_PERMISSIONS':['rest_framework.permissions.IsAdminUser'],
                        'ENUM_NAME_OVERRIDES':{'ReservationStatus':'apps.lodging.models.ReservationStatus',
                            'CleaningStatus':'apps.housekeeping.models.CleaningStatus','RepairStatus':'apps.housekeeping.models.MaintenanceStatus',
                            'OrderStatus':'apps.restaurant.models.OrderStatus'}}

if os.getenv('HMS_ENV','local') == 'production':
    from urllib.parse import urlsplit
    origin=urlsplit(PUBLIC_URL)
    if (DEBUG or not SESSION_COOKIE_SECURE or os.getenv('HMS_HTTPS') != '1' or not EMAIL_HOST or not EMAIL_USE_TLS or not os.getenv('HMS_EMAIL_FROM')
            or origin.scheme!='https' or origin.hostname not in ALLOWED_HOSTS or '*' in ALLOWED_HOSTS
            or any(not item.startswith('https://') for item in CSRF_TRUSTED_ORIGINS)):
        raise ImproperlyConfigured('Production requires a matching HTTPS public URL and allowed hosts, secure cookies, TLS redirects, debug off and recovery mail with STARTTLS.')
