from django.urls import path
from . import views

urlpatterns = [
    path('',              views.chat_home,    name='chat'),
    path('register/',     views.register_view, name='register'),
    path('login/',        views.login_view,    name='login'),
    path('logout/',       views.logout_view,   name='logout'),
    path('chat/<str:username>/', views.private_chat, name='private_chat'),
    path('profile/update/', views.update_profile,   name='update_profile'),
    path('search-users/', views.search_users),
]