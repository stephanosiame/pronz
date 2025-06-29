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
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import Distance
from django.contrib.gis.db.models.functions import Distance as DistanceFunction
from django.contrib.gis.geos import GEOSGeometry, GEOSException, LineString # Added for area search and admin routes
from django.utils import timezone
from datetime import datetime, timedelta
import json
import logging # Added
import requests # For Nominatim OSM Search
import os
from django.conf import settings
from django.core.serializers import serialize
import random
import string
import folium
from folium import plugins
from .models import *
from .forms import *
# Updated utils import
from .utils import (
    send_sms,
    calculate_route,
    is_within_coict_boundary,
    filter_locations_by_boundary,
    COICT_BOUNDARY_POLYGON, # Import if directly used by remaining views, or rely on functions
    STRICT_BOUNDS, # Import if directly used by remaining views
    COICT_CENTER_LAT, # Import if directly used by remaining views
    COICT_CENTER_LON  # Import if directly used by remaining views
)


# Logger instance
logger = logging.getLogger(__name__)

# Constants and helper functions like COICT_CENTER_LAT, COICT_CENTER_LON, COICT_BOUNDS_OFFSET,
# STRICT_BOUNDS, COICT_BOUNDARY_POLYGON, is_within_coict_boundary, filter_locations_by_boundary
# have been moved to utils.py and are imported above.

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
            user.is_verified = True
            user.save()

            # Send welcome SMS
            message = "Thanks for Register our app for navigation to CoICT collage"
            sms_sent = send_sms(user.phone_number, message)
            
            if sms_sent:
                SMSAlert.objects.create(
                    user=user,
                    message=message,
                    alert_type='welcome',
                    is_sent=True,
                    sent_at=timezone.now()
                )
                messages.success(request, 'Registration successful! You can now log in.')
                return redirect('login')
            else:
                messages.error(request, 'Registration successful, but welcome SMS could not be sent. Please contact admin if this persists.')
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
    """User logout"""
    user_name = request.user.first_name or request.user.username
    logout(request)
    messages.success(request, f'Goodbye {user_name}! You have been logged out successfully.')
    return redirect('login')

def verify_token_view(request, user_id):
    """Verify SMS token"""
    user = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        form = TokenVerificationForm(request.POST)
        if form.is_valid():
            token = form.cleaned_data['token']
            
            if user.verification_token == token:
                user.is_verified = True
                user.verification_token = None
                user.save()
                
                messages.success(request, 'Account verified successfully! You can now log in.')
                return redirect('login')
            else:
                messages.error(request, 'Invalid verification code.')
    else:
        form = TokenVerificationForm()
    
    return render(request, 'verify_token.html', {'form': form, 'user': user})

