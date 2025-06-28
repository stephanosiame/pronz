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
    path('view-all-campus-paths/', views.view_all_campus_paths, name='view_all_campus_paths'), # New page for viewing all paths
    
    # API endpoints
    path('api/search/', views.search_locations, name='search_locations'), # General location search
    path('search-campus-routes/', views.page_search_campus_routes, name='page_search_campus_routes'),
    path('get-campus-directions/', views.page_get_campus_directions, name='page_get_campus_directions'),
    path('api/campus-routes/search/', views.search_campus_routes_view, name='search_campus_routes'), # New route search
    path('api/campus-directions/', views.get_campus_directions_view, name='get_campus_directions'), # New campus directions
    path('api/directions/', views.get_directions, name='get_directions'), # This is the more general one
    path('api/update-location/', views.update_location, name='update_location'),
    path('api/location-details/<uuid:location_id>/', views.get_location_details_json, name='get_location_details_json'),
    path('api/get-last-user-location/', views.get_last_user_location, name='get_last_user_location'),
    path('api/geofences/', views.api_get_geofences, name='api_get_geofences'),
    path('api/locations-in-area/', views.get_locations_in_area, name='get_locations_in_area'), # New API for area search
    path('api/admin-routes/', views.get_admin_defined_routes, name='get_admin_defined_routes'), # API for admin-defined routes

    # Notification API endpoints
    path('api/notifications/unread_count/', views.get_unread_notification_count, name='get_unread_notification_count'),
    path('api/notifications/', views.get_notifications_list, name='get_notifications_list'),
    path('api/notifications/<int:notification_id>/mark_as_read/', views.mark_notification_as_read, name='mark_notification_as_read'),
]