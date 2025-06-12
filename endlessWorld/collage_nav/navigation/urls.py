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
    path('api/get-last-user-location/', views.get_last_user_location, name='get_last_user_location'),
    path('api/geofences/', views.api_get_geofences, name='api_get_geofences'),

    # Notification API endpoints
    path('api/notifications/unread_count/', views.get_unread_notification_count, name='get_unread_notification_count'),
    path('api/notifications/', views.get_notifications_list, name='get_notifications_list'),
    path('api/notifications/<int:notification_id>/mark_as_read/', views.mark_notification_as_read, name='mark_notification_as_read'),
]