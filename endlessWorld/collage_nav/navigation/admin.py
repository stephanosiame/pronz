from django.contrib import admin
from .models import (
    CustomUser, 
    Location, 
    NavigationRoute, 
    UserSearch, 
    Geofence, 
    SMSAlert, 
    Recommendation, 
    RouteRequest, 
    GeofenceEntry,
    UserLocation  # This was missing
)

# Basic registration
admin.site.register(CustomUser)
admin.site.register(Location)
admin.site.register(NavigationRoute)
admin.site.register(UserSearch)
admin.site.register(Geofence)
admin.site.register(SMSAlert)
admin.site.register(Recommendation)
admin.site.register(RouteRequest)
admin.site.register(GeofenceEntry)
admin.site.register(UserLocation)  # Added missing model

# Optional: Enhanced admin classes for better management
# Uncomment these if you want more detailed admin interfaces

# @admin.register(CustomUser)
# class CustomUserAdmin(admin.ModelAdmin):
#     list_display = ('username', 'email', 'phone_number', 'role', 'is_verified', 'date_joined')
#     list_filter = ('role', 'is_verified', 'date_joined')
#     search_fields = ('username', 'email', 'phone_number', 'first_name', 'last_name')
#     readonly_fields = ('date_joined', 'last_login')

# @admin.register(Location)
# class LocationAdmin(admin.ModelAdmin):
#     list_display = ('name', 'location_type', 'floor_level', 'is_accessible', 'created_at')
#     list_filter = ('location_type', 'is_accessible', 'floor_level')
#     search_fields = ('name', 'description')
#     readonly_fields = ('location_id', 'created_at', 'updated_at')

# @admin.register(SMSAlert)
# class SMSAlertAdmin(admin.ModelAdmin):
#     list_display = ('user', 'alert_type', 'is_sent', 'sent_at', 'created_at')
#     list_filter = ('alert_type', 'is_sent', 'created_at')
#     search_fields = ('user__username', 'user__phone_number', 'message')
#     readonly_fields = ('alert_id', 'created_at')

# @admin.register(UserSearch)
# class UserSearchAdmin(admin.ModelAdmin):
#     list_display = ('user', 'search_query', 'search_location', 'timestamp')
#     list_filter = ('timestamp',)
#     search_fields = ('user__username', 'search_query')
#     readonly_fields = ('timestamp',)