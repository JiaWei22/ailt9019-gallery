from django.urls import include, path
# Isolated rehearsal only; preserve original W5 URLConf unchanged.
urlpatterns = [path('w13/', include('showcase.urls')), path('', include('config.urls'))]
