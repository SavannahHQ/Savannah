"""Settings for the automated test suite: PostgreSQL from the environment, no external services."""

import os

from savannah.settings import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver"]
SITE_ROOT = "http://testserver"
SITE_DOMAIN = "testserver"

# The suite runs on PostgreSQL only: migrations behave differently there than on SQLite.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ["DATABASE_HOST"],
        "PORT": os.environ.get("DATABASE_PORT", "5432"),
        "NAME": os.environ["DATABASE_NAME"],
        "USER": os.environ["DATABASE_USER"],
        "PASSWORD": os.environ["DATABASE_PASSWORD"],
        "TEST": {"NAME": os.environ.get("TEST_DATABASE_NAME")},
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# Fast and weak on purpose: the suite creates users in most tests and none of them is real.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # nosec B303

# dj-stripe refuses to start without keys. These are not real and no test reaches Stripe.
STRIPE_LIVE_MODE = False
STRIPE_TEST_SECRET_KEY = "sk_test_fake_key_for_tests_only"  # nosec B105
STRIPE_TEST_PUBLIC_KEY = "pk_test_fake_key_for_tests_only"
DJSTRIPE_WEBHOOK_SECRET = "whsec_fake_secret_for_tests_only"  # nosec B105
