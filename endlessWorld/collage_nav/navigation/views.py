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
from django.utils import timezone
from datetime import datetime, timedelta
import json
from django.core.serializers import serialize
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
COICT_BOUNDS_OFFSET = 0.003

STRICT_BOUNDS = [
    [COICT_CENTER_LAT - COICT_BOUNDS_OFFSET, COICT_CENTER_LON - COICT_BOUNDS_OFFSET],  # SW corner
    [COICT_CENTER_LAT + COICT_BOUNDS_OFFSET, COICT_CENTER_LON + COICT_BOUNDS_OFFSET]   # NE corner
]

# Create boundary polygon for spatial queries
COICT_BOUNDARY_POLYGON = Polygon.from_bbox([
    COICT_CENTER_LON - COICT_BOUNDS_OFFSET,  # min_x (west)
    COICT_CENTER_LAT - COICT_BOUNDS_OFFSET,  # min_y (south)
    COICT_CENTER_LON + COICT_BOUNDS_OFFSET,  # max_x (east)
    COICT_CENTER_LAT + COICT_BOUNDS_OFFSET   # max_y (north)
])
COICT_BOUNDARY_POLYGON.srid = 4326
# --- End Constants ---

def is_within_coict_boundary(point):
    """Check if a point is within the COICT boundary"""
    if not point:
        return False
    
    lat, lon = point.y, point.x
    return (
        STRICT_BOUNDS[0][0] <= lat <= STRICT_BOUNDS[1][0] and
        STRICT_BOUNDS[0][1] <= lon <= STRICT_BOUNDS[1][1]
    )

def filter_locations_by_boundary(locations_queryset):
    """Filter locations to only include those within COICT boundary"""
    return locations_queryset.filter(coordinates__within=COICT_BOUNDARY_POLYGON)

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

