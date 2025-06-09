import os
import osmnx as ox
import networkx as nx
from django.contrib.gis.geos import Polygon, LineString, Point
from django.conf import settings
from twilio.rest import Client
import folium
from geopy.distance import geodesic
import random

# CoICT Boundary and Graph Storage
COICT_CENTER_LAT = -6.771204359255421
COICT_CENTER_LON = 39.24001333969674
COICT_BOUNDS_OFFSET = 0.003 # Approx 333 meters, adjust if needed

COICT_BOUNDARY_POLYGON = Polygon.from_bbox((
    COICT_CENTER_LON - COICT_BOUNDS_OFFSET,
    COICT_CENTER_LAT - COICT_BOUNDS_OFFSET,
    COICT_CENTER_LON + COICT_BOUNDS_OFFSET,
    COICT_CENTER_LAT + COICT_BOUNDS_OFFSET
))
COICT_BOUNDARY_POLYGON.srid = 4326

# Ensure BASE_DIR is available, if not, define a sensible default (e.g., current file's directory's parent)
# This is usually set by Django manage.py, but utils.py might be imported in other contexts
if not hasattr(settings, 'BASE_DIR'):
    # Fallback if settings.BASE_DIR is not configured (e.g. running script standalone)
    settings.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRAPH_FILE_PATH = os.path.join(settings.BASE_DIR, 'coict_campus_graph.graphml')
COICT_GRAPH = None # Global variable to hold the loaded graph


def load_coict_graph():
    global COICT_GRAPH
    if COICT_GRAPH is not None and COICT_GRAPH.number_of_nodes() > 0: # Check if already loaded and not empty
        return COICT_GRAPH

    if os.path.exists(GRAPH_FILE_PATH):
        try:
            COICT_GRAPH = ox.load_graphml(GRAPH_FILE_PATH)
            # Check if graph is empty after loading (e.g. if a previous fallback saved an empty graph)
            if COICT_GRAPH.number_of_nodes() == 0:
                print("Loaded graph from cache is empty. Attempting to re-download.")
                # Proceed to download logic by not returning here
            else:
                print(f"Loaded CoICT graph from cache: {GRAPH_FILE_PATH}")
                return COICT_GRAPH
        except Exception as e:
            print(f"Error loading graph from cache: {e}. Will attempt to re-download.")
            # Fallback: ensure COICT_GRAPH is None or empty so download is attempted
            COICT_GRAPH = nx.MultiDiGraph()


    print("Downloading CoICT campus graph data from OpenStreetMap...")
    try:
        # Using 'walk' network type. Consider 'all_private' or 'all' if more road types are needed.
        # Simplify graph to remove interstitial nodes not representing intersections.
        # retain_all=True ensures that disconnected subgraphs within the polygon are kept.
        graph = ox.graph_from_polygon(COICT_BOUNDARY_POLYGON, network_type='walk', simplify=True, retain_all=True, truncate_by_edge=True)

        # Check if the downloaded graph is empty or too small (sometimes happens if polygon is too small or no data)
        if graph.number_of_nodes() == 0:
            print("Warning: Downloaded graph is empty. Check COICT_BOUNDARY_POLYGON and OSM data for the area.")
            # Fallback to an empty graph to prevent subsequent crashes, but routing will fail.
            COICT_GRAPH = nx.MultiDiGraph()
            # Optionally, save this empty graph to prevent repeated downloads if the issue is persistent OSM data absence
            # ox.save_graphml(COICT_GRAPH, filepath=GRAPH_FILE_PATH)
            return COICT_GRAPH

        COICT_GRAPH = graph
        ox.save_graphml(COICT_GRAPH, filepath=GRAPH_FILE_PATH)
        print(f"Saved CoICT graph to {GRAPH_FILE_PATH}")
        return COICT_GRAPH
    except Exception as e:
        print(f"CRITICAL: Could not download or process CoICT graph: {e}")
        # Fallback: Create an empty graph to prevent crashes, routing will fail.
        # Save the empty graph to avoid repeated download attempts if there's a persistent issue.
        COICT_GRAPH = nx.MultiDiGraph()
        try:
            ox.save_graphml(COICT_GRAPH, filepath=GRAPH_FILE_PATH)
            print(f"Saved empty fallback graph to {GRAPH_FILE_PATH} to prevent repeated download failures.")
        except Exception as save_e:
            print(f"Error saving empty fallback graph: {save_e}")
        return COICT_GRAPH