def generate_restricted_campus_map(user_location=None, nearby_locations=None, defined_bounds=None, campus_routes_features=None):
    """Generate a restricted campus map using Folium for CoICT-UDSM with strict bounds"""
    
    if defined_bounds is None:
        defined_bounds = STRICT_BOUNDS

    center_lat = (defined_bounds[0][0] + defined_bounds[1][0]) / 2
    center_lon = (defined_bounds[0][1] + defined_bounds[1][1]) / 2
    
    # Create map centered on CoICT with full-screen settings
    campus_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=17,
        min_zoom=16,
        max_zoom=20,
        tiles='OpenStreetMap',
        attr='© OpenStreetMap contributors',
        control_scale=True,
        prefer_canvas=True,
    )
    
    # Set map to occupy full container
    campus_map.get_root().width = "100%"
    campus_map.get_root().height = "100%"

    # Add OpenStreetMap tile layer
    folium.TileLayer(
        tiles='OpenStreetMap',
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        name='OpenStreetMap',
        overlay=False,
        control=True
    ).add_to(campus_map)

    # Add CartoDB Positron as alternative
    folium.TileLayer(
        tiles='CartoDB positron',
        attr='&copy; <a href="https://carto.com/attributions">CARTO</a>',
        name='CartoDB Positron (Light)',
        overlay=False,
        control=True,
        show=False
    ).add_to(campus_map)
    
    # Add COICT boundary rectangle with enhanced styling
    folium.Rectangle(
        bounds=defined_bounds,
        color="#0d239c",
        weight=3,
        fill=True,
        fill_color="#082983",
        fill_opacity=0.15,
        popup='<b>CoICT Campus Boundary</b><br>Only locations within this area are accessible',
        tooltip='CoICT Campus Area'
    ).add_to(campus_map)
    
    # Add center marker
    folium.Marker(
        location=[center_lat, center_lon],
        popup='<b>CoICT Center</b><br>University of Dar es Salaam<br>College of Information and Communication Technologies',
        tooltip='CoICT Center',
        icon=folium.Icon(color='blue', icon='university', prefix='fa')
    ).add_to(campus_map)
    
    # Add user location if within bounds
    if user_location and is_within_coict_boundary(user_location):
        folium.Marker(
            location=[user_location.y, user_location.x],
            popup='<b>Your Current Location</b><br>Within CoICT Campus',
            tooltip='You are here',
            icon=folium.Icon(color='red', icon='user', prefix='fa')
        ).add_to(campus_map)
    
    # Add nearby locations (already filtered)
    if nearby_locations:
        for location in nearby_locations:
            if location.coordinates and is_within_coict_boundary(location.coordinates):
                # Custom DivIcon marker
                div_icon_html = """
                <div style="
                    width: 15px;
                    height: 15px;
                    border-radius: 50%;
                    background-color: #2ecc71;
                    border: 2px solid white;
                    box-shadow: 0 0 5px rgba(0,0,0,0.5);
                    text-align: center;
                    line-height: 15px; /* Vertically center if adding text/icon */
                    font-size: 10px; /* Example if adding text/icon */
                    color: white; /* Example if adding text/icon */
                ">
                </div>
                """
                folium.Marker(
                    location=[location.coordinates.y, location.coordinates.x],
                    popup=f'<b>{location.name}</b><br>{location.get_location_type_display()}<br>{location.description or "No description available"}',
                    tooltip=location.name,
                    icon=folium.features.DivIcon(
                        icon_size=(12, 12), # Set to match your div's size
                        icon_anchor=(7, 7), # Anchor point (half of size)
                        html=div_icon_html,
                        popup_anchor=(0, -10) # Adjust popup anchor if needed
                    )
                ).add_to(campus_map)
    
    # Add boundary enforcement JavaScript
    bounds_js = f"""
    // Define strict bounds
    var strictBounds = L.latLngBounds(
        L.latLng({defined_bounds[0][0]}, {defined_bounds[0][1]}),
        L.latLng({defined_bounds[1][0]}, {defined_bounds[1][1]})
    );
    
    // Wait for map to be ready
    setTimeout(function() {{
        if (typeof window.map_{campus_map._id} !== 'undefined') {{
            var map = window.map_{campus_map._id};
            
            // Make map full screen
            document.getElementById('{campus_map.get_name()}').style.width = '100%';
            document.getElementById('{campus_map.get_name()}').style.height = '100%';
            
            // Apply strict bounds with high viscosity (prevents dragging outside)
            map.setMaxBounds(strictBounds);
            map.options.maxBoundsViscosity = 1.0;
            
            // Force map to stay within bounds
            map.on('drag', function() {{
                map.panInsideBounds(strictBounds, {{animate: true}});
            }});
            
            // Prevent zooming out too far to see outside boundary
            map.on('zoomend', function() {{
                if (map.getZoom() < 16) {{
                    map.setZoom(16);
                }}
            }});
            
            // Add boundary warning control
            var boundaryControl = L.control({{position: 'topright'}});
            boundaryControl.onAdd = function(map) {{
                var div = L.DomUtil.create('div', 'boundary-warning');
                div.innerHTML = `
                    <div style="background: rgba(38, 38, 220, 0.9); color: white; padding: 10px; 
                                border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); 
                                font-size: 12px; max-width: 250px; border: 2px solid 	#2563eb;">
                        <div style="font-weight: bold; margin-bottom: 4px;">
                            🏛️ CoICT Campus Only
                        </div>
                        <div style="font-size: 11px; line-height: 1.3;">
                            Navigation is restricted to CoICT campus area. 
                            Only locations within the blue boundary are accessible.
                        </div>
                    </div>
                `;
                return div;
            }};
            boundaryControl.addTo(map);
            
            // Fit bounds to campus area
            map.fitBounds(strictBounds, {{padding: [100, 100]}});
        }}
    }}, 500);
    """
    
    campus_map.get_root().html.add_child(folium.Element(f"<script>{bounds_js}</script>"))
    
    # Add enhanced CSS
    map_css = """
    <style>
    .folium-map {
        width: 100% !important;
        height: 100% !important;
        position: relative !important;
        border: 3px solid #dc2626;
        border-radius: 8px;
        overflow: hidden;
    }
    .boundary-warning {
        z-index: 1000;
        pointer-events: none;
    }
    .leaflet-control-container {
        z-index: 1001;
    }
    </style>
    """
    campus_map.get_root().html.add_child(folium.Element(map_css))

    # Add predefined campus routes if provided
    if campus_routes_features:
        for route_feature in campus_routes_features:
            route_name = route_feature.get("properties", {}).get("description", "Campus Route")
            area_num = route_feature.get("properties", {}).get("area", "N/A")
            folium.GeoJson(
                route_feature, # This is the individual GeoJSON feature (LineString)
                name=f"Route: {route_name}",
                tooltip=f"<b>{route_name}</b> (Area: {area_num})",
                style_function=lambda x: {'color': 'purple', 'weight': 4, 'opacity': 0.75} # Changed color for visibility
            ).add_to(campus_map)

    # Add Layer Control
    folium.LayerControl().add_to(campus_map)
    
    map_id = campus_map.get_name()
    map_html_representation = campus_map._repr_html_()
    return {'html': map_html_representation, 'id': map_id}

