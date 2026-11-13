"""Only unique, local QA copies; never the demo or production database."""
import os
from pathlib import Path
from local_settings import *
qa_path=Path(os.environ['W13_QA_DB']).resolve()
if qa_path.parent != (BASE_DIR/'local_data').resolve() or not qa_path.name.startswith('qa-'):
    raise RuntimeError('QA requires a local_data/qa-* database')
DATABASES={'default': {'ENGINE':'django.db.backends.sqlite3','NAME':qa_path,'OPTIONS':{'timeout':30}}}
SESSION_COOKIE_NAME='w13_qa_session'
