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

COICT_BOUNDARY_POLYGON = Polygon.from_bbox(( # type: ignore
    COICT_CENTER_LON - COICT_BOUNDS_OFFSET,
    COICT_CENTER_LAT - COICT_BOUNDS_OFFSET,
    COICT_CENTER_LON + COICT_BOUNDS_OFFSET,
    COICT_CENTER_LAT + COICT_BOUNDS_OFFSET
))
COICT_BOUNDARY_POLYGON.srid = 4326 # type: ignore

# Ensure BASE_DIR is available, if not, define a sensible default (e.g., current file's directory's parent)
# This is usually set by Django manage.py, but utils.py might be imported in other contexts
if not hasattr(settings, 'BASE_DIR'):
    # Fallback if settings.BASE_DIR is not configured (e.g. running script standalone)
    settings.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRAPH_FILE_PATH = os.path.join(settings.BASE_DIR, 'coict_campus_graph.graphml')
COICT_GRAPH: nx.MultiDiGraph | None = None # Global variable to hold the loaded graph


def load_coict_graph():
    global COICT_GRAPH
    logger.info("Starting CoICT graph loading process.")

    if COICT_GRAPH is not None and COICT_GRAPH.number_of_nodes() > 0:
        logger.info(f"CoICT graph already loaded: {COICT_GRAPH.number_of_nodes()} nodes, {COICT_GRAPH.number_of_edges()} edges.")
        return COICT_GRAPH

    if os.path.exists(GRAPH_FILE_PATH):
        try:
            logger.info(f"Attempting to load CoICT graph from cache: {GRAPH_FILE_PATH}")
            COICT_GRAPH = ox.load_graphml(GRAPH_FILE_PATH)
            if COICT_GRAPH is not None and COICT_GRAPH.number_of_nodes() > 0:
                logger.info(f"Successfully loaded CoICT graph from cache: {COICT_GRAPH.number_of_nodes()} nodes, {COICT_GRAPH.number_of_edges()} edges.")
                return COICT_GRAPH
            else:
                logger.warning("Loaded graph from cache is empty or invalid. Will attempt to download.")
                # COICT_GRAPH will be None or empty, proceed to download
        except (FileNotFoundError, EOFError, nx.NetworkXError) as e:
            logger.warning(f"Cache miss or error loading graph from cache ({GRAPH_FILE_PATH}): {e}. Triggering download.")
            # COICT_GRAPH might be None or an empty graph from a failed load, ensure it's reset for download
            COICT_GRAPH = None
        except Exception as e:
            logger.error(f"Unexpected error loading graph from cache ({GRAPH_FILE_PATH}): {e}. Will attempt to download.")
            COICT_GRAPH = None # Ensure fallback to download

    if COICT_GRAPH is None or COICT_GRAPH.number_of_nodes() == 0: # Proceed to download if cache load failed or graph is empty
        logger.info("Starting graph download from OSM as it's not cached, cache is invalid, or cached graph is empty.")
        try:
            shapely_polygon = load_wkt(COICT_BOUNDARY_POLYGON.wkt) # type: ignore
            downloaded_graph = ox.graph_from_polygon(
                shapely_polygon,
                network_type='walk',
                simplify=True,
                retain_all=True,
                truncate_by_edge=True
            )

            if downloaded_graph is None or downloaded_graph.number_of_nodes() == 0:
                logger.warning("Downloaded graph is empty. This might be due to issues with COICT_BOUNDARY_POLYGON or OSM data availability.")
                COICT_GRAPH = nx.MultiDiGraph() # Fallback to an empty graph, do not save to cache.
            else:
                COICT_GRAPH = downloaded_graph
                logger.info(f"Successfully downloaded CoICT graph: {COICT_GRAPH.number_of_nodes()} nodes, {COICT_GRAPH.number_of_edges()} edges.")
                try:
                    ox.save_graphml(COICT_GRAPH, filepath=GRAPH_FILE_PATH)
                    logger.info(f"Saved CoICT graph to {GRAPH_FILE_PATH}")
                except Exception as save_e:
                    logger.error(f"Failed to save downloaded CoICT graph to {GRAPH_FILE_PATH}: {save_e}")
        except RequestException as e:
            logger.error(f"Network failure during graph download from OSM: {e}")
            COICT_GRAPH = None # Explicitly set to None on download failure
        except nx.NetworkXError as e:
            logger.error(f"NetworkX error during graph processing from OSM data: {e}")
            COICT_GRAPH = None
        except Exception as e:
            logger.critical(f"Critical failure during graph download or processing from OSM: {e}")
            COICT_GRAPH = None

    if COICT_GRAPH is None or COICT_GRAPH.number_of_nodes() == 0:
        logger.critical("CoICT_GRAPH is None or empty after all loading and download attempts. Routing will be unavailable.")
        # Optionally, set COICT_GRAPH to an empty graph here if other parts of the system expect a graph object
        # However, None is more indicative of a failed load.
        # COICT_GRAPH = nx.MultiDiGraph() # Consider if this is better than None
    return COICT_GRAPH

