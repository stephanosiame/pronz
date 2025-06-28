from django.urls import path
from . import views # For views remaining in views.py
from . import search_views # For search related views
from . import directions_views # For directions related views

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
    path('view-all-campus-paths/', views.view_all_campus_paths, name='view_all_campus_paths'),
    
    # Search related page
    path('search-campus-routes/', search_views.page_search_campus_routes, name='page_search_campus_routes'),

    # Directions related page
    path('get-campus-directions/', directions_views.page_get_campus_directions, name='page_get_campus_directions'),

    # API endpoints
    # Search APIs
    path('api/search/', search_views.search_locations, name='search_locations'), # General location search
    path('api/campus-routes/search/', search_views.search_campus_routes_view, name='search_campus_routes'),
    path('api/locations-in-area/', search_views.get_locations_in_area, name='get_locations_in_area'),
    path('api/admin-routes/', search_views.get_admin_defined_routes, name='get_admin_defined_routes'),

    # Directions APIs
    path('api/campus-directions/', directions_views.get_campus_directions_view, name='get_campus_directions'),
    path('api/directions/', directions_views.get_directions, name='get_directions'), # This is the more general one

    # Other APIs remaining in views.py
    path('api/update-location/', views.update_location, name='update_location'),
    path('api/location-details/<uuid:location_id>/', views.get_location_details_json, name='get_location_details_json'),
    path('api/get-last-user-location/', views.get_last_user_location, name='get_last_user_location'),
    path('api/geofences/', views.api_get_geofences, name='api_get_geofences'),

    # Notification API endpoints (remain in views.py)
    path('api/notifications/unread_count/', views.get_unread_notification_count, name='get_unread_notification_count'),
    path('api/notifications/', views.get_notifications_list, name='get_notifications_list'),
    path('api/notifications/<int:notification_id>/mark_as_read/', views.mark_notification_as_read, name='mark_notification_as_read'),
]