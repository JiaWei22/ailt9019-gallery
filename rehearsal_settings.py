"""Local-only rehearsal with real migrations and W5/W13 integration."""
from qa_settings import *
MIGRATION_MODULES = {}
ROOT_URLCONF = 'integration_urls'
FORCE_SCRIPT_NAME = '/review-system'
