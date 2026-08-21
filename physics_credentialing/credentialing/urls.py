from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('physicists/', views.physicist_list, name='physicist_list'),
    path('physicists/add/', views.add_physicist, name='add_physicist'),
    path('physicists/<int:pk>/', views.physicist_detail, name='physicist_detail'),
    path('physicists/<int:pk>/deactivate/', views.deactivate_physicist, name='deactivate_physicist'),
    path('physicists/<int:physicist_pk>/skills/<int:skill_pk>/update/',
         views.update_credential, name='update_credential'),
    path('matrix/', views.matrix, name='matrix'),
    path('matrix/export/', views.matrix_export, name='matrix_export'),
]
