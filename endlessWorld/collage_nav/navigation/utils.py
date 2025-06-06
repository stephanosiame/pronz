import os
from twilio.rest import Client
from django.conf import settings
from django.contrib.gis.geos import LineString, Point
import folium
from geopy.distance import geodesic
import random

def send_sms(phone_number, message):
    """Send SMS using Twilio"""
    try:
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            message = client.messages.create(
                body=message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            return True
        else:
            # In development, print the SMS to console
            print(f"SMS to {phone_number}: {message}")
            return True
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False

def generate_map_html(center_point, locations=None, route=None):
    """Generate Folium map HTML"""
    # Create map centered at the given point
    m = folium.Map(
        location=[center_point.y, center_point.x],
        zoom_start=17,
        tiles='OpenStreetMap',
        control_scale=True
    )
    
    # Add user location marker
    folium.Marker(
        [center_point.y, center_point.x],
        popup='Your Location',
        icon=folium.Icon(color='blue', icon='user')
    ).add_to(m)
    
    # Add nearby locations
    if locations:
        for location in locations:
            folium.Marker(
                [location.coordinates.y, location.coordinates.x],
                popup=f"<b>{location.name}</b><br>{location.get_location_type_display()}",
                tooltip=location.name,
                icon=folium.Icon(color='green', icon='info-sign')
            ).add_to(m)
    
    # Add route if provided
    if route:
        route_coords = [(point.y, point.x) for point in route.route_path]
        folium.PolyLine(
            route_coords,
            color='red',
            weight=5,
            opacity=0.7,
            tooltip=f"Route: {route.distance:.1f}m"
        ).add_to(m)
    
    # Return HTML representation
    return m._repr_html_()

def calculate_route(from_location=None, to_location=None, transport_mode='walking', from_coordinates=None, to_coordinates=None):
    """
    Calculate route between two points, which can be Location instances or coordinate tuples.
    Coordinates are expected as (latitude, longitude).
    """
    # Determine origin point and name
    if from_location:
        origin_point = from_location.coordinates
        origin_name = from_location.name
        origin_id = str(from_location.location_id)
    elif from_coordinates: # expects (latitude, longitude)
        origin_point = Point(from_coordinates[1], from_coordinates[0], srid=4326) # Point(lon, lat)
        origin_name = "Current Location"
        origin_id = None
    else:
        raise ValueError("Either from_location or from_coordinates must be provided for the origin.")

    # Determine destination point and name
    if to_location:
        dest_point = to_location.coordinates
        dest_name = to_location.name
        dest_id = str(to_location.location_id)
    elif to_coordinates: # expects (latitude, longitude)
        dest_point = Point(to_coordinates[1], to_coordinates[0], srid=4326) # Point(lon, lat)
        dest_name = "Selected Destination"
        dest_id = None
    else:
        raise ValueError("Either to_location or to_coordinates must be provided for the destination.")

    # Ensure points are valid GEOSGeometry objects
    if not isinstance(origin_point, Point) or not isinstance(dest_point, Point):
        raise ValueError("Origin or destination coordinates are invalid or could not be determined.")

    # Create a line between the two points
    # route_path_gis = LineString([origin_point, dest_point]) # Not directly used in simple path
    
    # Calculate distance in meters
    distance = geodesic((origin_point.y, origin_point.x), (dest_point.y, dest_point.x)).meters
    
    # Estimate time based on transport mode
    speed_multipliers = {
        'walking': 1.4,    # m/s
        'cycling': 4.2,    # m/s
        'driving': 13.9    # m/s (50 km/h)
    }
    
    speed = speed_multipliers.get(transport_mode, 1.4)
    estimated_time_minutes = int(distance / speed / 60) if speed > 0 else float('inf')
    duration_seconds = int(distance / speed) if speed > 0 else float('inf')
    
    # Create route data structure
    route_data = {
        'source': {
            'id': origin_id,
            'name': origin_name,
            'coordinates': {'lat': origin_point.y, 'lng': origin_point.x}
        },
        'destination': {
            'id': dest_id,
            'name': dest_name,
            'coordinates': {'lat': dest_point.y, 'lng': dest_point.x}
        },
        'path': [(origin_point.y, origin_point.x), (dest_point.y, dest_point.x)],
        'distance': distance,
        'estimated_time': estimated_time_minutes,
        'duration': estimated_time_minutes,
        'steps': [{
            'instruction': f"Travel from {origin_name} to {dest_name}",
            'distance': distance,
            'duration': duration_seconds
        }]
    }
    return route_data

def generate_random_route(from_point, to_point):
    """Generate a random route with intermediate points (for demo purposes)"""
    # This is just for demonstration - in production use a real routing service
    num_points = random.randint(2, 5)
    points = [from_point]
    
    for _ in range(num_points):
        # Create random intermediate points
        lat = from_point.y + (to_point.y - from_point.y) * random.random()
        lng = from_point.x + (to_point.x - from_point.x) * random.random()
        points.append(Point(lng, lat))
    
    points.append(to_point)
    return LineString(points)