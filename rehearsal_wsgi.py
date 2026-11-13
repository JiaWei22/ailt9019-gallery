"""Loopback-only QA mounting adapter; not a production entry point."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','rehearsal_settings')
from django.core.wsgi import get_wsgi_application
app=get_wsgi_application()

def application(environ,start_response):
    prefix='/review-system'
    path=environ.get('PATH_INFO','')
    if not path.startswith(prefix+'/'):
        start_response('404 Not Found',[('Content-Type','text/plain')]);return [b'Use /review-system/']
    environ['SCRIPT_NAME']=prefix
    environ['PATH_INFO']=path[len(prefix):]
    return app(environ,start_response)
