from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('physicists/', views.physicist_list, name='physicist_list'),
    path('physicists/add/', views.add_physicist, name='add_physicist'),
    path('physicists/<int:pk>/', views.physicist_detail, name='physicist_detail'),
    path('physicists/<int:pk>/edit/', views.edit_physicist, name='edit_physicist'),
    path('physicists/<int:pk>/deactivate/', views.deactivate_physicist, name='deactivate_physicist'),
    path('physicists/<int:physicist_pk>/skills/<int:skill_pk>/update/',
         views.update_credential, name='update_credential'),
    path('skills/', views.skill_list, name='skill_list'),
    path('skills/add/', views.add_skill, name='add_skill'),
    path('skills/categories/add/', views.add_category, name='add_category'),
    path('skills/categories/<int:pk>/rename/', views.rename_category, name='rename_category'),
    path('skills/categories/<int:pk>/delete/', views.delete_category, name='delete_category'),
    path('skills/<int:pk>/edit/', views.edit_skill, name='edit_skill'),
    path('skills/<int:pk>/delete/', views.delete_skill, name='delete_skill'),
    path('skills/<int:pk>/toggle/', views.toggle_skill, name='toggle_skill'),
    path('skills/<int:pk>/move/<str:direction>/', views.move_skill, name='move_skill'),
    path('skills/categories/<int:pk>/move/<str:direction>/', views.move_category, name='move_category'),
    path('matrix/', views.matrix, name='matrix'),
    path('matrix/export/', views.matrix_export, name='matrix_export'),
]
