from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('verify/<int:user_id>/', views.verify_token_view, name='verify_token'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/verify/<int:user_id>/', views.password_reset_verify, name='password_reset_verify'),
    
    # API endpoints
    path('api/search/', views.search_locations, name='search_locations'),
    path('api/directions/', views.get_directions, name='get_directions'),
    path('api/update-location/', views.update_location, name='update_location'),
    path('api/location-details/<uuid:location_id>/', views.get_location_details_json, name='get_location_details_json'),
]