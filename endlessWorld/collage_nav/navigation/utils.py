import os
import logging # Added
from shapely.wkt import loads as load_wkt # Added
import osmnx as ox
import networkx as nx
from requests.exceptions import RequestException # Added for network errors
from django.contrib.gis.geos import Polygon, LineString, Point
from django.conf import settings
from twilio.rest import Client
import folium
from geopy.distance import geodesic
import random

# Logger instance
logger = logging.getLogger(__name__)

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
        logger.info("CoICT graph already loaded and non-empty.")
        return COICT_GRAPH

    if os.path.exists(GRAPH_FILE_PATH):
        try:
            logger.info(f"Attempting to load CoICT graph from cache: {GRAPH_FILE_PATH}")
            COICT_GRAPH = ox.load_graphml(GRAPH_FILE_PATH)
            if COICT_GRAPH.number_of_nodes() == 0:
                logger.warning("Loaded graph from cache is empty. Attempting to re-download.")
            else:
                logger.info(f"Successfully loaded CoICT graph from cache: {GRAPH_FILE_PATH}")
                return COICT_GRAPH
        except (nx.NetworkXError, EOFError, FileNotFoundError) as e: # More specific exceptions
            logger.error(f"Error loading graph from cache: {e}. Will attempt to re-download.")
            COICT_GRAPH = nx.MultiDiGraph() # Ensure fallback to download
        except Exception as e: # Catch any other unexpected errors during loading
            logger.error(f"Unexpected error loading graph from cache: {e}. Will attempt to re-download.")
            COICT_GRAPH = nx.MultiDiGraph() # Ensure fallback to download

    logger.info("Downloading CoICT campus graph data from OpenStreetMap as it's not cached or cache is invalid.")
    try:
        # Convert Django GEOS Polygon to Shapely Polygon
        shapely_polygon = load_wkt(COICT_BOUNDARY_POLYGON.wkt)

        graph = ox.graph_from_polygon(
            shapely_polygon, # Use the converted shapely polygon
            network_type='walk',
            simplify=True,
            retain_all=True,
            truncate_by_edge=True
        )

        if graph.number_of_nodes() == 0:
            logger.warning("Downloaded graph is empty. This might be due to issues with COICT_BOUNDARY_POLYGON or OSM data availability for the area.")
            COICT_GRAPH = nx.MultiDiGraph() # Fallback to an empty graph
            # Not saving empty graph to cache to allow retries if OSM data becomes available
            return COICT_GRAPH

        COICT_GRAPH = graph
        logger.info(f"Successfully downloaded CoICT graph with {COICT_GRAPH.number_of_nodes()} nodes and {COICT_GRAPH.number_of_edges()} edges.")
        try:
            ox.save_graphml(COICT_GRAPH, filepath=GRAPH_FILE_PATH)
            logger.info(f"Saved CoICT graph to {GRAPH_FILE_PATH}")
        except Exception as save_e: # Catch errors during saving
            logger.error(f"Error saving downloaded CoICT graph to {GRAPH_FILE_PATH}: {save_e}")
        return COICT_GRAPH
    except RequestException as e: # Specific for network/download errors
        logger.critical(f"Network error while downloading CoICT graph: {e}")
        COICT_GRAPH = nx.MultiDiGraph() # Fallback to empty graph
        # Consider not saving empty graph here to allow retries on network recovery
        return COICT_GRAPH
    except (nx.NetworkXError, Exception) as e: # Catch osmnx/networkx specific errors and other general processing errors
        logger.critical(f"Could not download or process CoICT graph: {e}")
        COICT_GRAPH = nx.MultiDiGraph() # Fallback to empty graph
        try:
            # Save this empty graph to prevent repeated failed downloads if the issue is persistent (e.g. bad polygon)
            ox.save_graphml(COICT_GRAPH, filepath=GRAPH_FILE_PATH)
            logger.info(f"Saved empty fallback graph to {GRAPH_FILE_PATH} to prevent repeated download/processing failures.")
        except Exception as save_e:
            logger.error(f"Error saving empty fallback graph after download failure: {save_e}")
        return COICT_GRAPH

# Load the graph when the module is imported
# This should be called by applications using the utils, not necessarily on module import
# to give more control over when this potentially long operation runs.
# For now, keeping it as is based on original structure.
if __name__ == '__main__': # Example of how it might be controlled
    load_coict_graph()