@login_required
def dashboard_view(request):
    """Main dashboard with restricted campus map and recommendations"""
    user_location = None
    nearby_locations_list = []
    recommendations = []
    current_strict_bounds = STRICT_BOUNDS

    # Get user's last known location within COICT boundary
    try:
        user_location_objs = UserLocation.objects.filter(user=request.user).order_by('-timestamp')
        for loc_obj in user_location_objs[:10]:  # Check last 10 locations
            if loc_obj.location and is_within_coict_boundary(loc_obj.location):
                user_location = loc_obj.location
                if not user_location.srid:
                    user_location.srid = 4326
                break
    except UserLocation.DoesNotExist:
        pass
    
    # If no valid user location within boundary, use COICT center
    if not user_location:
        user_location = Point(COICT_CENTER_LON, COICT_CENTER_LAT, srid=4326)
    
    # Get all locations within COICT boundary only
    try:
        # Use spatial query to get only locations within boundary
        boundary_locations = filter_locations_by_boundary(Location.objects.all())
        
        if user_location:
            # Order by distance from user location
            nearby_locations_list = list(boundary_locations.annotate(
                distance=DistanceFunction('coordinates', user_location)
            ).order_by('distance')[:50])
        else:
            nearby_locations_list = list(boundary_locations[:50])
            
        # Generate recommendations from boundary-filtered locations
        current_hour = timezone.now().hour
        recommendations = get_smart_recommendations(request.user, nearby_locations_list, current_hour)
        
    except Exception as e:
        print(f"Error filtering locations by boundary: {e}")
        nearby_locations_list = []
        recommendations = []
    
    # Get recent searches (only those that found results within boundary)
    recent_searches = UserSearch.objects.filter(
        user=request.user,
        results_count__gt=0
    ).order_by('-timestamp')[:5]

    # Load campus routes data
    campus_routes_geojson_features = []
    geojson_file_path = os.path.join(settings.BASE_DIR, 'navigation', 'data', 'coict_routes.geojson')
    try:
        if os.path.exists(geojson_file_path):
            with open(geojson_file_path, 'r') as f:
                routes_data = json.load(f)
                campus_routes_geojson_features = routes_data.get('features', [])
        else:
            logger.warning(f"Campus routes GeoJSON file not found at {geojson_file_path}")
    except Exception as e:
        logger.error(f"Error loading or parsing campus routes GeoJSON: {e}")

    # Generate restricted campus map
    map_data = generate_restricted_campus_map(
        user_location, 
        nearby_locations_list, 
        defined_bounds=current_strict_bounds,
        campus_routes_features=campus_routes_geojson_features # Pass the loaded routes
    )
    
    # Get user preferences
    user_preferences = get_user_preferences(request.user)
    
    context = {
        'nearby_locations': nearby_locations_list,
        'recommendations': recommendations,
        'recent_searches': recent_searches,
        'map_html': map_data['html'],
        'map_id': map_data['id'],
        'user_location': user_location,
        'user_preferences': user_preferences,
        'total_locations': len(nearby_locations_list),
        'boundary_info': {
            'center_lat': COICT_CENTER_LAT,
            'center_lon': COICT_CENTER_LON,
            'bounds': STRICT_BOUNDS,
            'area_name': 'CoICT Campus'
        }
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def get_directions(request):
    """Get directions between two points within COICT boundary"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            transport_mode = data.get('mode', 'walking')

            from_location_id = data.get('from_id')
            to_location_id = data.get('to_id')
            from_lat = data.get('from_latitude')
            from_lon = data.get('from_longitude')
            to_lat = data.get('to_latitude')
            to_lon = data.get('to_longitude')

            from_location_obj = None
            to_location_obj = None
            from_coords_tuple = None
            to_coords_tuple = None

            # Validate origin location is within boundary
            if from_location_id:
                from_location_obj = get_object_or_404(Location, location_id=from_location_id)
                if not is_within_coict_boundary(from_location_obj.coordinates):
                    return JsonResponse({
                        'success': False, 
                        'error': 'Origin location is outside CoICT campus boundary'
                    }, status=400)
            elif from_lat is not None and from_lon is not None:
                from_point = Point(float(from_lon), float(from_lat), srid=4326)
                if not is_within_coict_boundary(from_point):
                    return JsonResponse({
                        'success': False, 
                        'error': 'Origin coordinates are outside CoICT campus boundary'
                    }, status=400)
                from_coords_tuple = (float(from_lat), float(from_lon))
            else:
                # Try to get user's last known location within boundary
                last_user_locs = UserLocation.objects.filter(user=request.user).order_by('-timestamp')[:10]
                for last_loc in last_user_locs:
                    if last_loc.location and is_within_coict_boundary(last_loc.location):
                        from_coords_tuple = (last_loc.location.y, last_loc.location.x)
                        break
                
                if not from_coords_tuple:
                    return JsonResponse({
                        'success': False, 
                        'error': 'No valid origin location within CoICT campus boundary'
                    }, status=400)

            # Validate destination location is within boundary
            if to_location_id:
                to_location_obj = get_object_or_404(Location, location_id=to_location_id)
                if not is_within_coict_boundary(to_location_obj.coordinates):
                    return JsonResponse({
                        'success': False, 
                        'error': 'Destination location is outside CoICT campus boundary'
                    }, status=400)
            elif to_lat is not None and to_lon is not None:
                to_point = Point(float(to_lon), float(to_lat), srid=4326)
                if not is_within_coict_boundary(to_point):
                    return JsonResponse({
                        'success': False, 
                        'error': 'Destination coordinates are outside CoICT campus boundary'
                    }, status=400)
                to_coords_tuple = (float(to_lat), float(to_lon))
            else:
                return JsonResponse({
                    'success': False, 
                    'error': 'Destination location or coordinates missing'
                }, status=400)

            # Calculate route
            route_data_list = []
            try:
                route_data_list = calculate_route( # Renamed to route_data_list
                    from_location=from_location_obj,
                    to_location=to_location_obj,
                    transport_mode=transport_mode,
                    from_coordinates=from_coords_tuple,
                    to_coordinates=to_coords_tuple
                )
            except ValueError as ve:
                error_message = str(ve)
                logger.error(f"Routing Error in get_directions: {error_message}", exc_info=True) # Added exc_info
                # Check for specific local graph unavailability message from calculate_route
                if "CoICT campus map data is currently unavailable or empty for local routing" in error_message:
                    user_friendly_message = "Campus-specific map data is missing or not detailed enough for routing. Please ensure OpenStreetMap has detailed campus pathways. Routing via general map services may still be available if points are outside campus or for broader routes."
                    return JsonResponse({'success': False, 'error': user_friendly_message}, status=503)
                # For other ValueErrors (likely from OSRM or other specific issues in calculate_route)
                return JsonResponse({'success': False, 'error': error_message}, status=400)

            if route_data_list and isinstance(route_data_list, list) and route_data_list[0]:
                actual_route_info = route_data_list[0]
                response_payload = {
                    'success': True,
                    'routes': route_data_list,
                    'source_service': actual_route_info.get('source_service', 'unknown')
                }

                if from_location_obj and to_location_obj:
                    RouteRequest.objects.create(
                        user=request.user,
                        from_location=from_location_obj,
                        to_location=to_location_obj,
                        transport_mode=transport_mode,
                        timestamp=timezone.now()
                    )
                    if request.user.notifications_enabled and actual_route_info.get('summary', {}).get('totalDistance', 0) > 500:
                        distance_km = actual_route_info.get('summary', {}).get('totalDistance',0) / 1000
                        time_min = actual_route_info.get('summary', {}).get('totalTime',0) / 60
                        message_sms = f"Campus route to {to_location_obj.name} is {distance_km:.1f}km. Est. time: {time_min:.0f} min."
                        send_sms(request.user.phone_number, message_sms)
                        SMSAlert.objects.create(
                            user=request.user,
                            message=message_sms,
                            alert_type='navigation',
                            is_sent=True,
                            sent_at=timezone.now()
                        )
                return JsonResponse(response_payload)
            else:
                # This case should ideally be caught by ValueErrors in calculate_route
                # But as a safeguard if calculate_route returns empty/invalid without error:
                logger.error("get_directions: calculate_route did not return valid route data or an exception.")
                return JsonResponse({'success': False, 'error': 'Failed to calculate route due to an unexpected internal issue.'}, status=500)

        except Location.DoesNotExist:
            logger.warning(f"Location.DoesNotExist in get_directions for user {request.user.id}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Origin or destination location not found within campus boundary.'}, status=404)
        except ValueError as ve: # Catches ValueErrors raised BEFORE calculate_route (e.g., param validation)
            logger.warning(f"ValueError before calculate_route in get_directions: {str(ve)}")
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error in get_directions for user {request.user.id}: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'An unexpected server error occurred. Please try again.'}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method. Please use POST.'}, status=405)

@login_required
def update_location(request): # type: ignore
    """Update user's current location with boundary validation"""
    if request.method == 'POST':
        data = json.loads(request.body) # type: ignore
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        accuracy = data.get('accuracy', 0.0) # Default to 0.0 if not provided
        
        if latitude is not None and longitude is not None:
            try:
                location = Point(float(longitude), float(latitude), srid=4326)
            except (ValueError, TypeError):
                logger.warning(f"Invalid coordinate format received in update_location: lat={latitude}, lon={longitude}")
                return JsonResponse({'success': False, 'error': 'Invalid coordinate format.'}, status=400)

            if not is_within_coict_boundary(location):
                return JsonResponse({
                    'success': False,
                    'error': 'Location is outside CoICT campus boundary.',
                    'boundary_violation': True,
                    'message': 'Your location must be within CoICT campus to use this service.'
                }, status=400) # Status 400 for client error
            
            UserLocation.objects.create(
                user=request.user, # type: ignore
                location=location,
                accuracy=float(accuracy),
                timestamp=timezone.now()
            )
            
            check_geofences(request.user, location) # type: ignore
            
            # Clean up old location records
            old_locations_qs = UserLocation.objects.filter(user=request.user).order_by('-timestamp') # type: ignore
            ids_to_delete = list(old_locations_qs.values_list('id', flat=True)[50:])
            if ids_to_delete:
                UserLocation.objects.filter(id__in=ids_to_delete).delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Location updated successfully within CoICT campus.',
                'within_boundary': True
            })
        else:
            logger.warning("Missing latitude or longitude in update_location request.")
            return JsonResponse({'success': False, 'error': 'Missing latitude or longitude.'}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method. Please use POST.'}, status=405)


def check_geofences(user, location: Point):
    """Check geofences only within COICT boundary"""
    active_geofences = Geofence.objects.filter(
        is_active=True,
        boundary__within=COICT_BOUNDARY_POLYGON # type: ignore
    )
    
    for geofence in active_geofences:
        is_inside = geofence.boundary.contains(location) # type: ignore
        
        last_status = GeofenceEntry.objects.filter(
            user=user,
            geofence=geofence
        ).order_by('-timestamp').first()
        
        if is_inside and (not last_status or not last_status.is_inside):
            if geofence.trigger_type in ['entry', 'both']:
                message = f"Welcome to {geofence.name} at CoICT! {geofence.description}"
                
                if user.notifications_enabled: # type: ignore
                    send_sms(user.phone_number, message) # type: ignore
                    SMSAlert.objects.create(
                        user=user, message=message, alert_type='geofence_entry',
                        is_sent=True, sent_at=timezone.now()
                    )
                GeofenceEntry.objects.create(
                    user=user, geofence=geofence, is_inside=True, timestamp=timezone.now()
                )
        elif not is_inside and last_status and last_status.is_inside:
            if geofence.trigger_type in ['exit', 'both']:
                message = f"You have left {geofence.name} at CoICT. Thank you for visiting!"
                if user.notifications_enabled: # type: ignore
                    send_sms(user.phone_number, message) # type: ignore
                    SMSAlert.objects.create(
                        user=user, message=message, alert_type='geofence_exit',
                        is_sent=True, sent_at=timezone.now()
                    )
                GeofenceEntry.objects.create(
                    user=user, geofence=geofence, is_inside=False, timestamp=timezone.now()
                )

@login_required
def get_last_user_location(request): # type: ignore
    """Get last user location within boundary"""
    if request.method == 'GET':
        try:
            recent_locations = UserLocation.objects.filter(user=request.user).order_by('-timestamp')[:10] # type: ignore
            
            for loc_obj in recent_locations:
                if loc_obj.location and is_within_coict_boundary(loc_obj.location):
                    return JsonResponse({
                        'success': True,
                        'latitude': loc_obj.location.y,
                        'longitude': loc_obj.location.x,
                        'timestamp': loc_obj.timestamp.isoformat(), # Use ISO format
                        'within_boundary': True
                    })
            
            return JsonResponse({
                'success': False, 
                'error': 'No location history found within CoICT campus boundary.',
                'boundary_violation': True
            }, status=404) # 404 if no valid location found
            
        except UserLocation.DoesNotExist: # Should not happen with filter().first() or slicing
            logger.warning(f"UserLocation.DoesNotExist unexpectedly in get_last_user_location for user {request.user.id}") # type: ignore
            return JsonResponse({'success': False, 'error': 'No location history found.'}, status=404)
        except Exception as e:
            logger.error(f"Error in get_last_user_location for user {request.user.id}: {e}", exc_info=True) # type: ignore
            return JsonResponse({'success': False, 'error': 'An unexpected server error occurred.'}, status=500)

    return JsonResponse({'success': False, 'error': 'Invalid request method. Please use GET.'}, status=405)


@login_required
def get_location_details_json(request, location_id): # type: ignore
    """Return location details only if within boundary"""
    try:
        location = get_object_or_404(Location, location_id=location_id) # type: ignore
        
        if not location.coordinates: # type: ignore
            logger.warning(f"Location {location_id} has no coordinates.")
            return JsonResponse({'success': False, 'error': 'Location has no coordinates.'}, status=404)
            
        if not is_within_coict_boundary(location.coordinates): # type: ignore
            logger.warning(f"Location {location_id} is outside CoICT boundary.")
            return JsonResponse({
                'success': False, 
                'error': 'Location is outside CoICT campus boundary.'
            }, status=400) # Client error as they requested a non-campus location
            
        return JsonResponse({
            'success': True,
            'name': location.name, # type: ignore
            'latitude': location.coordinates.y, # type: ignore
            'longitude': location.coordinates.x, # type: ignore
            'within_boundary': True,
            'location_type': location.get_location_type_display(), # type: ignore
            'description': location.description or 'No description available' # type: ignore
        })
        
    except Location.DoesNotExist: # type: ignore
        logger.warning(f"Location {location_id} not found in get_location_details_json.")
        return JsonResponse({'success': False, 'error': 'Location not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_location_details_json for {location_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An unexpected server error occurred.'}, status=500)

# Keep other views unchanged...
@login_required
def profile_view(request): # type: ignore
    """User profile management with enhanced features"""
    user_instance = request.user # type: ignore
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=user_instance) # type: ignore
        if form.is_valid():
            user = form.save()
            
            if user.notifications_enabled: # type: ignore
                message = f"Hi {user.first_name}! Your CoICT navigation profile has been updated successfully." # type: ignore
                send_sms(user.phone_number, message) # type: ignore
                
                SMSAlert.objects.create(
                    user=user, message=message, alert_type='profile_update',
                    is_sent=True, sent_at=timezone.now()
                )
            
            messages.success(request, 'Profile updated successfully!') # type: ignore
            return redirect('profile') # type: ignore
    else:
        form = ProfileUpdateForm(instance=user_instance) # type: ignore
    
    user_stats = {
        'total_searches': UserSearch.objects.filter(user=user_instance).count(),
        'total_routes': RouteRequest.objects.filter(user=user_instance).count(),
        'total_alerts': SMSAlert.objects.filter(user=user_instance).count(),
        'member_since': user_instance.date_joined,
    }
    
    return render(request, 'profile.html', { # type: ignore
        'form': form,
        'user_stats': user_stats
    })

