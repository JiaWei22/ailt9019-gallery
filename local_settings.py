from config.settings import *
SECRET_KEY = 'local-fake-data-only-w13'
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
ROOT_URLCONF = 'local_urls'
INSTALLED_APPS += ['showcase']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'local_data' / 'w13.sqlite3', 'OPTIONS': {'timeout': 30}}}
MIGRATION_MODULES = {'reviews': None, 'showcase': None}
SESSION_COOKIE_NAME = 'w13_local_session'
MEDIA_ROOT = BASE_DIR / 'local_data' / 'media'

# Local development never embeds remote media automatically.
W13_EXTERNAL_VIDEO_ENABLED = False
TIME_ZONE = "Asia/Hong_Kong"

# Local demonstrations opt in; production defaults in middleware remain closed.
MIDDLEWARE = [*MIDDLEWARE, "showcase.middleware.AvailabilityMiddleware"]
W13_ENABLED = True
W13_WRITES_ENABLED = True

W13_LOCAL_DEMO = True
