from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.core.validators import RegexValidator
import uuid
from datetime import datetime, timedelta

class CustomUser(AbstractUser):
    USER_ROLES = (
        ('student', 'Student'),
        ('staff', 'Staff'),
        ('visitor', 'Visitor'),
    )
    
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    
    phone_number = models.CharField(validators=[phone_regex], max_length=17, unique=True)
    role = models.CharField(max_length=10, choices=USER_ROLES, default='student')
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=6, null=True, blank=True)
    token_created_at = models.DateTimeField(null=True, blank=True)
    
    # User preferences
    dark_mode = models.BooleanField(default=False)
    notifications_enabled = models.BooleanField(default=True)
    location_sharing = models.BooleanField(default=True)
    theme_preference = models.CharField(max_length=10, default='light')
    map_zoom_level = models.IntegerField(default=15)
    
    # Fix the reverse accessor conflicts
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name='customuser_set',
        related_query_name='customuser',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='customuser_set',
        related_query_name='customuser',
    )
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class Location(models.Model):
    LOCATION_TYPES = (
        ('building', 'Building'),
        ('classroom', 'Classroom'),
        ('office', 'Office'),
        ('library', 'Library'),
        ('cafeteria', 'Cafeteria'),
        ('parking', 'Parking'),
        ('entrance', 'Entrance'),
        ('facility', 'Facility'),
        ('landmark', 'Landmark'),
        ('dormitory', 'Dormitory'),
        ('lab', 'Laboratory'),
        ('study_room', 'Study Room'),
        ('restaurant', 'Restaurant'),
        ('food_court', 'Food Court'),
        ('lecture_hall', 'Lecture Hall'),
        ('security', 'Security'),
    )
    
    location_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=300, blank=True)  # Added missing address field
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES)
    coordinates = models.PointField()
    floor_level = models.IntegerField(default=0)
    is_accessible = models.BooleanField(default=True)
    capacity = models.IntegerField(null=True, blank=True)
    operating_hours = models.CharField(max_length=100, blank=True)
    contact_info = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='locations/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['location_type']),
            models.Index(fields=['name']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_location_type_display()})"

class NavigationRoute(models.Model):
    route_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='routes_from')
    destination_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='routes_to')
    route_path = models.LineStringField()
    distance = models.FloatField()  # in meters
    estimated_time = models.IntegerField()  # in minutes
    difficulty_level = models.CharField(
        max_length=10,
        choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
        default='easy'
    )
    is_accessible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.source_location.name} → {self.destination_location.name}"

class UserSearch(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    search_query = models.CharField(max_length=200)
    search_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)
    results_count = models.IntegerField(default=0)  # Added to track result count
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username}: {self.search_query}"

class Geofence(models.Model):
    TRIGGER_TYPES = (
        ('entry', 'Entry'),
        ('exit', 'Exit'),
        ('both', 'Both'),
    )
    
    geofence_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)  # Added description field
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    boundary = models.PolygonField()
    radius = models.FloatField(default=100)  # in meters
    trigger_type = models.CharField(max_length=10, choices=TRIGGER_TYPES, default='entry')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Geofence: {self.name}"

class SMSAlert(models.Model):
    ALERT_TYPES = (
        ('verification', 'Verification'),
        ('password_reset', 'Password Reset'),
        ('geofence_entry', 'Geofence Entry'),
        ('geofence_exit', 'Geofence Exit'),
        ('navigation', 'Navigation'),
        ('welcome', 'Welcome'),
        ('profile_update', 'Profile Update'),
        ('password_changed', 'Password Changed'),
        ('notification', 'General Notification'),
    )
    
    alert_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    message = models.TextField()
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"SMS to {self.user.phone_number}: {self.get_alert_type_display()}"

class Recommendation(models.Model):
    recommendation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    recommended_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='recommended_for')
    reason = models.CharField(max_length=200)
    score = models.FloatField(default=0.0)
    rating = models.FloatField(default=4.0)  # Added rating field
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-score', '-created_at']
    
    def __str__(self):
        return f"Recommend {self.recommended_location.name} for {self.location.name}"

class UserLocation(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    location = models.PointField()
    timestamp = models.DateTimeField(auto_now_add=True)
    accuracy = models.FloatField(null=True, blank=True)  # GPS accuracy in meters
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username} location at {self.timestamp}"

class RouteRequest(models.Model):
    """Model to track route requests for analytics"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    from_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='route_requests_from')
    to_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='route_requests_to')
    transport_mode = models.CharField(max_length=20, default='walking')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username}: {self.from_location.name} → {self.to_location.name}"

class GeofenceEntry(models.Model):
    """Model to track geofence entries/exits"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    geofence = models.ForeignKey(Geofence, on_delete=models.CASCADE)
    is_inside = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        status = "entered" if self.is_inside else "exited"
        return f"{self.user.username} {status} {self.geofence.name}"