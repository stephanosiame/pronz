import os
from decouple import config
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='your-secret-key-here')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'corsheaders',
    'crispy_forms',
    'crispy_bootstrap5',
    'navigation',
    'leaflet',  # Added django-leaflet
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'collage_nav.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'collage_nav',
        'USER': 'steph',
        'PASSWORD': 'admin2025',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

AUTH_USER_MODEL = 'navigation.CustomUser'

# SMS Configuration
TWILIO_ACCOUNT_SID = config('AC3354d9343c8a851019072e9c6d16be73', default='AC3354d9343c8a851019072e9c6d16be73')
TWILIO_AUTH_TOKEN = config('eaa80f632bcfefb238f456a6776d1cd9', default='eaa80f632bcfefb238f456a6776d1cd9')
TWILIO_PHONE_NUMBER = config('+255740471547', default='+255740471547')

# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Authentication
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Session settings
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# CORS settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8081",
]

# Leaflet Configuration
LEAFLET_CONFIG = {
    'DEFAULT_CENTER': (-6.7712, 39.2400),  # CoICT Campus approximate center
    'DEFAULT_ZOOM': 16,
    'MIN_ZOOM': 3,
    'MAX_ZOOM': 20,
    'TILES': 'OpenStreetMap',  # Default tile layer
    # 'TILES': [('OpenStreetMap', 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {'attribution': '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'})],
    # Add other tile layers if needed, e.g., satellite
    # 'TILES': [
    #     ('OpenStreetMap', '//{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    #      {'attribution': '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'}),
    #     ('Satellite', 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    #      {'attribution': 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA FSA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'})
    # ],
    'SCALE': 'metric', # Options: 'metric', 'imperial', 'both'
    'ATTRIBUTION_PREFIX': 'CoICT Navigation App', # Optional
    # 'SRID': 4326, # Default is 4326, ensure your geometries match
    # 'RESET_VIEW': True, # Show a reset view button on the map
}


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'