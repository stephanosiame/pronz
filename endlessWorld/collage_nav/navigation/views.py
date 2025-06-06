from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, F
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import Distance
from django.contrib.gis.db.models.functions import Distance as DistanceFunction
from django.utils import timezone
from datetime import datetime, timedelta
import json
import random
import string
import folium
from folium import plugins
from .models import *
from .forms import *
from .utils import send_sms, calculate_route

# --- Constants for CoICT Campus Boundaries ---
COICT_CENTER_LAT = -6.771204359255421
COICT_CENTER_LON = 39.24001333969674
# Offset in degrees. 0.002 degrees is approx 222 meters.
# This creates a square boundary.
COICT_BOUNDS_OFFSET = 0.002

STRICT_BOUNDS = [
    [COICT_CENTER_LAT - COICT_BOUNDS_OFFSET, COICT_CENTER_LON - COICT_BOUNDS_OFFSET],  # SW corner
    [COICT_CENTER_LAT + COICT_BOUNDS_OFFSET, COICT_CENTER_LON + COICT_BOUNDS_OFFSET]   # NE corner
]
# --- End Constants ---

def home(request):
    """Home page - redirect to dashboard if authenticated"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')

def register_view(request):
    """User registration with SMS verification"""
    if request.method == 'POST':
        form = CustomUserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Send verification SMS
            message = f"Welcome to College Navigation! Your verification code is: {user.verification_token}"
            sms_sent = send_sms(user.phone_number, message)
            
            if sms_sent:
                # Create SMS alert record
                SMSAlert.objects.create(
                    user=user,
                    message=message,
                    alert_type='verification',
                    is_sent=True,
                    sent_at=timezone.now()
                )
                messages.success(request, 'Registration successful! Please check your phone for verification code.')
                return redirect('verify_token', user_id=user.id)
            else:
                messages.error(request, 'Registration successful, but SMS could not be sent. Please contact admin.')
                return redirect('login')
    else:
        form = CustomUserRegistrationForm()
    
    return render(request, 'register.html', {'form': form})

def login_view(request):
    """User login"""
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user and user.is_verified:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name}!')
                return redirect('dashboard')
            elif user and not user.is_verified:
                messages.error(request, 'Please verify your account first.')
                return redirect('verify_token', user_id=user.id)
            else:
                messages.error(request, 'Invalid credentials.')
    else:
        form = CustomLoginForm()
    
    return render(request, 'login.html', {'form': form})

@login_required
def logout_view(request):
    """User logout - THIS WAS MISSING!"""
    user_name = request.user.first_name or request.user.username
    logout(request)
    messages.success(request, f'Goodbye {user_name}! You have been logged out successfully.')
    return redirect('login')

def verify_token_view(request, user_id):
    """Verify SMS token"""
    user = get_object_or_404(CustomUser, id=user_id)
    #TODO: The token_created_at check here might be problematic if user object doesn't have it.
    # This should be reviewed if password reset verify fails.
    # if user.token_created_at and timezone.now() > user.token_created_at + timedelta(minutes=settings.PASSWORD_RESET_TIMEOUT_MINUTES):
    #    messages.error(request, 'Reset code has expired. Please request a new one.')
    #    return redirect('password_reset_request')

    if request.method == 'POST':
        form = TokenVerificationForm(request.POST)
        if form.is_valid():
            token = form.cleaned_data['token']
            
            if user.verification_token == token:
                user.is_verified = True
                user.verification_token = None
                user.save()
                
                # Send welcome SMS after verification
                welcome_message = f"Welcome {user.first_name}! Your College Navigation account is now active. You can now access all features including real-time directions and location alerts."
                send_sms(user.phone_number, welcome_message)
                
                SMSAlert.objects.create(
                    user=user,
                    message=welcome_message,
                    alert_type='welcome',
                    is_sent=True,
                    sent_at=timezone.now()
                )
                
                messages.success(request, 'Account verified successfully! You can now log in.')
                return redirect('login')
            else:
                messages.error(request, 'Invalid verification code.')
    else:
        form = TokenVerificationForm()
    
    return render(request, 'verify_token.html', {'form': form, 'user': user})

def generate_restricted_campus_map(user_location=None, nearby_locations=None, defined_bounds=None):
    """Generate a restricted campus map using Folium for CoICT-UDSM with strict bounds"""
    
    if defined_bounds is None:
        # Fallback to global STRICT_BOUNDS if not provided, though it should always be.
        defined_bounds = STRICT_BOUNDS

    center_lat = (defined_bounds[0][0] + defined_bounds[1][0]) / 2
    center_lon = (defined_bounds[0][1] + defined_bounds[1][1]) / 2
    
    # Create map centered on CoICT with full-screen settings
    campus_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=16,
        min_zoom=15,
        max_zoom=20,
        tiles='OpenStreetMap',
        attr='© OpenStreetMap contributors',
        control_scale=True,
        prefer_canvas=True,  # Better performance for many markers
    )
    
    # Set map to occupy full container
    campus_map.get_root().width = "100%"
    campus_map.get_root().height = "100%"

    # Explicitly add the primary OpenStreetMap tile layer for roads and general map view
    # This ensures it's named in the LayerControl.
    folium.TileLayer(
        tiles='OpenStreetMap',
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        name='OpenStreetMap',
        overlay=False,
        control=True
    ).add_to(campus_map)

    # Example: Add an alternative base map layer like CartoDB Positron for a different look
    # User can switch between these layers using the LayerControl
    folium.TileLayer(
        tiles='CartoDB positron',
        attr='&copy; <a href="https://carto.com/attributions">CARTO</a>',
        name='CartoDB Positron (Light)',
        overlay=False, # Base layer
        control=True,
        show=False # Initially not active, user can switch to it
    ).add_to(campus_map)
    
    # Add strict boundary rectangle using the passed defined_bounds
    folium.Rectangle(
        bounds=defined_bounds,
        color='#1e3a8a',
        weight=2,
        fill=True,
        fill_color='#1e3a8a',
        fill_opacity=0.1,
        popup='CoICT Campus Boundary'
    ).add_to(campus_map)
    
    # Add center marker
    folium.Marker(
        location=[center_lat, center_lon],
        popup='<b>CoICT Center</b><br>University of Dar es Salaam',
        icon=folium.Icon(color='blue', icon='university', prefix='fa')
    ).add_to(campus_map)
    
    # Add user location if within bounds
    if user_location:
        user_lat = user_location.y
        user_lon = user_location.x
        
        # Check if within defined_bounds
        if (defined_bounds[0][0] <= user_lat <= defined_bounds[1][0] and
            defined_bounds[0][1] <= user_lon <= defined_bounds[1][1]):
            
            folium.Marker(
                location=[user_lat, user_lon],
                popup='<b>Your Location</b><br>Within CoICT Campus',
                icon=folium.Icon(color='red', icon='user', prefix='fa')
            ).add_to(campus_map)
    
    # Add nearby locations only if within defined_bounds
    # Note: nearby_locations should already be pre-filtered by dashboard_view
    if nearby_locations:
        for location in nearby_locations: # These are already filtered
            if location.coordinates:
                lat = location.coordinates.y
                lon = location.coordinates.x
                # This check is somewhat redundant if pre-filtering is done correctly,
                # but kept as a safeguard for map marker placement.
                if (defined_bounds[0][0] <= lat <= defined_bounds[1][0] and
                    defined_bounds[0][1] <= lon <= defined_bounds[1][1]):
                    
                    folium.Marker(
                        location=[lat, lon],
                        popup=f'<b>{location.name}</b><br>{location.get_location_type_display()}',
                        icon=folium.Icon(color='green', icon='map-marker')
                    ).add_to(campus_map)
    
    # Add JavaScript to enforce strict bounds and full-screen behavior
    bounds_js = f"""
    // Define strict bounds using defined_bounds
    var strictBounds = L.latLngBounds(
        L.latLng({defined_bounds[0][0]}, {defined_bounds[0][1]}),
        L.latLng({defined_bounds[1][0]}, {defined_bounds[1][1]})
    );
    
    // Apply bounds immediately
    if (typeof window.map_{campus_map._id} !== 'undefined') {{
        // Make map full screen
        document.getElementById('{campus_map.get_name()}').style.width = '100%';
        document.getElementById('{campus_map.get_name()}').style.height = '100%';
        
        // Apply strict bounds
        window.map_{campus_map._id}.setMaxBounds(strictBounds);
        window.map_{campus_map._id}.options.maxBoundsViscosity = 1.0;
        
        // Disable dragging outside bounds
        window.map_{campus_map._id}.on('drag', function() {{
            window.map_{campus_map._id}.panInsideBounds(strictBounds, {{animate: false}});
        }});
        
        // Add boundary info
        var boundaryInfo = L.control({{position: 'topright'}});
        boundaryInfo.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'boundary-info');
            div.innerHTML = `
                <div style="background: white; padding: 8px; border-radius: 4px; 
                            box-shadow: 0 2px 4px rgba(0,0,0,0.2); font-size: 12px;
                            max-width: 200px;">
                    <strong>CoICT Campus Boundary</strong>
                    <div style="margin-top: 4px; color: #666;">
                        Only locations within this area are shown
                    </div>
                </div>
            `;
            return div;
        }};
        boundaryInfo.addTo(window.map_{campus_map._id});
    }}
    """
    
    campus_map.get_root().html.add_child(folium.Element(f"<script>{bounds_js}</script>"))
    
    # Add CSS for full-screen behavior
    map_css = """
    <style>
    .folium-map {
        width: 100% !important;
        height: 100% !important;
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        z-index: 1;
    }
    .boundary-info {
        z-index: 1000;
    }
    </style>
    """
    campus_map.get_root().html.add_child(folium.Element(map_css))

    # Add Layer Control to the map
    folium.LayerControl().add_to(campus_map)
    
    return campus_map._repr_html_()

@login_required
def dashboard_view(request):
    """Main dashboard with restricted campus map and recommendations"""
    # Get nearby locations for recommendations
    user_location = None
    # nearby_locations will be a list of Location model instances
    nearby_locations_list = []
    recommendations = []
    
    # Use the global STRICT_BOUNDS for consistency
    current_strict_bounds = STRICT_BOUNDS

    # Get user's last known location or use default college center
    try:
        user_location_obj = UserLocation.objects.filter(user=request.user).latest('timestamp')
        user_location = user_location_obj.location
        # Ensure SRID is set for existing location
        if user_location and not user_location.srid:
            user_location.srid = 4326
    except UserLocation.DoesNotExist:
        # Default to college center (Dar es Salaam coordinates) with SRID
        user_location = Point(39.23999216661627, -6.771396137358294, srid=4326)  # Point(longitude, latitude)
    
    if user_location:
        # Find all locations within a broader radius first (e.g., 5km)
        potential_nearby_locations = Location.objects.annotate(
            distance=DistanceFunction('coordinates', user_location)
        ).filter(
            coordinates__distance_lte=(user_location, Distance(km=5)) # Broad geographical filter
        ).order_by('distance')
        
        # Rigorously filter locations to be within the STRICT_BOUNDS
        # And ensure they have coordinates
        filtered_nearby_locations = []
        for loc in potential_nearby_locations:
            if loc.coordinates:
                lat, lon = loc.coordinates.y, loc.coordinates.x
                if (current_strict_bounds[0][0] <= lat <= current_strict_bounds[1][0] and
                    current_strict_bounds[0][1] <= lon <= current_strict_bounds[1][1]):
                    filtered_nearby_locations.append(loc)
        
        # Now, nearby_locations_list contains only locations strictly within bounds
        # Apply slicing after filtering
        nearby_locations_list = filtered_nearby_locations[:50]

        # Generate smart recommendations based on user preferences and time,
        # using only the strictly filtered nearby locations for context if needed
        current_hour = timezone.now().hour
        # Pass the QuerySet potential_nearby_locations or the filtered list
        # depending on how get_smart_recommendations uses it.
        # For now, assuming it can handle a list of model instances.
        recommendations = get_smart_recommendations(request.user, nearby_locations_list, current_hour)
    
    # Get recent searches
    recent_searches = UserSearch.objects.filter(user=request.user).order_by('-timestamp')[:5]
    
    # Generate restricted campus map HTML, passing the filtered list and bounds
    map_html = generate_restricted_campus_map(user_location, nearby_locations_list, defined_bounds=current_strict_bounds)
    
    # Get user preferences for theme, zoom, etc.
    user_preferences = get_user_preferences(request.user)
    
    context = {
        'nearby_locations': nearby_locations_list, # Use the filtered and sliced list
        'recommendations': recommendations,
        'recent_searches': recent_searches,
        'map_html': map_html,
        'user_location': user_location,
        'user_preferences': user_preferences,
        'total_locations': len(nearby_locations_list), # Count of the filtered list
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def search_locations(request):
    """Search for locations via AJAX with enhanced functionality"""
    query = request.GET.get('q', '')
    
    if len(query) < 2:
        return JsonResponse({'locations': []})
    
    # Enhanced search including fuzzy matching
    locations = Location.objects.filter(
        Q(name__icontains=query) | 
        Q(description__icontains=query) |
        Q(location_type__icontains=query) |
        Q(address__icontains=query)
    ).values(
        'location_id', 'name', 'location_type', 
        'description', 'address', 'coordinates'
    )[:15]
    
    # Save search query with metadata
    if query:
        UserSearch.objects.create(
            user=request.user,
            search_query=query,
            timestamp=timezone.now(),
            results_count=locations.count()
        )
    
    # Convert coordinates for JSON response
    locations_list = []
    for loc in locations:
        loc_dict = dict(loc)
        if loc['coordinates']:
            loc_dict['latitude'] = loc['coordinates'].y
            loc_dict['longitude'] = loc['coordinates'].x
            del loc_dict['coordinates']
        locations_list.append(loc_dict)
    
    return JsonResponse({'locations': locations_list})

@login_required
def get_directions(request):
    """Get directions between two points with route optimization"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            transport_mode = data.get('mode', 'walking')

            from_location_id = data.get('from_id') # Changed from 'from'
            to_location_id = data.get('to_id')     # Changed from 'to'

            from_lat = data.get('from_latitude')
            from_lon = data.get('from_longitude')
            to_lat = data.get('to_latitude')
            to_lon = data.get('to_longitude')

            from_location_obj = None
            to_location_obj = None
            from_coords_tuple = None
            to_coords_tuple = None

            # Origin
            if from_location_id:
                from_location_obj = Location.objects.get(location_id=from_location_id)
            elif from_lat is not None and from_lon is not None:
                from_coords_tuple = (float(from_lat), float(from_lon))
            else:
                # Try to get user's last known location as a fallback origin
                last_user_loc = UserLocation.objects.filter(user=request.user).order_by('-timestamp').first()
                if last_user_loc and last_user_loc.location:
                    from_coords_tuple = (last_user_loc.location.y, last_user_loc.location.x)
                    print(f"Using user's last known location as origin: {from_coords_tuple}") # For logging
                else: # If no ID, no coords, and no last known location
                    return JsonResponse({'success': False, 'error': 'Origin location or coordinates missing, and no last known location found.'}, status=400)


            # Destination
            if to_location_id:
                to_location_obj = Location.objects.get(location_id=to_location_id)
            elif to_lat is not None and to_lon is not None:
                to_coords_tuple = (float(to_lat), float(to_lon))
            else:
                return JsonResponse({'success': False, 'error': 'Destination location or coordinates missing'}, status=400)

            route_data = calculate_route(
                from_location=from_location_obj,
                to_location=to_location_obj,
                transport_mode=transport_mode,
                from_coordinates=from_coords_tuple,
                to_coordinates=to_coords_tuple
            )
            
            # Analytics and SMS sending logic
            if from_location_obj and to_location_obj: # Only if both are from existing Location instances
                RouteRequest.objects.create(
                    user=request.user,
                    from_location=from_location_obj,
                    to_location=to_location_obj,
                    transport_mode=transport_mode,
                    timestamp=timezone.now()
                )
                if request.user.notifications_enabled and route_data.get('distance', 0) > 2000:
                    message = f"Route to {to_location_obj.name} is {route_data['distance']:.0f}m. Estimated time: {route_data['duration']} minutes."
                    send_sms(request.user.phone_number, message)
                    SMSAlert.objects.create(user=request.user, message=message, alert_type='navigation', is_sent=True, sent_at=timezone.now())
            elif to_location_obj and request.user.notifications_enabled and route_data.get('distance', 0) > 2000 : # SMS if destination is known
                 message = f"Route to {to_location_obj.name} is {route_data['distance']:.0f}m. Estimated time: {route_data['duration']} minutes."
                 send_sms(request.user.phone_number, message)
                 SMSAlert.objects.create(user=request.user, message=message, alert_type='navigation', is_sent=True, sent_at=timezone.now())


            return JsonResponse({'success': True, 'route': route_data})

        except Location.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Location not found'}, status=404)
        except ValueError as ve:
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except Exception as e:
            # It's good practice to log the actual exception e to your logging system
            print(f"Unexpected error in get_directions: {e}") # Basic logging
            return JsonResponse({'success': False, 'error': 'An unexpected error occurred. Please try again.'}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method. Please use POST.'}, status=405)

@login_required
def profile_view(request):
    """User profile management with enhanced features"""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            
            # Send profile update confirmation SMS
            if user.notifications_enabled:
                message = f"Hi {user.first_name}! Your profile has been updated successfully."
                send_sms(user.phone_number, message)
                
                SMSAlert.objects.create(
                    user=user,
                    message=message,
                    alert_type='profile_update',
                    is_sent=True,
                    sent_at=timezone.now()
                )
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    
    # Get user statistics
    user_stats = {
        'total_searches': UserSearch.objects.filter(user=request.user).count(),
        'total_routes': RouteRequest.objects.filter(user=request.user).count(),
        'total_alerts': SMSAlert.objects.filter(user=request.user).count(),
        'member_since': request.user.date_joined,
    }
    
    return render(request, 'profile.html', {
        'form': form,
        'user_stats': user_stats
    })

def password_reset_request(request):
    """Request password reset via SMS"""
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            phone_number = form.cleaned_data['phone_number']
            
            try:
                user = CustomUser.objects.get(phone_number=phone_number)
                
                # Generate reset token
                reset_token = ''.join(random.choices(string.digits, k=6))
                user.verification_token = reset_token
                user.token_created_at = timezone.now()
                user.save()
                
                # Send SMS
                message = f"Password reset for College Navigation. Your reset code is: {reset_token}. This code expires in 15 minutes. If you didn't request this, please ignore."
                sms_sent = send_sms(phone_number, message)
                
                if sms_sent:
                    SMSAlert.objects.create(
                        user=user,
                        message=message,
                        alert_type='password_reset',
                        is_sent=True,
                        sent_at=timezone.now()
                    )
                    messages.success(request, 'Reset code sent to your phone! Check your messages.')
                    return redirect('password_reset_verify', user_id=user.id)
                else:
                    messages.error(request, 'Could not send SMS. Please try again or contact support.')
                    
            except CustomUser.DoesNotExist:
                # Don't reveal if user exists or not for security
                messages.success(request, 'If this phone number is registered, you will receive a reset code.')
    else:
        form = PasswordResetRequestForm()
    
    return render(request, 'password_reset_request.html', {'form': form})

def password_reset_verify(request, user_id):
    """Verify reset token and set new password"""
    user = get_object_or_404(CustomUser, id=user_id)
    
    # Check if token is expired (15 minutes)
    if user.token_created_at and timezone.now() > user.token_created_at + timedelta(minutes=15):
        messages.error(request, 'Reset code has expired. Please request a new one.')
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        token = request.POST.get('token')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if user.verification_token == token:
            if new_password == confirm_password and len(new_password) >= 8:
                user.set_password(new_password)
                user.verification_token = None
                user.token_created_at = None
                user.save()
                
                # Send confirmation SMS
                message = f"Hi {user.first_name}! Your password has been reset successfully. If this wasn't you, please contact support immediately."
                send_sms(user.phone_number, message)
                
                SMSAlert.objects.create(
                    user=user,
                    message=message,
                    alert_type='password_changed',
                    is_sent=True,
                    sent_at=timezone.now()
                )
                
                messages.success(request, 'Password reset successfully! You can now log in with your new password.')
                return redirect('login')
            else:
                messages.error(request, 'Passwords do not match or are too short (minimum 8 characters).')
        else:
            messages.error(request, 'Invalid reset code. Please check and try again.')
    
    return render(request, 'password_reset_verify.html', {'user': user})

@login_required
def update_location(request):
    """Update user's current location with geofence checking"""
    if request.method == 'POST':
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        accuracy = data.get('accuracy', 0)
        
        if latitude and longitude:
            location = Point(longitude, latitude)  # Note: Point(x, y) = Point(lng, lat)
            
            # Save user location
            user_location = UserLocation.objects.create(
                user=request.user,
                location=location,
                accuracy=accuracy,
                timestamp=timezone.now()
            )
            
            # Check geofences for alerts
            check_geofences(request.user, location)
            
            # Clean up old location records (keep only last 50)
            old_locations = UserLocation.objects.filter(
                user=request.user
            ).order_by('-timestamp')[50:]
            
            if old_locations:
                UserLocation.objects.filter(
                    id__in=[loc.id for loc in old_locations]
                ).delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Location updated successfully'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid location data'
    })

