# Django Settings

import os
from pathlib import Path

import ldap
from django_auth_ldap.config import LDAPSearch, GroupOfNamesType

BASE_DIR = Path(__file__).resolve().parent.parent
# You must set the SECRET_KEY environment variable before running this project
SECRET_KEY = os.environ.get("SECRET_KEY")
DEBUG = True

ALLOWED_HOSTS = ['django', 'localhost']
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'smartdorm',
    'rest_framework',
]

ROOT_URLCONF = 'smartdorm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
            ],
        },
    },
]

WSGI_APPLICATION = 'smartdorm.wsgi.application'

# PostgreSQL database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'testing'),
        'USER': os.environ.get('POSTGRES_USER', 'pg'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]

# LDAP server configuration
AUTH_LDAP_SERVER_URI = "ldap://ldap.schollheim.net:389"
AUTH_LDAP_BIND_DN = "cn=admin,dc=schollheim,dc=net"
AUTH_LDAP_BIND_PASSWORD = os.environ.get("LDAP_ADMIN_PASSWORD")

# User search configuration
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    "dc=schollheim,dc=net",
    ldap.SCOPE_SUBTREE,
    "(cn=%(user)s)"
)

# Group search configuration
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    "ou=groups2,dc=schollheim,dc=net",
    ldap.SCOPE_SUBTREE,
    "(objectClass=groupOfNames)"
)
AUTH_LDAP_GROUP_TYPE = GroupOfNamesType(name_attr="cn")

# User attributes mapping
AUTH_LDAP_USER_ATTR_MAP = {
    "username": "cn",
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
}

# Authentication backend configuration
AUTHENTICATION_BACKENDS = [
    'django_auth_ldap.backend.LDAPBackend',
    'django.contrib.auth.backends.ModelBackend',
]