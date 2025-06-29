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
    UserLocation,  # This was missing
    AdminNotification,
    UserNotificationStatus
)
from django.utils import timezone # Needed for admin actions

# Basic registration - We will use @admin.register for new models and can update others gradually
# admin.site.register(CustomUser) # Example: Keep some basic, or convert all to @admin.register
# admin.site.register(Location) # Handled by LocationAdmin below
# admin.site.register(NavigationRoute)
# admin.site.register(UserSearch)
# admin.site.register(Geofence)
# admin.site.register(SMSAlert)
# admin.site.register(Recommendation)
# admin.site.register(RouteRequest)
# admin.site.register(GeofenceEntry)
# admin.site.register(UserLocation)

# Only models not registered with @admin.register decorator below should be listed here for basic registration.
# For this task, we are focusing on adding AdminNotification and UserNotificationStatus.
# Existing basic registrations will be left as is unless they conflict with a new @admin.register.
# Location is already handled by @gis_admin.register(Location).
# We will remove basic registrations if we provide a custom admin class for them.

admin.site.register(CustomUser) # Kept for now
# Location is handled by LocationAdmin
# admin.site.register(NavigationRoute) # Will be handled by NavigationRouteAdmin
admin.site.register(UserSearch) # Kept for now
admin.site.register(Geofence) # Kept for now
admin.site.register(SMSAlert) # Kept for now
admin.site.register(Recommendation) # Kept for now
admin.site.register(RouteRequest) # Kept for now
admin.site.register(GeofenceEntry) # Kept for now
admin.site.register(UserLocation) # Kept for now



# # Basic registration
# admin.site.register(CustomUser)
# # admin.site.register(Location)
# admin.site.register(NavigationRoute)
# admin.site.register(UserSearch)
# admin.site.register(Geofence)
# admin.site.register(SMSAlert)
# admin.site.register(Recommendation)
# admin.site.register(RouteRequest)
# admin.site.register(GeofenceEntry)
# admin.site.register(UserLocation)  # Added missing model



from django.contrib.gis import admin as gis_admin # Use alias to avoid conflict if regular 'admin' is used a lot
from leaflet.admin import LeafletGeoAdmin # Import LeafletGeoAdmin

# --- Constants for CoICT Campus Map Default View in Admin ---
# Ideally, these would be imported from a central settings/constants file
COICT_CENTER_LAT_ADMIN = -6.771204359255421
COICT_CENTER_LON_ADMIN = 39.24001333969674
# --- End Constants ---

# Optional: Enhanced admin classes for better management
# Uncomment these if you want more detailed admin interfaces

# @admin.register(CustomUser) # Keep using admin.register for non-GIS models
# class CustomUserAdmin(admin.ModelAdmin):
#     list_display = ('username', 'email', 'phone_number', 'role', 'is_verified', 'date_joined')
#     list_filter = ('role', 'is_verified', 'date_joined')
#     search_fields = ('username', 'email', 'phone_number', 'first_name', 'last_name')
#     readonly_fields = ('date_joined', 'last_login')

# The @gis_admin.register(Location) decorator handles unregistering if Location was previously registered.
@gis_admin.register(Location) # Or @admin.register(Location) if using LeafletGeoAdmin for a non-GIS specific model admin
class LocationAdmin(LeafletGeoAdmin): # Inherit from LeafletGeoAdmin
    list_display = ('name', 'location_type', 'address', 'floor_level', 'is_accessible', 'updated_at')
    search_fields = ('name', 'address', 'description', 'location_type')
    list_filter = ('location_type', 'is_accessible', 'floor_level')

    # Define fields to ensure all are editable and in desired order
    # OSMGeoAdmin handles 'coordinates' with a map widget.
    # 'location_id', 'created_at', 'updated_at' are often read-only or auto-managed.
    fields = (
        'name', 'description', 'address', 'location_type',
        'coordinates', # This will use the OSMGeoAdmin map widget
        'floor_level', 'is_accessible', 'capacity',
        'operating_hours', 'contact_info', 'image',
        'location_id', 'created_at', 'updated_at' # Display as read-only
    )
    readonly_fields = ('location_id', 'created_at', 'updated_at') # Make these read-only in the form

    # Default map settings for OSMGeoAdmin
    default_lat = COICT_CENTER_LAT_ADMIN
    default_lon = COICT_CENTER_LON_ADMIN
    default_zoom = 16 # A bit more zoomed in for better detail initially

@admin.register(NavigationRoute) # Use standard admin.register
class NavigationRouteAdmin(LeafletGeoAdmin): # Inherit from LeafletGeoAdmin to use map widget for route_path
    list_display = ('name', 'route_id', 'source_location', 'destination_location', 'distance', 'estimated_time', 'is_active', 'is_accessible', 'difficulty_level')
    search_fields = ('name', 'description', 'source_location__name', 'destination_location__name')
    list_filter = ('is_active', 'is_accessible', 'difficulty_level')
    # The 'route_path' field (LineStringField) will automatically use the Leaflet map widget for drawing,
    # thanks to inheriting from LeafletGeoAdmin.

    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'is_active', 'is_accessible', 'difficulty_level')
        }),
        ('Route Details', {
            'fields': ('source_location', 'destination_location', 'route_path', 'distance', 'estimated_time')
        }),
        ('Metadata', {
            'fields': ('route_id', 'created_at',),
            'classes': ('collapse',) # Keep metadata collapsed by default
        }),
    )
    readonly_fields = ('route_id', 'created_at')


    # Optional: Customize Leaflet settings specifically for this admin page if needed
    # settings_overrides = {
    #     'DEFAULT_CENTER': (COICT_CENTER_LAT_ADMIN, COICT_CENTER_LON_ADMIN),
    #     'DEFAULT_ZOOM': 17,
    # }

# @gis_admin.register(SMSAlert) # Use gis_admin if SMSAlert had GeoDjango fields, otherwise admin.register
# class SMSAlertAdmin(admin.ModelAdmin): # If not a GeoDjango model, use admin.ModelAdmin
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

@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_published', 'published_at', 'created_at')
    list_filter = ('is_published', 'created_at', 'published_at')
    search_fields = ('title', 'message')
    readonly_fields = ('created_at', 'published_at')
    actions = ['publish_notifications', 'unpublish_notifications']

    def publish_notifications(self, request, queryset):
        queryset.update(is_published=True, published_at=timezone.now())
    publish_notifications.short_description = "Publish selected notifications"

    def unpublish_notifications(self, request, queryset):
        queryset.update(is_published=False, published_at=None) # Also clear published_at
    unpublish_notifications.short_description = "Unpublish selected notifications"

@admin.register(UserNotificationStatus)
class UserNotificationStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_title', 'is_read', 'read_at')
    list_filter = ('is_read', 'notification__is_published', 'notification__title') # Filter by notification title
    search_fields = ('user__username', 'notification__title')
    readonly_fields = ('read_at',)
    list_select_related = ('user', 'notification') # Optimize queries

    def notification_title(self, obj):
        return obj.notification.title
    notification_title.short_description = 'Notification Title'
    notification_title.admin_order_field = 'notification__title' # Allow sorting by title