# Load the graph when the module is imported.
# Consider application-level control for this potentially long operation.
load_coict_graph()

def send_sms(phone_number, message):
    """Send SMS using Twilio"""
    try:
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN) # type: ignore
            
            message = client.messages.create( # type: ignore
                body=message,
                from_=settings.TWILIO_PHONE_NUMBER, # type: ignore
                to=phone_number
            )
            return True
        else:
            # In development, print the SMS to console
            logger.info(f"SMS to {phone_number}: {message}") # Changed print to logger.info
            return True
    except Exception as e:
        logger.error(f"Error sending SMS: {e}") # Changed print to logger.error
        return False

def generate_map_html(center_point, locations=None, route=None):
    """Generate Folium map HTML"""
    # Create map centered at the given point
    m = folium.Map( # type: ignore
        location=[center_point.y, center_point.x], # type: ignore
        zoom_start=17,
        tiles='OpenStreetMap',
        control_scale=True
    )
    
    # Add user location marker
    folium.Marker( # type: ignore
        [center_point.y, center_point.x], # type: ignore
        popup='Your Location',
        icon=folium.Icon(color='blue', icon='user') # type: ignore
    ).add_to(m)
    
    # Add nearby locations
    if locations:
        for location in locations:
            folium.Marker( # type: ignore
                [location.coordinates.y, location.coordinates.x], # type: ignore
                popup=f"<b>{location.name}</b><br>{location.get_location_type_display()}", # type: ignore
                tooltip=location.name, # type: ignore
                icon=folium.Icon(color='green', icon='info-sign') # type: ignore
            ).add_to(m)
    
    # Add route if provided
    if route:
        route_coords = [(point.y, point.x) for point in route.route_path] # type: ignore
        folium.PolyLine( # type: ignore
            route_coords,
            color='red',
            weight=5,
            opacity=0.7,
            tooltip=f"Route: {route.distance:.1f}m" # type: ignore
        ).add_to(m)
    
    # Return HTML representation
    return m._repr_html_() # type: ignore