def check_geofences(user, location):
    """Check if user entered/exited any geofences and send alerts"""
    active_geofences = Geofence.objects.filter(is_active=True)
    
    for geofence in active_geofences:
        is_inside = geofence.boundary.contains(location)
        
        # Check if this is a new entry/exit
        last_status = GeofenceEntry.objects.filter(
            user=user,
            geofence=geofence
        ).order_by('-timestamp').first()
        
        if is_inside and (not last_status or not last_status.is_inside):
            # User entered geofence
            if geofence.trigger_type in ['entry', 'both']:
                message = f"Welcome to {geofence.name}! {geofence.description}"
                
                if user.notifications_enabled:
                    send_sms(user.phone_number, message)
                    
                    SMSAlert.objects.create(
                        user=user,
                        message=message,
                        alert_type='geofence_entry',
                        is_sent=True,
                        sent_at=timezone.now()
                    )
                
                # Record the entry
                GeofenceEntry.objects.create(
                    user=user,
                    geofence=geofence,
                    is_inside=True,
                    timestamp=timezone.now()
                )
                
        elif not is_inside and last_status and last_status.is_inside:
            # User exited geofence
            if geofence.trigger_type in ['exit', 'both']:
                message = f"You have left {geofence.name}. Thank you for visiting!"
                
                if user.notifications_enabled:
                    send_sms(user.phone_number, message)
                    
                    SMSAlert.objects.create(
                        user=user,
                        message=message,
                        alert_type='geofence_exit',
                        is_sent=True,
                        sent_at=timezone.now()
                    )
                
                # Record the exit
                GeofenceEntry.objects.create(
                    user=user,
                    geofence=geofence,
                    is_inside=False,
                    timestamp=timezone.now()
                )

