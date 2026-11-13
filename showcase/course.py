from django.shortcuts import render
from django.views.decorators.http import require_GET
@require_GET
def home(request):
    return render(request, 'showcase/course_home.html')

from pathlib import Path
from django.http import FileResponse, Http404

@require_GET
def asset(request, name):
    types = {'home.css': 'text/css', 'home.js': 'application/javascript',
             'cds-logo.png': 'image/png', 'campus.jpg': 'image/jpeg', 'lecture.webp': 'image/webp',
             'studio.jpg': 'image/jpeg', 'exhibition.webp': 'image/webp',
             'montserrat-800.woff2': 'font/woff2', 'montserrat-400.woff2': 'font/woff2'}
    if name not in types:
        raise Http404
    return FileResponse(open(Path(__file__).parent / 'static/showcase/course' / name, 'rb'), content_type=types[name])
