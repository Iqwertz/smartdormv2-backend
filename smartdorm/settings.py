import os
from pathlib import Path
import ldap
from django_auth_ldap.config import LDAPSearch, LDAPSearchUnion, GroupOfNamesType

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("SECRET_KEY")
DEBUG = True

ALLOWED_HOSTS = ['django', 'localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'smartdorm',
    'rest_framework',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', 
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'smartdorm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'smartdorm/templates'],
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

WSGI_APPLICATION = 'smartdorm.wsgi.application'

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

# --- Session Configuration ---
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 1209600  # 2 Weeks
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ICS Calendar
NEXTCLOUD_ICS_URL = os.environ.get("NEXTCLOUD_ICS_URL", "https://cloud.schollheim.net/remote.php/dav/public-calendars/8BXCQ5JxXGGQzr2w/?export") #Used to generate a preview to the calendar
NEXTCLOUD_CALENDAR_URL = os.environ.get("NEXTCLOUD_CALENDAR_URL", "https://cloud.schollheim.net/apps/calendar/p/8BXCQ5JxXGGQzr2w/dayGridMonth/now") # Used to redirect users to the full calendar

# --- Cache (for Sessions) Configuration ---
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

# --- CORS Configuration ---
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_CREDENTIALS = True # Important for cookies/sessions

# --- LDAP Configuration ---
AUTH_LDAP_SERVER_URI = "ldap://ldap.schollheim.net:389"
AUTH_LDAP_BIND_DN = "cn=admin,dc=schollheim,dc=net"
AUTH_LDAP_BIND_PASSWORD = os.environ.get("LDAP_ADMIN_PASSWORD")
# User search configuration
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    "dc=schollheim,dc=net",
    ldap.SCOPE_SUBTREE,
    "(cn=%(user)s)"
)

# --- User Attribute Mapping ---
# Map LDAP attributes to Django User model fields
AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "employeeType", #we use the first_name field for employeeType, since the standard Django user model, doesnt have a field for it. I think we can use it for now. 
    "last_name": "sn",
    "email": "mail",
}

# --- Group Search and Handling ---
# Search across multiple OUs for groups the user is a member of. (LDAP setup is a bit clustered due to other services we use, according to sandro)
AUTH_LDAP_GROUP_SEARCH = LDAPSearchUnion(
    LDAPSearch("ou=groups,dc=schollheim,dc=net", ldap.SCOPE_SUBTREE, "(objectClass=groupOfNames)"),
    LDAPSearch("ou=roles,dc=schollheim,dc=net", ldap.SCOPE_SUBTREE, "(objectClass=groupOfNames)"),
    LDAPSearch("ou=groups2,dc=schollheim,dc=net", ldap.SCOPE_SUBTREE, "(objectClass=groupOfNames)"),
)
AUTH_LDAP_GROUP_TYPE = GroupOfNamesType()

AUTH_LDAP_MIRROR_GROUPS = True

AUTH_LDAP_CACHE_TIMEOUT = 3600  # 1 hour

# --- Authentication Backend ---
AUTHENTICATION_BACKENDS = [
    'django_auth_ldap.backend.LDAPBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# --- REST Framework ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated', # login is required for all views (we may have to change this later)
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
     # Ensure CSRF is handled correctly with SessionAuthentication
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

# --- CSRF ---
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]