else:
    # If not running as main, load it as it was originally
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
        logger.warning("CoICT graph not loaded or is empty when starting calculate_route. Attempting to load...")
        load_coict_graph() # Attempt to load again
        if COICT_GRAPH is None or COICT_GRAPH.number_of_nodes() == 0:
            logger.error("CoICT campus map data is unavailable after attempting load. Cannot calculate route.")
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
        origin_node = ox.nearest_nodes(COICT_GRAPH, X=origin_point.x, Y=origin_point.y)
        destination_node = ox.nearest_nodes(COICT_GRAPH, X=dest_point.x, Y=dest_point.y)
    except Exception as e:
        logger.error(f"Error finding nearest nodes: {e}. Points: Origin({origin_point.x},{origin_point.y}), Dest({dest_point.x},{dest_point.y})")
        if COICT_GRAPH.number_of_nodes() == 0:
            logger.error("Campus map data is empty. Cannot snap points.")
            raise ValueError("Campus map data is empty. Cannot snap points.")
        # Additional check if nodes have x/y, though ox.nearest_nodes should handle this or graph loading should ensure it.
        # sample_node_id = list(COICT_GRAPH.nodes())[0] if COICT_GRAPH.nodes() else None
        # if sample_node_id and ('x' not in COICT_GRAPH.nodes[sample_node_id] or 'y' not in COICT_GRAPH.nodes[sample_node_id]):
        #    logger.error("Graph nodes are missing 'x' or 'y' attributes required for nearest_nodes.")
        raise ValueError("Could not snap start or end points to the campus map. Ensure they are within CoICT boundary.") from e

    # Pathfinding
    try:
        route_node_ids = nx.shortest_path(COICT_GRAPH, source=origin_node, target=destination_node, weight='length')
        distance_meters = nx.shortest_path_length(COICT_GRAPH, source=origin_node, target=destination_node, weight='length')

        route_path_coords = []
        for node_id in route_node_ids:
            node_data = COICT_GRAPH.nodes[node_id]
            route_path_coords.append((node_data['y'], node_data['x'])) # (lat, lon)

    except nx.NetworkXNoPath:
        logger.warning(f"No path found between {origin_name} (Node {origin_node}) and {dest_name} (Node {destination_node}) on the campus map.")
        raise ValueError(f"No path found between {origin_name} and {dest_name} on the campus map.")
    except Exception as e:
        logger.error(f"Error during pathfinding (shortest_path or shortest_path_length): {e}")
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
        'duration': duration_seconds,
        'steps': [] # Placeholder, will be populated below
    }

    # Generate detailed steps
    if len(route_node_ids) < 2:
        # This case should ideally not happen if a path is found, but handle defensively
        route_data['steps'].append({
            'instruction': f"Proceed from {origin_name} to {dest_name}.",
            'distance': route_data['distance'],
            'duration': route_data['duration'],
            'node_start': origin_node,
            'node_end': destination_node
        })
    else:
        current_distance = 0
        current_duration = 0
        for i in range(len(route_node_ids) - 1):
            u = route_node_ids[i]
            v = route_node_ids[i+1]

            # Get edge data. A MultiDiGraph can have multiple edges between two nodes (u,v),
            # usually distinguished by a key (defaulting to 0 if only one).
            # We'll try to get the data for the first key (0).
            edge_data = COICT_GRAPH.get_edge_data(u, v, 0) # Get data for key 0
            segment_length = edge_data.get('length', 0) if edge_data else 0 # Default to 0 if no length
            segment_duration = int(segment_length / speed) if speed > 0 else float('inf')

            street_name_parts = []
            if edge_data:
                # Try to get street name, could be a list or a string
                name_attr = edge_data.get('name')
                if isinstance(name_attr, list):
                    street_name_parts.extend(name_attr)
                elif isinstance(name_attr, str):
                    street_name_parts.append(name_attr)

                # Also check for highway type as it can be descriptive
                highway_attr = edge_data.get('highway')
                if isinstance(highway_attr, list): # highway can also be a list
                    street_name_parts.extend([h for h in highway_attr if h not in street_name_parts]) # Avoid duplicates
                elif isinstance(highway_attr, str) and highway_attr not in street_name_parts:
                    street_name_parts.append(highway_attr)

            if street_name_parts:
                # Join parts, filter out None or empty strings if any somehow got in
                path_description = ", ".join(filter(None, street_name_parts))
                instruction = f"Proceed along {path_description} from node {u} to node {v}."
            else:
                instruction = f"Proceed along path segment {i+1} (Node {u} to Node {v})."

            route_data['steps'].append({
                'instruction': instruction,
                'distance': round(segment_length, 2),
                'duration': segment_duration,
                'node_start': u,
                'node_end': v,
                'street_name': path_description if street_name_parts else "N/A"
            })
            current_distance += segment_length
            current_duration += segment_duration

        # Update total distance and duration based on summed segments if different from direct calculation
        # This can happen due to rounding or if 'length' attribute isn't perfectly consistent
        route_data['distance'] = round(current_distance, 2)
        route_data['duration'] = int(current_duration)
        route_data['estimated_time'] = int(current_duration / 60) if current_duration != float('inf') else float('inf')


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