@login_required
def update_preferences(request):
    """Update user preferences (theme, notifications, etc.)"""
    if request.method == 'POST':
        data = json.loads(request.body)
        
        user = request.user
        user.theme_preference = data.get('theme', 'light')
        user.map_zoom_level = data.get('zoom_level', 15)
        user.notifications_enabled = data.get('notifications', True)
        user.location_sharing = data.get('location_sharing', True)
        user.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Preferences updated successfully'
        })
    
    return JsonResponse({'success': False})

@login_required
def get_last_user_location(request):
    if request.method == 'GET':
        try:
            last_location_obj = UserLocation.objects.filter(user=request.user).latest('timestamp')
            if last_location_obj and last_location_obj.location: # Check if location PointField is not null
                return JsonResponse({
                    'success': True,
                    'latitude': last_location_obj.location.y,
                    'longitude': last_location_obj.location.x,
                    'timestamp': last_location_obj.timestamp
                })
            else:
                # This case might be rare if UserLocation always saves a valid Point.
                return JsonResponse({'success': False, 'message': 'Last location data is invalid or empty.'})
        except UserLocation.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'No location history found for this user.'})
        except Exception as e:
            # Log the exception e for server-side debugging
            print(f"Error in get_last_user_location: {e}") # Basic logging
            return JsonResponse({'success': False, 'message': 'An error occurred while fetching last location.'}, status=500)
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method. Only GET is allowed.'}, status=405)