def calculate_route(from_location=None, to_location=None, transport_mode='walking', from_coordinates=None, to_coordinates=None):
    """
    Calculate route between two points, which can be Location instances or coordinate tuples.
    Coordinates are expected as (latitude, longitude).
    Uses OSMnx graph for pathfinding within CoICT campus.
    """
    global COICT_GRAPH
    logger.debug("Starting calculate_route function.")

    if COICT_GRAPH is None or COICT_GRAPH.number_of_nodes() == 0:
        logger.error("CoICT campus map data is currently unavailable or empty. Cannot calculate route.")
        # The subtask asks to raise ValueError if graph is None or empty AT THE VERY BEGINNING.
        # The initial load_coict_graph() at module level should have loaded it.
        # If it's still None here, it means loading failed.
        raise ValueError("CoICT campus map data is currently unavailable or empty. Cannot calculate route.")

    # Determine origin point and name
    if from_location:
        origin_point = from_location.coordinates # type: ignore
        origin_name = from_location.name # type: ignore
        origin_id = str(from_location.location_id) # type: ignore
    elif from_coordinates: # expects (latitude, longitude)
        origin_point = Point(from_coordinates[1], from_coordinates[0], srid=4326) # Point(lon, lat)
        origin_name = "Current Location"
        origin_id = None
    else:
        logger.error("Route calculation failed: Origin location or coordinates not provided.")
        raise ValueError("Either from_location or from_coordinates must be provided for the origin.")

    # Determine destination point and name
    if to_location:
        dest_point = to_location.coordinates # type: ignore
        dest_name = to_location.name # type: ignore
        dest_id = str(to_location.location_id) # type: ignore
    elif to_coordinates: # expects (latitude, longitude)
        dest_point = Point(to_coordinates[1], to_coordinates[0], srid=4326) # Point(lon, lat)
        dest_name = "Selected Destination"
        dest_id = None
    else:
        logger.error("Route calculation failed: Destination location or coordinates not provided.")
        raise ValueError("Either to_location or to_coordinates must be provided for the destination.")

    logger.info(f"Calculating route from '{origin_name}' (Lat: {origin_point.y}, Lon: {origin_point.x}) to '{dest_name}' (Lat: {dest_point.y}, Lon: {dest_point.x}). Mode: {transport_mode}")


    if not isinstance(origin_point, Point) or not isinstance(dest_point, Point):
        logger.error(f"Invalid origin or destination point type. Origin: {type(origin_point)}, Dest: {type(dest_point)}")
        raise ValueError("Origin or destination coordinates are invalid GEOS Point objects.")

    # Snap points to the graph
    origin_node, destination_node = None, None
    try:
        logger.debug(f"Attempting to snap origin point ({origin_point.x}, {origin_point.y}) to graph.")
        origin_node = ox.nearest_nodes(COICT_GRAPH, X=origin_point.x, Y=origin_point.y) # type: ignore
        logger.info(f"Snapped origin point ({origin_point.y}, {origin_point.x}) to graph node ID: {origin_node}")

        logger.debug(f"Attempting to snap destination point ({dest_point.x}, {dest_point.y}) to graph.")
        destination_node = ox.nearest_nodes(COICT_GRAPH, X=dest_point.x, Y=dest_point.y) # type: ignore
        logger.info(f"Snapped destination point ({dest_point.y}, {dest_point.x}) to graph node ID: {destination_node}")

    except Exception as e: # Broad exception as ox.nearest_nodes can raise various things internally
        logger.error(f"Failed to snap origin/destination points to graph. Origin: ({origin_point.y},{origin_point.x}), Dest: ({dest_point.y},{dest_point.x}). Error: {e}")
        raise ValueError("Could not snap start/end points to the campus map. Ensure they are within CoICT boundary and the map data is complete.") from e

    # Pathfinding
    route_node_ids = []
    distance_meters = 0.0
    try:
        logger.debug(f"Calling nx.shortest_path for origin_node: {origin_node}, destination_node: {destination_node}")
        route_node_ids = nx.shortest_path(COICT_GRAPH, source=origin_node, target=destination_node, weight='length') # type: ignore
        distance_meters = nx.shortest_path_length(COICT_GRAPH, source=origin_node, target=destination_node, weight='length') # type: ignore

        route_path_coords = []
        for node_id in route_node_ids:
            node_data = COICT_GRAPH.nodes[node_id]
            route_path_coords.append((node_data['y'], node_data['x'])) # (lat, lon)

    except nx.NetworkXNoPath:
        logger.warning(f"No path found between {origin_name} (Node {origin_node}) and {dest_name} (Node {destination_node}) on the campus map.")
        raise ValueError(f"No path found between the specified locations ('{origin_name}' to '{dest_name}') on the campus map.")
    except Exception as e: # Catch other potential errors from NetworkX or data issues
        logger.error(f"Error during NetworkX shortest_path calculation between {origin_node} and {destination_node}: {e}")
        raise ValueError("An unexpected error occurred while trying to find the shortest path on the campus map.") from e

    # Estimate time based on transport mode (using actual path distance)
    speed_multipliers = {
        'walking': 1.4,    # m/s (average walking speed)
        'cycling': 4.2,    # m/s (approx 15 km/h)
        'driving': 11.1    # m/s (approx 40 km/h, campus speed)
    }
    speed = speed_multipliers.get(transport_mode, 1.4) # Default to walking speed
    estimated_time_minutes = int(distance_meters / speed / 60) if speed > 0 else float('inf')
    duration_seconds = int(distance_meters / speed) if speed > 0 else float('inf')

    logger.info(f"Successfully calculated route: Distance: {distance_meters:.2f}m, Est. Time: {estimated_time_minutes} min ({duration_seconds}s)")

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
        route_data['steps'].append({ # type: ignore
            'instruction': f"Proceed from {origin_name} to {dest_name}.",
            'distance': route_data['distance'],
            'duration': route_data['duration'],
            'node_start': origin_node,
            'node_end': destination_node
        })
    else:
        current_distance = 0.0
        current_duration = 0
        for i in range(len(route_node_ids) - 1):
            u = route_node_ids[i]
            v = route_node_ids[i+1]

            edge_data = COICT_GRAPH.get_edge_data(u, v, 0) # type: ignore # Get data for key 0
            segment_length = edge_data.get('length', 0) if edge_data else 0.0
            segment_duration = int(segment_length / speed) if speed > 0 else float('inf')

            street_name_parts = []
            path_description = "path segment" # Default description
            if edge_data:
                name_attr = edge_data.get('name')
                if isinstance(name_attr, list):
                    street_name_parts.extend(name_attr)
                elif isinstance(name_attr, str):
                    street_name_parts.append(name_attr)

                highway_attr = edge_data.get('highway')
                if isinstance(highway_attr, list):
                    street_name_parts.extend([h for h in highway_attr if h not in street_name_parts])
                elif isinstance(highway_attr, str) and highway_attr not in street_name_parts:
                    street_name_parts.append(highway_attr)

                if street_name_parts:
                    path_description = ", ".join(filter(None, street_name_parts))


            instruction = f"Proceed along {path_description}."
            # More detailed instruction if it's not the last segment
            if i < len(route_node_ids) - 2:
                 # Try to get name of next segment for better instruction
                next_edge_data = COICT_GRAPH.get_edge_data(route_node_ids[i+1], route_node_ids[i+2], 0) # type: ignore
                next_street_name_parts = []
                if next_edge_data:
                    next_name_attr = next_edge_data.get('name')
                    if isinstance(next_name_attr, list): next_street_name_parts.extend(next_name_attr)
                    elif isinstance(next_name_attr, str): next_street_name_parts.append(next_name_attr)

                if next_street_name_parts and next_street_name_parts[0] != path_description.split(", ")[0] : # if current and next street names differ
                    instruction += f" Then turn onto {', '.join(filter(None,next_street_name_parts))}."


            route_data['steps'].append({ # type: ignore
                'instruction': instruction,
                'distance': round(segment_length, 2),
                'duration': segment_duration,
                'node_start': u,
                'node_end': v,
                'street_name': path_description if street_name_parts else "Unnamed Path"
            })
            current_distance += segment_length
            current_duration += segment_duration

        # Final step instruction towards destination name
        if route_data['steps']:
            final_step_instruction = f"Continue towards {dest_name}."
            if "then turn onto" not in route_data['steps'][-1]['instruction'].lower(): # type: ignore
                 route_data['steps'][-1]['instruction'] += f" towards {dest_name}." # type: ignore
            else: # if previous instruction already had a turn, add a new simpler step.
                 route_data['steps'].append({ # type: ignore
                    'instruction': final_step_instruction,
                    'distance': 0, # distance already covered by previous segment
                    'duration': 0, # duration already covered
                    'node_start': route_node_ids[-1] if route_node_ids else destination_node, # last node
                    'node_end': destination_node,
                    'street_name': "Destination Area"
                 })


        # Update total distance and duration based on summed segments
        route_data['distance'] = round(current_distance, 2)
        route_data['duration'] = int(current_duration)
        route_data['estimated_time'] = int(current_duration / 60) if current_duration != float('inf') else float('inf')

    logger.debug(f"Returning route_data: {route_data}")
    return route_data

def generate_random_route(from_point, to_point):
    """Generate a random route with intermediate points (for demo purposes)"""
    # This is just for demonstration - in production use a real routing service
    num_points = random.randint(2, 5)
    points = [from_point]
    
    for _ in range(num_points):
        # Create random intermediate points
        lat = from_point.y + (to_point.y - from_point.y) * random.random() # type: ignore
        lng = from_point.x + (to_point.x - from_point.x) * random.random() # type: ignore
        points.append(Point(lng, lat)) # type: ignore
    
    points.append(to_point) # type: ignore
    return LineString(points) # type: ignore