# Load the graph when the module is imported
load_coict_graph()

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
    Uses OSMnx graph for pathfinding within CoICT campus.
    """
    global COICT_GRAPH
    if COICT_GRAPH is None or COICT_GRAPH.number_of_nodes() == 0:
        print("CoICT graph not loaded or is empty, attempting to load...")
        load_coict_graph() # Attempt to load again
        if COICT_GRAPH is None or COICT_GRAPH.number_of_nodes() == 0:
            raise ValueError("CoICT campus map data is unavailable. Cannot calculate route.")

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

    # Ensure points are valid GEOSGeometry objects
    if not isinstance(origin_point, Point) or not isinstance(dest_point, Point):
        raise ValueError("Origin or destination coordinates are invalid or could not be determined.")

    # Snap points to the graph
    try:
        # Ensure graph has 'x' and 'y' attributes for nodes if not loaded from ox.graph_from_projected
        # If loaded directly from graphml and originally from non-projected, it should have them.
        # If graph is projected, nearest_nodes expects projected coordinates.
        # For now, assume graph is in lat/lon (EPSG:4326) as per ox.graph_from_polygon default.
        origin_node = ox.nearest_nodes(COICT_GRAPH, X=origin_point.x, Y=origin_point.y)
        destination_node = ox.nearest_nodes(COICT_GRAPH, X=dest_point.x, Y=dest_point.y)
    except Exception as e:
        print(f"Error finding nearest nodes: {e}. Points: Origin({origin_point.x},{origin_point.y}), Dest({dest_point.x},{dest_point.y})")
        # Check if graph has nodes at all
        if COICT_GRAPH.number_of_nodes() == 0:
            raise ValueError("Campus map data is empty. Cannot snap points.")
        # Check if nodes have x and y data, which is needed by nearest_nodes
        # sample_node = list(COICT_GRAPH.nodes(data=True))[0]
        # if 'x' not in sample_node[1] or 'y' not in sample_node[1]:
        #    print("Graph nodes are missing 'x' or 'y' attributes for nearest_nodes calculation.")
        raise ValueError("Could not snap start or end points to the campus map. Ensure they are within CoICT boundary.") from e

    # Pathfinding
    try:
        route_node_ids = nx.shortest_path(COICT_GRAPH, source=origin_node, target=destination_node, weight='length')

        route_path_coords = []
        for node_id in route_node_ids:
            node_data = COICT_GRAPH.nodes[node_id]
            route_path_coords.append((node_data['y'], node_data['x'])) # (lat, lon)

        distance_meters = nx.shortest_path_length(COICT_GRAPH, source=origin_node, target=destination_node, weight='length')

    except nx.NetworkXNoPath:
        # Fallback to straight line if no path found on graph? Or just raise error?
        # For now, raise error as it indicates issue with graph or points being too far apart on disconnected components.
        print(f"No path found between {origin_name} (Node {origin_node}) and {dest_name} (Node {destination_node}) on the campus map.")
        raise ValueError(f"No path found between {origin_name} and {dest_name} on the campus map.")
    except Exception as e:
        print(f"Error during pathfinding: {e}")
        raise ValueError("An unexpected error occurred while calculating the route.") from e

    # Estimate time based on transport mode (using actual path distance)
    speed_multipliers = {
        'walking': 1.4,    # m/s
        'cycling': 4.2,    # m/s
        'driving': 13.9    # m/s (50 km/h)
    }
    speed = speed_multipliers.get(transport_mode, 1.4) # Default to walking speed
    estimated_time_minutes = int(distance_meters / speed / 60) if speed > 0 else float('inf')
    duration_seconds = int(distance_meters / speed) if speed > 0 else float('inf')

    route_data = {
        'source': {
            'id': origin_id,
            'name': origin_name,
            'coordinates': {'lat': origin_point.y, 'lng': origin_point.x} # Original point
        },
        'destination': {
            'id': dest_id,
            'name': dest_name,
            'coordinates': {'lat': dest_point.y, 'lng': dest_point.x} # Original point
        },
        'path': route_path_coords, # Path from graph
        'distance': round(distance_meters, 2),
        'estimated_time': estimated_time_minutes, # Based on graph path
        'duration': duration_seconds, # Using new name for consistency, was estimated_time_minutes
        'steps': [{
            'instruction': f"Follow the highlighted route from {origin_name} to {dest_name}.",
            'distance': round(distance_meters, 2),
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