@login_required
def get_location_details_json(request, location_id):
    """Return location details (name, lat, lon) as JSON."""
    try:
        location = get_object_or_404(Location, location_id=location_id)
        if location.coordinates:
            return JsonResponse({
                'success': True,
                'name': location.name,
                'latitude': location.coordinates.y,
                'longitude': location.coordinates.x
            })
        else:
            return JsonResponse({'success': False, 'error': 'Location has no coordinates.'})
    except Location.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Location not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Helper functions
def get_smart_recommendations(user, nearby_locations, current_hour):
    """Generate smart recommendations based on time and user behavior"""
    recommendations = []
    
    # Time-based recommendations
    if 7 <= current_hour <= 11:  # Morning
        priority_types = ['library', 'cafeteria', 'lecture_hall']
    elif 12 <= current_hour <= 14:  # Lunch time
        priority_types = ['cafeteria', 'restaurant', 'food_court']
    elif 15 <= current_hour <= 18:  # Afternoon
        priority_types = ['library', 'study_room', 'lab']
    else:  # Evening/Night
        priority_types = ['dormitory', 'security', 'parking']
    
    # Get recommendations based on priority types
    # nearby_locations is a list of Location model instances.
    raw_recommendations = [] # Temporary list to hold found/created recommendations

    for location_type_filter in priority_types:
        # Filter the list of Location objects using list comprehension
        matching_location_objects = [
            loc for loc in nearby_locations # nearby_locations is already the filtered list from dashboard_view
            if loc.location_type == location_type_filter
        ][:2] # Get the first 2 matches

        for loc_obj in matching_location_objects:
            existing_recommendation = Recommendation.objects.filter(recommended_location=loc_obj).order_by('-created_at').first()

            if existing_recommendation:
                # Use the existing Recommendation object's data
                raw_recommendations.append({
                    'recommended_location': loc_obj,
                    'reason': existing_recommendation.reason,
                    'rating': existing_recommendation.rating,
                    'media_url': existing_recommendation.media_url,
                    'description': loc_obj.description, # Add description from location object
                    'location_type_display': loc_obj.get_location_type_display() # Add display name for type
                })
            else:
                # Create a default dictionary if no specific Recommendation entry exists
                # Attempt to get media_url from the location's image field if available
                media_url_fallback = None
                if loc_obj.image and hasattr(loc_obj.image, 'url'):
                    media_url_fallback = loc_obj.image.url

                raw_recommendations.append({
                    'recommended_location': loc_obj,
                    'reason': f'Popular {loc_obj.get_location_type_display()} nearby',
                    'rating': 4.0,
                    'media_url': media_url_fallback,
                    'description': loc_obj.description,
                    'location_type_display': loc_obj.get_location_type_display()
                })

    # Limit to 6 recommendations. This structure is already a list of dicts.
    return raw_recommendations[:6]

def get_user_preferences(user):
    """Get user preferences with defaults"""
    return {
        'theme': getattr(user, 'theme_preference', 'light'),
        'zoom_level': getattr(user, 'map_zoom_level', 15),
        'notifications_enabled': getattr(user, 'notifications_enabled', True),
        'location_sharing': getattr(user, 'location_sharing', True),
    }