def generate_restricted_campus_map(user_location=None, nearby_locations=None, defined_bounds=None):
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
                        icon_size=(15, 15), # Set to match your div's size
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
                    <div style="background: rgba(220, 38, 38, 0.9); color: white; padding: 10px; 
                                border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); 
                                font-size: 12px; max-width: 250px; border: 2px solid #dc2626;">
                        <div style="font-weight: bold; margin-bottom: 4px;">
                            🏛️ CoICT Campus Only
                        </div>
                        <div style="font-size: 11px; line-height: 1.3;">
                            Navigation is restricted to CoICT campus area. 
                            Only locations within the red boundary are accessible.
                        </div>
                    </div>
                `;
                return div;
            }};
            boundaryControl.addTo(map);
            
            // Fit bounds to campus area
            map.fitBounds(strictBounds, {{padding: [20, 20]}});
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
    
    # Generate restricted campus map
    map_data = generate_restricted_campus_map(
        user_location, 
        nearby_locations_list, 
        defined_bounds=current_strict_bounds
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
def search_locations(request):
    """Search for locations within COICT boundary only"""
    query = request.GET.get('q', '')
    
    if len(query) < 2:
        return JsonResponse({'locations': []})
    
    # Search only within COICT boundary
    boundary_locations = filter_locations_by_boundary(Location.objects.all())
    
    locations = boundary_locations.filter(
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
    
    return JsonResponse({
        'locations': locations_list,
        'boundary_restricted': True,
        'total_found': len(locations_list)
    })

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
            route_data = calculate_route(
                from_location=from_location_obj,
                to_location=to_location_obj,
                transport_mode=transport_mode,
                from_coordinates=from_coords_tuple,
                to_coordinates=to_coords_tuple
            )
            
            # Add boundary validation flag to response
            route_data['boundary_validated'] = True
            route_data['campus_area'] = 'CoICT'
            
            # Analytics and SMS sending logic
            if from_location_obj and to_location_obj:
                RouteRequest.objects.create(
                    user=request.user,
                    from_location=from_location_obj,
                    to_location=to_location_obj,
                    transport_mode=transport_mode,
                    timestamp=timezone.now()
                )
                if request.user.notifications_enabled and route_data.get('distance', 0) > 500:  # Lowered threshold for campus
                    message = f"Campus route to {to_location_obj.name} is {route_data['distance']:.0f}m. Estimated time: {route_data['duration']} minutes."
                    send_sms(request.user.phone_number, message)
                    SMSAlert.objects.create(
                        user=request.user, 
                        message=message, 
                        alert_type='navigation', 
                        is_sent=True, 
                        sent_at=timezone.now()
                    )

            return JsonResponse({'success': True, 'route': route_data})

        except Location.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Location not found within campus boundary'}, status=404)
        except ValueError as ve:
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except Exception as e:
            print(f"Unexpected error in get_directions: {e}")
            return JsonResponse({'success': False, 'error': 'An unexpected error occurred. Please try again.'}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method. Please use POST.'}, status=405)

@login_required
def update_location(request):
    """Update user's current location with boundary validation"""
    if request.method == 'POST':
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        accuracy = data.get('accuracy', 0)
        
        if latitude and longitude:
            location = Point(longitude, latitude, srid=4326)
            
            # Check if location is within COICT boundary
            if not is_within_coict_boundary(location):
                return JsonResponse({
                    'success': False,
                    'error': 'Location is outside CoICT campus boundary',
                    'boundary_violation': True,
                    'message': 'Your location must be within CoICT campus to use this service'
                })
            
            # Save user location
            user_location = UserLocation.objects.create(
                user=request.user,
                location=location,
                accuracy=accuracy,
                timestamp=timezone.now()
            )
            
            # Check geofences for alerts (only within boundary)
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
                'message': 'Location updated successfully within CoICT campus',
                'within_boundary': True
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid location data'
    })

def check_geofences(user, location):
    """Check geofences only within COICT boundary"""
    # Only check geofences that are within the boundary
    active_geofences = Geofence.objects.filter(
        is_active=True,
        boundary__within=COICT_BOUNDARY_POLYGON
    )
    
    for geofence in active_geofences:
        is_inside = geofence.boundary.contains(location)
        
        last_status = GeofenceEntry.objects.filter(
            user=user,
            geofence=geofence
        ).order_by('-timestamp').first()
        
        if is_inside and (not last_status or not last_status.is_inside):
            if geofence.trigger_type in ['entry', 'both']:
                message = f"Welcome to {geofence.name} at CoICT! {geofence.description}"
                
                if user.notifications_enabled:
                    send_sms(user.phone_number, message)
                    SMSAlert.objects.create(
                        user=user,
                        message=message,
                        alert_type='geofence_entry',
                        is_sent=True,
                        sent_at=timezone.now()
                    )
                
                GeofenceEntry.objects.create(
                    user=user,
                    geofence=geofence,
                    is_inside=True,
                    timestamp=timezone.now()
                )
                
        elif not is_inside and last_status and last_status.is_inside:
            if geofence.trigger_type in ['exit', 'both']:
                message = f"You have left {geofence.name} at CoICT. Thank you for visiting!"
                
                if user.notifications_enabled:
                    send_sms(user.phone_number, message)
                    SMSAlert.objects.create(
                        user=user,
                        message=message,
                        alert_type='geofence_exit',
                        is_sent=True,
                        sent_at=timezone.now()
                    )
                
                GeofenceEntry.objects.create(
                    user=user,
                    geofence=geofence,
                    is_inside=False,
                    timestamp=timezone.now()
                )

@login_required
def get_last_user_location(request):
    """Get last user location within boundary"""
    if request.method == 'GET':
        try:
            # Get recent locations and find the first one within boundary
            recent_locations = UserLocation.objects.filter(user=request.user).order_by('-timestamp')[:10]
            
            for location_obj in recent_locations:
                if location_obj.location and is_within_coict_boundary(location_obj.location):
                    return JsonResponse({
                        'success': True,
                        'latitude': location_obj.location.y,
                        'longitude': location_obj.location.x,
                        'timestamp': location_obj.timestamp,
                        'within_boundary': True
                    })
            
            return JsonResponse({
                'success': False, 
                'message': 'No location history found within CoICT campus boundary',
                'boundary_violation': True
            })
            
        except UserLocation.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'message': 'No location history found for this user'
            })
        except Exception as e:
            print(f"Error in get_last_user_location: {e}")
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred while fetching last location'
            }, status=500)
    else:
        return JsonResponse({
            'success': False, 
            'message': 'Invalid request method. Only GET is allowed'
        }, status=405)

@login_required
def get_location_details_json(request, location_id):
    """Return location details only if within boundary"""
    try:
        location = get_object_or_404(Location, location_id=location_id)
        
        if not location.coordinates:
            return JsonResponse({'success': False, 'error': 'Location has no coordinates'})
            
        if not is_within_coict_boundary(location.coordinates):
            return JsonResponse({
                'success': False, 
                'error': 'Location is outside CoICT campus boundary'
            })
            
        return JsonResponse({
            'success': True,
            'name': location.name,
            'latitude': location.coordinates.y,
            'longitude': location.coordinates.x,
            'within_boundary': True,
            'location_type': location.get_location_type_display(),
            'description': location.description or 'No description available'
        })
        
    except Location.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Location not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Keep other views unchanged...
@login_required
def profile_view(request):
    """User profile management with enhanced features"""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            
            if user.notifications_enabled:
                message = f"Hi {user.first_name}! Your CoICT navigation profile has been updated successfully."
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

# --- Notification API Views ---

@login_required
def get_unread_notification_count(request):
    # Count published notifications that the user hasn't read
    published_notifications = AdminNotification.objects.filter(is_published=True)

    unread_count = 0
    for notification in published_notifications:
        status, created = UserNotificationStatus.objects.get_or_create(
            user=request.user,
            notification=notification
            # Defaults to is_read=False, which is correct for unread logic
        )
        if not status.is_read:
            unread_count += 1

    return JsonResponse({'unread_count': unread_count})

@login_required
def get_notifications_list(request):
    notifications_data = []
    # Fetch latest 10 published notifications
    recent_published_notifications = AdminNotification.objects.filter(is_published=True).order_by('-published_at', '-created_at')[:10]

    for notification in recent_published_notifications:
        status, created = UserNotificationStatus.objects.get_or_create(
            user=request.user,
            notification=notification
        )
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'published_at': notification.published_at.strftime('%Y-%m-%d %H:%M') if notification.published_at else notification.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_read': status.is_read,
        })
    return JsonResponse({'notifications': notifications_data})

@login_required
@require_http_methods(["POST"]) # Use require_http_methods as it's already imported
def mark_notification_as_read(request, notification_id):
    try:
        # Ensure the notification exists and is published before marking as read
        notification = AdminNotification.objects.get(id=notification_id, is_published=True)

        status, created = UserNotificationStatus.objects.get_or_create(
            user=request.user,
            notification=notification
        )

        if not status.is_read:
            status.is_read = True
            status.read_at = timezone.now()
            status.save()

        return JsonResponse({'success': True, 'message': 'Notification marked as read.'})
    except AdminNotification.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Notification not found or not published.'}, status=404)
    except Exception as e:
        # Log the exception e for server-side debugging
        # For example: print(f"Error in mark_notification_as_read: {e}")
        return JsonResponse({'success': False, 'error': 'An internal error occurred.'}, status=500)

@login_required
def api_get_geofences(request):
    active_geofences = Geofence.objects.filter(is_active=True)
    # Serialize the boundary to GeoJSON directly if possible, or prepare a list of dicts
    geofences_data = []
    for gf in active_geofences:
        if gf.boundary: # Ensure boundary exists
            geofences_data.append({
                'id': gf.geofence_id,
                'name': gf.name,
                'description': gf.description,
                'boundary_geojson': json.loads(gf.boundary.geojson) # Get GeoJSON directly
            })
    return JsonResponse({'geofences': geofences_data})