def password_reset_request(request): # type: ignore
    """Request password reset via SMS"""
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST) # type: ignore
        if form.is_valid():
            phone_number = form.cleaned_data['phone_number'] # type: ignore
            
            try:
                user = CustomUser.objects.get(phone_number=phone_number) # type: ignore
                
                reset_token = ''.join(random.choices(string.digits, k=6))
                user.verification_token = reset_token # type: ignore
                user.token_created_at = timezone.now() # type: ignore
                user.save() # type: ignore
                
                message = f"Password reset for College Navigation. Your reset code is: {reset_token}. This code expires in 15 minutes. If you didn't request this, please ignore."
                sms_sent = send_sms(phone_number, message) # type: ignore
                
                if sms_sent:
                    SMSAlert.objects.create( # type: ignore
                        user=user, message=message, alert_type='password_reset',
                        is_sent=True, sent_at=timezone.now()
                    )
                    messages.success(request, 'Reset code sent to your phone! Check your messages.') # type: ignore
                    return redirect('password_reset_verify', user_id=user.id) # type: ignore
                else:
                    messages.error(request, 'Could not send SMS. Please try again or contact support.') # type: ignore
                    
            except CustomUser.DoesNotExist: # type: ignore
                messages.success(request, 'If this phone number is registered, you will receive a reset code.') # type: ignore
    else:
        form = PasswordResetRequestForm() # type: ignore
    
    return render(request, 'password_reset_request.html', {'form': form}) # type: ignore

