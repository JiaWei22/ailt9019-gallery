from django.urls import path
from . import views as v
app_name = 'showcase'
urlpatterns=[path('',v.gallery,name='gallery'),path('login/',v.login,name='login'),path('logout/',v.logout,name='logout'),path('projects/<int:pk>/',v.project,name='project'),path('reviews/',v.tasks,name='tasks'),path('reviews/<int:pk>/',v.review,name='review'),path('vote/',v.vote,name='vote'),path('manage/',v.manage,name='manage'),path('manage/export/',v.export,name='export')]

from . import admin_views
urlpatterns += [path("manage/<str:kind>/<int:pk>/edit/",admin_views.edit,name="edit"),path("manage/audit/",admin_views.audit,name="audit")]

urlpatterns += [path('manage/logout/',v.staff_logout,name='staff_logout')]
urlpatterns += [path('vote/preview/',v.vote_preview,name='vote_preview')]

from .student_submission import my_project
urlpatterns += [path('my-project/', my_project, name='my_project')]

from . import information
urlpatterns += [path('activity/',information.activity,name='activity'),path('guide/',information.student_guide,name='student_guide'),path('manage/guide/',information.staff_guide,name='staff_guide')]

from .course import home
urlpatterns += [path('course/', home, name='course_home')]
from .exhibition import exhibition
urlpatterns += [path('exhibition/', exhibition, name='exhibition')]
from .exhibition import exhibit_detail
urlpatterns += [path('exhibition/project/<int:pk>/', exhibit_detail, name='exhibit_detail')]
urlpatterns += [path('exhibition/assets/phaser.js', __import__('showcase.exhibition',fromlist=['phaser_asset']).phaser_asset, name='phaser_asset')]

from .exhibition import openvgal, openvgal_asset
urlpatterns += [path('exhibition/openvgal/',openvgal,name='openvgal'),path('exhibition/openvgal/assets/<str:name>',openvgal_asset,name='openvgal_asset')]

from .exhibition import exhibition_asset
urlpatterns += [path('exhibition/style/<str:name>',exhibition_asset,name='exhibition_asset')]

from .course import asset as course_asset
urlpatterns += [path('course/assets/<str:name>', course_asset, name='course_asset')]

urlpatterns += [path('session-state/',v.session_state,name='session_state')]