def password_reset_verify(request, user_id): # type: ignore
    """Verify reset token and set new password"""
    user = get_object_or_404(CustomUser, id=user_id) # type: ignore
    
    if user.token_created_at and timezone.now() > user.token_created_at + timedelta(minutes=15): # type: ignore
        messages.error(request, 'Reset code has expired. Please request a new one.') # type: ignore
        return redirect('password_reset_request') # type: ignore
    
    if request.method == 'POST':
        token = request.POST.get('token')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if user.verification_token == token: # type: ignore
            if new_password == confirm_password and new_password and len(new_password) >= 8:
                user.set_password(new_password) # type: ignore
                user.verification_token = None # type: ignore
                user.token_created_at = None # type: ignore
                user.save() # type: ignore
                
                message = f"Hi {user.first_name}! Your password has been reset successfully. If this wasn't you, please contact support immediately." # type: ignore
                send_sms(user.phone_number, message) # type: ignore
                
                SMSAlert.objects.create( # type: ignore
                    user=user, message=message, alert_type='password_changed',
                    is_sent=True, sent_at=timezone.now()
                )
                
                messages.success(request, 'Password reset successfully! You can now log in with your new password.') # type: ignore
                return redirect('login') # type: ignore
            else:
                messages.error(request, 'Passwords do not match or are too short (minimum 8 characters).') # type: ignore
        else:
            messages.error(request, 'Invalid reset code. Please check and try again.') # type: ignore
    
    return render(request, 'password_reset_verify.html', {'user': user}) # type: ignore

# This function is duplicated, removing one instance.
# def check_geofences(user, location):
#     """Check if user entered/exited any geofences and send alerts"""
#     active_geofences = Geofence.objects.filter(is_active=True)
    
#     for geofence in active_geofences:
#         is_inside = geofence.boundary.contains(location)
        
#         last_status = GeofenceEntry.objects.filter(
#             user=user,
#             geofence=geofence
#         ).order_by('-timestamp').first()
        
#         if is_inside and (not last_status or not last_status.is_inside):
#             if geofence.trigger_type in ['entry', 'both']:
#                 message = f"Welcome to {geofence.name}! {geofence.description}"
#                 if user.notifications_enabled:
#                     send_sms(user.phone_number, message)
#                     SMSAlert.objects.create(
#                         user=user, message=message, alert_type='geofence_entry',
#                         is_sent=True, sent_at=timezone.now()
#                     )
#                 GeofenceEntry.objects.create(
#                     user=user, geofence=geofence, is_inside=True, timestamp=timezone.now()
#                 )
#         elif not is_inside and last_status and last_status.is_inside:
#             if geofence.trigger_type in ['exit', 'both']:
#                 message = f"You have left {geofence.name}. Thank you for visiting!"
#                 if user.notifications_enabled:
#                     send_sms(user.phone_number, message)
#                     SMSAlert.objects.create(
#                         user=user, message=message, alert_type='geofence_exit',
#                         is_sent=True, sent_at=timezone.now()
#                     )
#                 GeofenceEntry.objects.create(
#                     user=user, geofence=geofence, is_inside=False, timestamp=timezone.now()
#                 )

@login_required
def update_preferences(request): # type: ignore
    """Update user preferences (theme, notifications, etc.)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body) # type: ignore
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in update_preferences request.")
            return JsonResponse({'success': False, 'error': 'Invalid JSON format.'}, status=400)
        
        user = request.user # type: ignore
        user.theme_preference = data.get('theme', user.theme_preference) # type: ignore
        user.map_zoom_level = data.get('zoom_level', user.map_zoom_level) # type: ignore
        user.notifications_enabled = data.get('notifications', user.notifications_enabled) # type: ignore
        user.location_sharing = data.get('location_sharing', user.location_sharing) # type: ignore
        user.save() # type: ignore
        
        return JsonResponse({
            'success': True,
            'message': 'Preferences updated successfully.'
        })
    
    return JsonResponse({'success': False, 'error': 'Invalid request method. Please use POST.'}, status=405)

# This function is duplicated. Removing one instance.
# @login_required
# def get_location_details_json(request, location_id):
#     """Return location details (name, lat, lon) as JSON."""
#     try:
#         location = get_object_or_404(Location, location_id=location_id)
#         if location.coordinates:
#             return JsonResponse({
#                 'success': True,
#                 'name': location.name,
#                 'latitude': location.coordinates.y,
#                 'longitude': location.coordinates.x
#             })
#         else:
#             return JsonResponse({'success': False, 'error': 'Location has no coordinates.'})
#     except Location.DoesNotExist:
#         return JsonResponse({'success': False, 'error': 'Location not found.'})
#     except Exception as e:
#         return JsonResponse({'success': False, 'error': str(e)})

# Helper functions
def get_smart_recommendations(user, nearby_locations: list[Location], current_hour: int):
    """Generate smart recommendations based on time and user behavior"""
    
    if 7 <= current_hour <= 11: priority_types = ['library', 'cafeteria', 'lecture_hall']
    elif 12 <= current_hour <= 14: priority_types = ['cafeteria', 'restaurant', 'food_court']
    elif 15 <= current_hour <= 18: priority_types = ['library', 'study_room', 'lab']
    else: priority_types = ['dormitory', 'security', 'parking']
    
    raw_recommendations = []
    processed_loc_ids = set()

    for loc_type in priority_types:
        # Filter from the provided nearby_locations list
        matching_locations = [
            loc for loc in nearby_locations
            if loc.location_type == loc_type and loc.location_id not in processed_loc_ids
        ]
        for loc_obj in matching_locations[:2]: # Take up to 2 for this type
            if loc_obj.location_id in processed_loc_ids:
                continue # Should not happen if logic is correct, but safeguard

            existing_rec = Recommendation.objects.filter(recommended_location=loc_obj).order_by('-created_at').first()
            media_url = existing_rec.media_url if existing_rec and existing_rec.media_url else \
                        (loc_obj.image.url if loc_obj.image and hasattr(loc_obj.image, 'url') else None)

            raw_recommendations.append({
                'recommended_location': loc_obj, # Keep the object for template access
                'reason': existing_rec.reason if existing_rec else f'Popular {loc_obj.get_location_type_display()} nearby',
                'rating': existing_rec.rating if existing_rec else 4.0,
                'media_url': media_url,
                'description': loc_obj.description or "No description available.",
                'location_type_display': loc_obj.get_location_type_display()
            })
            processed_loc_ids.add(loc_obj.location_id)
            if len(raw_recommendations) >= 6: break # Max 6 recommendations
        if len(raw_recommendations) >= 6: break

    return raw_recommendations


def get_user_preferences(user): # type: ignore
    """Get user preferences with defaults"""
    return {
        'theme': user.theme_preference if hasattr(user, 'theme_preference') else 'light', # type: ignore
        'zoom_level': user.map_zoom_level if hasattr(user, 'map_zoom_level') else 15, # type: ignore
        'notifications_enabled': user.notifications_enabled if hasattr(user, 'notifications_enabled') else True, # type: ignore
        'location_sharing': user.location_sharing if hasattr(user, 'location_sharing') else True, # type: ignore
    }

# --- Notification API Views ---

@login_required
def get_unread_notification_count(request): # type: ignore
    user = request.user # type: ignore
    published_notifications = AdminNotification.objects.filter(is_published=True) # type: ignore
    unread_count = 0
    for notification in published_notifications:
        status, _ = UserNotificationStatus.objects.get_or_create(user=user, notification=notification) # type: ignore
        if not status.is_read: # type: ignore
            unread_count += 1
    return JsonResponse({'unread_count': unread_count})

@login_required
def get_notifications_list(request): # type: ignore
    user = request.user # type: ignore
    notifications_data = []
    recent_published_notifications = AdminNotification.objects.filter(is_published=True).order_by('-published_at', '-created_at')[:10] # type: ignore

    for notification in recent_published_notifications:
        status, _ = UserNotificationStatus.objects.get_or_create(user=user, notification=notification) # type: ignore
        notifications_data.append({
            'id': notification.id, # type: ignore
            'title': notification.title, # type: ignore
            'message': notification.message, # type: ignore
            'published_at': (notification.published_at or notification.created_at).strftime('%Y-%m-%d %H:%M'), # type: ignore
            'is_read': status.is_read, # type: ignore
        })
    return JsonResponse({'notifications': notifications_data})

@login_required
@require_http_methods(["POST"])
def mark_notification_as_read(request, notification_id): # type: ignore
    user = request.user # type: ignore
    try:
        notification = AdminNotification.objects.get(id=notification_id, is_published=True) # type: ignore
        status, _ = UserNotificationStatus.objects.get_or_create(user=user, notification=notification) # type: ignore

        if not status.is_read: # type: ignore
            status.is_read = True # type: ignore
            status.read_at = timezone.now() # type: ignore
            status.save() # type: ignore
        return JsonResponse({'success': True, 'message': 'Notification marked as read.'})
    except AdminNotification.DoesNotExist: # type: ignore
        logger.warning(f"Attempt to mark non-existent/non-published notification {notification_id} as read by user {user.id}")
        return JsonResponse({'success': False, 'error': 'Notification not found or not published.'}, status=404)
    except Exception as e:
        logger.error(f"Error in mark_notification_as_read for notif {notification_id}, user {user.id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)

@login_required
def api_get_geofences(request): # type: ignore
    active_geofences = Geofence.objects.filter(is_active=True) # type: ignore
    geofences_data = []
    for gf in active_geofences:
        if gf.boundary: # type: ignore
            geofences_data.append({
                'id': gf.geofence_id, # type: ignore
                'name': gf.name, # type: ignore
                'description': gf.description, # type: ignore
                'boundary_geojson': json.loads(gf.boundary.geojson) # type: ignore
            })
    return JsonResponse({'geofences': geofences_data})

@login_required
@csrf_exempt # Consider CSRF implications if used beyond trusted clients or if state changes
@require_http_methods(["POST"]) # Enforce POST
def get_locations_in_area(request):
    """
    API endpoint to find locations within a given geographical area (polygon or bbox),
    restricted to the CoICT campus boundary.

    Method: POST
    URL: /api/locations-in-area/
    Requires Login: Yes

    JSON Payload Parameters:
        One of the following must be provided:
        - geojson_polygon (str or dict): A GeoJSON Polygon string or a GeoJSON Polygon dict
                                          defining the search area.
                                          Example (string):
                                          '{ "type": "Polygon", "coordinates": [[ [lon1, lat1], [lon2, lat2], ... ]]}'
        - bbox (str): A comma-separated string representing "min_lon,min_lat,max_lon,max_lat".
                      Example: "39.235,-6.775,39.245,-6.765"

    Successful JSON Response (200 OK):
        {
            "success": true,
            "locations": [
                {
                    "location_id": "uuid-string",
                    "name": "Location Name",
                    "location_type": "building",
                    "description": "Description text",
                    "address": "Location address",
                    "latitude": -6.12345,
                    "longitude": 39.12345
                },
                // ... other locations
            ],
            "boundary_restricted": true,
            "total_found": 2
        }

    Error JSON Response (400 Bad Request or 500 Internal Server Error):
        {
            "success": false,
            "error": "Error message describing the issue."
        }
        Common errors:
        - "Missing geojson_polygon or bbox in request."
        - "Invalid GeoJSON polygon format: <details>"
        - "Invalid bounding box format: <details>"
        - "Invalid JSON payload."
    """
    try:
        data = json.loads(request.body)
        area_polygon = None

        if 'geojson_polygon' in data:
            try:
                geojson_str = data['geojson_polygon']
                if isinstance(geojson_str, dict): # If already parsed by something upstream
                    geojson_str = json.dumps(geojson_str)

                # Validate basic GeoJSON structure (optional but good)
                geom = GEOSGeometry(geojson_str)
                if not isinstance(geom, Polygon):
                    return JsonResponse({'success': False, 'error': 'Invalid GeoJSON: Not a Polygon.'}, status=400)
                area_polygon = geom
            except (GEOSException, TypeError, json.JSONDecodeError) as e:
                logger.warning(f"Invalid GeoJSON polygon provided: {e}")
                return JsonResponse({'success': False, 'error': f'Invalid GeoJSON polygon format: {e}'}, status=400)

        elif 'bbox' in data:
            try:
                bbox_str = data['bbox']
                coords = [float(c.strip()) for c in bbox_str.split(',')]
                if len(coords) != 4:
                    raise ValueError("Bounding box must contain 4 coordinates.")
                # Ensure min_lon < max_lon and min_lat < max_lat if strict validation is needed.
                # For Polygon.from_bbox, order is (xmin, ymin, xmax, ymax)
                area_polygon = Polygon.from_bbox(coords)
                area_polygon.srid = 4326 # Assume WGS84 if not specified
            except ValueError as e:
                logger.warning(f"Invalid bounding box string: {e}")
                return JsonResponse({'success': False, 'error': f'Invalid bounding box format: {e}'}, status=400)

        else:
            return JsonResponse({'success': False, 'error': 'Missing geojson_polygon or bbox in request.'}, status=400)

        if not area_polygon: # Should have been caught by earlier checks
             return JsonResponse({'success': False, 'error': 'Could not define search area.'}, status=400)

        # Ensure the user's area has SRID set, default to 4326 if not
        if not area_polygon.srid:
            area_polygon.srid = 4326

        # Important: Intersect the user's area with the COICT campus boundary
        # to ensure we only return locations within both the requested area AND campus.
        # Note: intersection might return GeometryCollection if disjoint, or empty if no overlap.
        # However, Location.coordinates__within=area_polygon and Location.coordinates__within=COICT_BOUNDARY_POLYGON
        # effectively does this intersection at the query level.

        # Query locations within the user-defined area AND within COICT boundary
        locations_qs = Location.objects.filter(
            coordinates__within=area_polygon
        ).filter(
            coordinates__within=COICT_BOUNDARY_POLYGON # Redundant if filter_locations_by_boundary is used
        )
        # A more efficient way might be to use filter_locations_by_boundary first, then filter by user's area.
        # locations_qs = filter_locations_by_boundary(Location.objects.all()).filter(
        #     coordinates__within=area_polygon
        # )

        final_locations = locations_qs.values(
            'location_id', 'name', 'location_type',
            'description', 'address', 'coordinates'
        )[:50] # Limit results, e.g., to 50

        locations_list = []
        for loc in final_locations:
            loc_dict = dict(loc)
            if loc['coordinates']:
                loc_dict['latitude'] = loc['coordinates'].y
                loc_dict['longitude'] = loc['coordinates'].x
                del loc_dict['coordinates']
            locations_list.append(loc_dict)

        return JsonResponse({
            'success': True,
            'locations': locations_list,
            'boundary_restricted': True, # All results are implicitly campus-restricted
            'total_found': len(locations_list)
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in get_locations_in_area: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An unexpected server error occurred.'}, status=500)

# search_campus_routes_view MOVED to search_views.py

from django.contrib.auth.decorators import login_required # Ensure this is imported

@login_required
def get_campus_directions_view(request):
    """
    Provides directions based on predefined campus routes from coict_routes.geojson.
    Currently, this basic version only returns the route if start and end are the same,
    or if only one of from_route/to_route is provided (effectively a search).

    Query Parameters:
        from_route (str): The name/identifier of the starting route (e.g., "Area 1", "1").
        to_route (str): The name/identifier of the ending route (e.g., "Area 5", "5").
    Returns:
        JsonResponse:
            - route (dict): GeoJSON feature of the route if applicable.
            - message (str): Informational message.
    """
    from_route_query = request.GET.get('from_route', '').strip().lower()
    to_route_query = request.GET.get('to_route', '').strip().lower()

    if not from_route_query and not to_route_query:
        return JsonResponse({'route': None, 'message': 'Please provide at least a starting or ending route.'}, status=400)

    target_query = None
    descriptive_query_for_message = "" # Store the original query for messages

    if from_route_query and not to_route_query:
        target_query = from_route_query
        descriptive_query_for_message = request.GET.get('from_route', '')
        message_prefix = f"Displaying route for '{descriptive_query_for_message}'"
    elif not from_route_query and to_route_query:
        target_query = to_route_query
        descriptive_query_for_message = request.GET.get('to_route', '')
        message_prefix = f"Displaying route for '{descriptive_query_for_message}'"
    elif from_route_query == to_route_query:
        target_query = from_route_query
        descriptive_query_for_message = request.GET.get('from_route', '')
        message_prefix = f"Route from '{descriptive_query_for_message}' to '{request.GET.get('to_route', '')}' (same route)"
    else: # from_route_query and to_route_query are different
        return JsonResponse({
            'route': None,
            'message': "Multi-segment routing between different predefined campus routes is not yet supported. " \
                       "Please specify the same start and end route to view its path, or provide only one route."
        }, status=400)

    file_path = os.path.join(settings.BASE_DIR, 'navigation', 'data', 'coict_routes.geojson')
    if not os.path.exists(file_path):
        logger.error(f"GeoJSON file not found at {file_path} in get_campus_directions_view")
        return JsonResponse({'route': None, 'message': 'Route data file not found. Please contact admin.'}, status=500)

    try:
        with open(file_path, 'r') as f:
            geojson_data = json.load(f)

        features = geojson_data.get('features', [])
        found_route_feature = None

        for feature in features:
            properties = feature.get('properties', {})
            area_prop = str(properties.get('area', '')).lower()
            desc_prop = str(properties.get('description', '')).lower()

            if target_query == area_prop or target_query == desc_prop or target_query == desc_prop.replace("route ", ""):
                found_route_feature = feature
                break
            if target_query.isdigit() and area_prop.isdigit() and int(target_query) == int(area_prop):
                found_route_feature = feature
                break

        if found_route_feature:
            # SMS Sending Logic
            if request.user.is_authenticated and hasattr(request.user, 'notifications_enabled') and request.user.notifications_enabled:
                if hasattr(request.user, 'phone_number') and request.user.phone_number:
                    route_name = found_route_feature.get("properties", {}).get("description", "selected campus route")
                    sms_message_text = f"CoICT Nav: Details for {route_name} are ready in the app. {message_prefix}."
                    if len(sms_message_text) > 160: # Basic check for SMS length
                        sms_message_text = f"CoICT Nav: Details for {route_name} are ready in the app."

                    sms_sent_successfully = send_sms(request.user.phone_number, sms_message_text)
                    SMSAlert.objects.create(
                        user=request.user,
                        message=sms_message_text,
                        alert_type='campus_direction', # New alert type
                        is_sent=sms_sent_successfully,
                        sent_at=timezone.now() if sms_sent_successfully else None
                    )

            return JsonResponse({
                'route': found_route_feature,
                'message': f"{message_prefix}."
            }, status=200)
        else:
            return JsonResponse({
                'route': None,
                'message': f"The specified route '{descriptive_query_for_message}' was not found in the campus route data."
            }, status=404)

    except json.JSONDecodeError:
        logger.error(f"Error decoding GeoJSON file: {file_path} in get_campus_directions_view")
        return JsonResponse({'route': None, 'message': 'Error reading route data file.'}, status=500)
    except Exception as e:
        logger.error(f"Unexpected error in get_campus_directions_view: {e}", exc_info=True)
        return JsonResponse({'route': None, 'message': f'An unexpected server error occurred: {str(e)}'}, status=500)

@login_required # Or remove if public access is desired
def page_search_campus_routes(request):
    """Renders the HTML page for searching campus routes."""
    return render(request, 'navigation/search_campus_form.html')

@login_required # Or remove if public access is desired
def page_get_campus_directions(request):
    """Renders the HTML page for getting campus directions."""
    return render(request, 'navigation/directions_campus_form.html')

@login_required
def view_all_campus_paths(request):
    """
    Displays all CampusPath objects on a Leaflet map.
    """
    campus_paths = CampusPath.objects.all()

    # We need to pass the GeoJSON data in a format that JavaScript can easily use.
    # The geojson_feature field in CampusPath already stores this.
    # We'll pass the whole list of paths to the template.
    # The template's JS will then iterate and add each GeoJSON feature to the map.

    # Serialize entire CampusPath objects, or just the geojson_feature part.
    # Passing the whole objects might be useful if we want to display names/descriptions too.
    # For now, let's pass them as a list of dictionaries, taking what's needed.

    paths_data = []
    for path in campus_paths:
        paths_data.append({
            'id': path.path_id,
            'name': path.name,
            'area_id': path.area_id,
            'description': path.description,
            'geojson_feature': path.geojson_feature # This is the crucial part
        })

    context = {
        'campus_paths_data': json.dumps(paths_data), # Convert to JSON string for easy JS parsing
        'page_title': "All Campus Paths"
    }
    return render(request, 'navigation/view_all_campus_paths.html', context)