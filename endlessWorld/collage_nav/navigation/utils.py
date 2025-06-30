import os
import logging
import requests # For OSRM fallback
from shapely.wkt import loads as load_wkt
import osmnx as ox
import networkx as nx
from requests.exceptions import RequestException
from django.contrib.gis.geos import Polygon, LineString, Point
from django.conf import settings
import json # For parsing OSRM response
from twilio.rest import Client
import folium
from geopy.distance import geodesic
import random
from .models import Location, NavigationRoute # Added for Admin-defined routes

# Logger instance
logger = logging.getLogger(__name__)

# CoICT Boundary and Graph Storage
COICT_CENTER_LAT = -6.771204359255421  # Center latitude for CoICT campus
COICT_CENTER_LON = 39.24001333969674  # Center longitude for CoICT campus
COICT_BOUNDS_OFFSET = 0.003  # Approx 333 meters offset to define a square boundary around the center

# Defines the primary operational area for the application.
# Used for downloading OSM data for the campus graph and for restricting location searches/routing.
COICT_BOUNDARY_POLYGON = Polygon.from_bbox((  # type: ignore
    COICT_CENTER_LON - COICT_BOUNDS_OFFSET,  # min_x (west)
    COICT_CENTER_LAT - COICT_BOUNDS_OFFSET,  # min_y (south)
    COICT_CENTER_LON + COICT_BOUNDS_OFFSET,  # max_x (east)
    COICT_CENTER_LAT + COICT_BOUNDS_OFFSET   # max_y (north)
))
COICT_BOUNDARY_POLYGON.srid = 4326  # Set Spatial Reference ID to WGS84

# Ensure BASE_DIR is available, if not, define a sensible default (e.g., current file's directory's parent)
# This is usually set by Django manage.py, but utils.py might be imported in other contexts
if not hasattr(settings, 'BASE_DIR'):
    # Fallback if settings.BASE_DIR is not configured (e.g. running script standalone)
    logger.warning("settings.BASE_DIR not found, falling back to relative path for graph file.")
    settings.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Path to the cached GraphML file for the CoICT campus road/path network.
GRAPH_FILE_PATH = os.path.join(settings.BASE_DIR, 'coict_campus_graph.graphml')
COICT_GRAPH: nx.MultiDiGraph | None = None  # Global variable to hold the loaded osmnx graph.

def load_coict_graph():
    """
    Loads the CoICT campus graph.
    Tries to load from a cached GraphML file first. If not found or invalid,
    it downloads the graph data from OpenStreetMap using the COICT_BOUNDARY_POLYGON,
    processes it, and saves it to the cache file for future use.
    The loaded graph is stored in the global COICT_GRAPH variable.
    """
    global COICT_GRAPH
    logger.info("Starting CoICT graph loading process.")

    # If graph is already loaded and seems valid, return it.
    if COICT_GRAPH is not None and COICT_GRAPH.number_of_nodes() > 0:
        logger.info(f"CoICT graph already loaded: {COICT_GRAPH.number_of_nodes()} nodes, {COICT_GRAPH.number_of_edges()} edges.")
        return COICT_GRAPH

    # Attempt to load from cache file
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

# --- Boundary Helper Functions ---
# These were originally in views.py, moved here for centralized access.
# They rely on COICT_CENTER_LAT, COICT_CENTER_LON, COICT_BOUNDS_OFFSET,
# and COICT_BOUNDARY_POLYGON defined above in this file.

# Helper to generate STRICT_BOUNDS from constants, used by is_within_coict_boundary
STRICT_BOUNDS = [
    [COICT_CENTER_LAT - COICT_BOUNDS_OFFSET, COICT_CENTER_LON - COICT_BOUNDS_OFFSET],  # SW corner
    [COICT_CENTER_LAT + COICT_BOUNDS_OFFSET, COICT_CENTER_LON + COICT_BOUNDS_OFFSET]   # NE corner
]

def is_within_coict_boundary(point: Point) -> bool:
    """
    Check if a GEOS Point is within the defined COICT campus boundary.
    Uses STRICT_BOUNDS for a quick rectangular check.
    """
    if not point or not isinstance(point, Point):
        return False

    # Ensure point has SRID, default to 4326 if not (though ideally it should match COICT_BOUNDARY_POLYGON's SRID)
    # For this simple bounds check, SRID matching isn't strictly enforced here but is good practice for .contains()
    # if not point.srid:
    #     point.srid = 4326

    lat, lon = point.y, point.x
    return (
        STRICT_BOUNDS[0][0] <= lat <= STRICT_BOUNDS[1][0] and
        STRICT_BOUNDS[0][1] <= lon <= STRICT_BOUNDS[1][1]
    )
    # For a more precise check against the actual polygon:
    # return COICT_BOUNDARY_POLYGON.contains(point)
    # However, the views.py version used STRICT_BOUNDS, so keeping that logic.

def filter_locations_by_boundary(locations_queryset):
    """
    Filter a queryset of Location models to only include those
    whose 'coordinates' field is within the COICT_BOUNDARY_POLYGON.
    """
    return locations_queryset.filter(coordinates__within=COICT_BOUNDARY_POLYGON)
# --- End Boundary Helper Functions ---

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
    Prioritizes admin-defined routes, then OSMnx graph, then OSRM fallback.
    """
    global COICT_GRAPH
    logger.debug("Starting calculate_route function.")

    # Determine origin point and name (these are used by all methods)
    # from_location and to_location are model instances if provided, else None.
    # origin_point and dest_point are GEOS Point objects.
    if from_location:
        origin_point = from_location.coordinates
        origin_name = from_location.name
        origin_id = str(from_location.location_id) # Keep for analytics if needed
    elif from_coordinates: # expects (latitude, longitude)
        origin_point = Point(from_coordinates[1], from_coordinates[0], srid=4326) # Point(lon, lat)
        origin_name = "Current Location"
        origin_id = None
    else:
        logger.error("Route calculation failed: Origin location or coordinates not provided.")
        raise ValueError("Either from_location or from_coordinates must be provided for the origin.")

    if to_location:
        dest_point = to_location.coordinates
        dest_name = to_location.name
        dest_id = str(to_location.location_id) # Keep for analytics if needed
    elif to_coordinates: # expects (latitude, longitude)
        dest_point = Point(to_coordinates[1], to_coordinates[0], srid=4326) # Point(lon, lat)
        dest_name = "Selected Destination"
        dest_id = None
    else:
        logger.error("Route calculation failed: Destination location or coordinates not provided.")
        raise ValueError("Either to_location or to_coordinates must be provided for the destination.")

    logger.info(f"Preparing route from '{origin_name}' ({origin_point.y}, {origin_point.x}) to '{dest_name}' ({dest_point.y}, {dest_point.x}). Mode: {transport_mode}")

    if not isinstance(origin_point, Point) or not isinstance(dest_point, Point):
        logger.error(f"Invalid origin or destination point type. Origin: {type(origin_point)}, Dest: {type(dest_point)}")
        raise ValueError("Origin or destination coordinates are invalid GEOS Point objects.")

    # --- Attempt 0: Admin-defined NavigationRoute ---
    if isinstance(from_location, Location) and isinstance(to_location, Location):
        try:
            admin_route = NavigationRoute.objects.filter(
                source_location=from_location,
                destination_location=to_location,
                is_active=True
            ).first()

            if admin_route and admin_route.route_path:
                logger.info(f"Found active admin-defined route: {admin_route.name or admin_route.route_id}")

                # Convert LineStringField to list of [lat, lon] coordinates
                # route_path.coords are (lon, lat) tuples
                path_coords_admin = [[coord[1], coord[0]] for coord in admin_route.route_path.coords]

                # Ensure distance and time are valid
                admin_distance = admin_route.distance if admin_route.distance is not None else 0.0
                admin_time_minutes = admin_route.estimated_time if admin_route.estimated_time is not None else 0
                admin_time_seconds = admin_time_minutes * 60

                # Create simple instructions
                instruction_text = admin_route.description or \
                                   (admin_route.name if admin_route.name else f"Follow defined path to {to_location.name}")

                lrm_instructions_admin = [{
                    'text': instruction_text,
                    'distance': admin_distance,
                    'time': admin_time_seconds
                }]
                if not path_coords_admin and admin_distance > 0 : # If no path drawn but distance exists, make a straight line
                    logger.warning(f"Admin route {admin_route.name} has distance but no drawn path. Creating straight line.")
                    path_coords_admin = [[origin_point.y, origin_point.x], [dest_point.y, dest_point.x]]


                lrm_route_admin = {
                    'name': admin_route.name or f"Admin Route: {from_location.name} to {to_location.name}",
                    'summary': {'totalDistance': admin_distance, 'totalTime': admin_time_seconds},
                    'coordinates': path_coords_admin,
                    'waypoints': [[origin_point.y, origin_point.x], [dest_point.y, dest_point.x]],
                    'instructions': lrm_instructions_admin,
                    'source_service': 'admin_defined'
                }
                logger.info(f"Using admin-defined route. Distance: {admin_distance}m, Time: {admin_time_minutes}min")
                return [lrm_route_admin]
            elif admin_route: # Route exists but no path
                 logger.warning(f"Admin route {admin_route.name or admin_route.route_id} found but has no route_path defined. Skipping.")


        except Exception as e:
            logger.error(f"Error checking/processing admin-defined route: {e}", exc_info=True)
            # Do not re-raise, just fall through to other methods if admin route check fails critically

    # --- Attempt 1: Local OSMnx Graph Routing (if no admin route used) ---
    try:
        if COICT_GRAPH is None or COICT_GRAPH.number_of_nodes() == 0:
            logger.warning("CoICT campus map data is unavailable for local routing. Will try OSRM.")
            raise ValueError("CoICT campus map data is currently unavailable or empty for local routing.")

        logger.info("Attempting route calculation using local CoICT graph.")
        # (The rest of the OSMnx routing logic remains the same as before)
        origin_node = ox.nearest_nodes(COICT_GRAPH, X=origin_point.x, Y=origin_point.y)
        destination_node = ox.nearest_nodes(COICT_GRAPH, X=dest_point.x, Y=dest_point.y)
        logger.info(f"Snapped local graph nodes: Origin {origin_node}, Destination {destination_node}")

        route_node_ids = nx.shortest_path(COICT_GRAPH, source=origin_node, target=destination_node, weight='length')
        distance_meters = nx.shortest_path_length(COICT_GRAPH, source=origin_node, target=destination_node, weight='length')

        route_path_coords = []
        for node_id_val in route_node_ids:
            node_data = COICT_GRAPH.nodes[node_id_val]
            route_path_coords.append((node_data['y'], node_data['x']))

        speed_multipliers = {'walking': 1.4, 'cycling': 4.2, 'driving': 11.1}
        speed = speed_multipliers.get(transport_mode, 1.4)
        duration_seconds = int(distance_meters / speed) if speed > 0 else float('inf')

        logger.info(f"Local graph route: Distance: {distance_meters:.2f}m, Duration: {duration_seconds}s")
        local_steps = []
        if len(route_node_ids) >= 2:
            for i in range(len(route_node_ids) - 1):
                u, v = route_node_ids[i], route_node_ids[i+1]
                edge_data = COICT_GRAPH.get_edge_data(u, v, 0)
                segment_length = edge_data.get('length', 0) if edge_data else 0.0
                segment_duration = int(segment_length / speed) if speed > 0 else float('inf')
                path_description = "path segment"
                street_name_parts = []
                if edge_data:
                    name_attr = edge_data.get('name')
                    if isinstance(name_attr, list): street_name_parts.extend(name_attr)
                    elif isinstance(name_attr, str): street_name_parts.append(name_attr)
                    highway_attr = edge_data.get('highway')
                    if isinstance(highway_attr, list): street_name_parts.extend([h for h in highway_attr if h not in street_name_parts])
                    elif isinstance(highway_attr, str) and highway_attr not in street_name_parts: street_name_parts.append(highway_attr)
                    if street_name_parts: path_description = ", ".join(filter(None, street_name_parts))
                instruction = f"Proceed along {path_description}."
                if i < len(route_node_ids) - 2:
                    next_edge_data = COICT_GRAPH.get_edge_data(route_node_ids[i+1], route_node_ids[i+2], 0)
                    next_street_name_parts = []
                    if next_edge_data:
                        next_name_attr = next_edge_data.get('name')
                        if isinstance(next_name_attr, list): next_street_name_parts.extend(next_name_attr)
                        elif isinstance(next_name_attr, str): next_street_name_parts.append(next_name_attr)
                    if next_street_name_parts and next_street_name_parts[0] != path_description.split(", ")[0]:
                        instruction += f" Then turn onto {', '.join(filter(None,next_street_name_parts))}."
                local_steps.append({'instruction': instruction, 'distance': round(segment_length, 2), 'duration': segment_duration, 'street_name': path_description if street_name_parts else "Unnamed Path"})
            if local_steps: local_steps[-1]['instruction'] += f" towards {dest_name}."

        lrm_route_local = {
            'name': f"Route from {origin_name} to {dest_name} (Campus Graph)",
            'summary': {'totalDistance': round(distance_meters, 2), 'totalTime': duration_seconds},
            'coordinates': route_path_coords,
            'waypoints': [[origin_point.y, origin_point.x], [dest_point.y, dest_point.x]],
            'instructions': [{'text': s['instruction'], 'distance': s['distance'], 'time': s['duration']} for s in local_steps],
            'source_service': 'local_graph'
        }
        logger.info("Successfully calculated route via local CoICT graph.")
        return [lrm_route_local]

    except (ValueError, nx.NetworkXNoPath, Exception) as local_route_error:
        logger.warning(f"Local graph routing failed: {local_route_error}. Attempting OpenRouteService fallback.")
        pass # Fall through to OpenRouteService attempt

    # --- Attempt 2: OpenRouteService Fallback (if no admin route and local graph failed) ---
    logger.info(f"Attempting OpenRouteService fallback for route from '{origin_name}' to '{dest_name}'.")

    ors_api_key = getattr(settings, 'OPENROUTESERVICE_API_KEY', None)
    if not ors_api_key or ors_api_key == 'YOUR_ORS_API_KEY_HERE':
        logger.error("OpenRouteService API key is not configured in settings.")
        raise ValueError("Map service (OpenRouteService) API key not configured.")

    ors_profile_map = {
        'walking': 'foot-walking',
        'cycling': 'cycling-regular',
        'driving': 'driving-car'
    }
    ors_profile = ors_profile_map.get(transport_mode, 'foot-walking')

    headers = {
        'Authorization': ors_api_key,
        'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
        'Content-Type': 'application/json; charset=utf-8'
    }

    # ORS expects coordinates as [longitude, latitude]
    body = {
        'coordinates': [[origin_point.x, origin_point.y], [dest_point.x, dest_point.y]],
        'instructions_format': 'text', # 'html' or 'text'
        'language': 'en', # Specify language for instructions
        'preference': 'fastest', # 'fastest', 'shortest', 'recommended'
        'units': 'm' # 'm' for meters, 'km' for kilometers
    }

    ors_url = f"https://api.openrouteservice.org/v2/directions/{ors_profile}/geojson"

    try:
        response = requests.post(ors_url, json=body, headers=headers, timeout=20)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        ors_data = response.json()

        if ors_data.get('features') and len(ors_data['features']) > 0:
            route_feature = ors_data['features'][0]
            summary = route_feature.get('properties', {}).get('summary', {})
            distance_meters_ors = summary.get('distance', 0.0)  # in meters as per 'units': 'm'
            duration_seconds_ors = summary.get('duration', 0.0)  # in seconds

            # Geometry is GeoJSON LineString, coordinates are [lon, lat]
            geometry_coords = route_feature.get('geometry', {}).get('coordinates', [])
            # Convert to [lat, lon] for consistency with Leaflet Routing Machine
            route_path_coords_ors = [[coord[1], coord[0]] for coord in geometry_coords]

            lrm_instructions_ors = []
            segments = route_feature.get('properties', {}).get('segments', [])
            if segments:
                for segment in segments:
                    for step in segment.get('steps', []):
                        lrm_instructions_ors.append({
                            'text': step.get('instruction', 'Proceed on path'),
                            'distance': round(step.get('distance', 0), 1),  # in meters
                            'time': round(step.get('duration', 0), 1)  # in seconds
                        })

            # If no detailed steps, create a general instruction
            if not lrm_instructions_ors and distance_meters_ors > 0:
                lrm_instructions_ors.append({
                    'text': f"Follow the route to {dest_name}.",
                    'distance': round(distance_meters_ors, 1),
                    'time': round(duration_seconds_ors, 1)
                })


            lrm_route_ors = {
                'name': f"Route from {origin_name} to {dest_name} (via OpenRouteService)",
                'summary': {'totalDistance': round(distance_meters_ors, 2), 'totalTime': round(duration_seconds_ors, 2)},
                'coordinates': route_path_coords_ors,
                'waypoints': [[origin_point.y, origin_point.x], [dest_point.y, dest_point.x]], # Leaflet needs [lat, lon]
                'instructions': lrm_instructions_ors,
                'source_service': 'openrouteservice'
            }
            logger.info(f"Successfully calculated route via OpenRouteService: Distance: {distance_meters_ors:.2f}m")
            return [lrm_route_ors]
        else:
            error_message = "OpenRouteService could not find a route or returned an empty response."
            if ors_data.get('error'):
                error_message = ors_data['error'].get('message', error_message)
            logger.error(f"OpenRouteService routing unsuccessful: {error_message} Response: {ors_data}")
            raise ValueError(f"Map Error: {error_message}")

    except requests.exceptions.Timeout:
        logger.error(f"OpenRouteService request timed out: {ors_url}")
        raise ValueError("Map service (OpenRouteService) request timed out. Please try again.")
    except requests.exceptions.HTTPError as http_err:
        # Attempt to get more specific error message from ORS response
        error_details = ""
        try:
            err_json = http_err.response.json()
            error_details = err_json.get("error", {}).get("message", str(http_err))
        except json.JSONDecodeError:
            error_details = str(http_err)
        logger.error(f"OpenRouteService HTTP error: {error_details} (Status: {http_err.response.status_code}) URL: {ors_url}")
        raise ValueError(f"Map service (OpenRouteService) error: {error_details}")
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenRouteService request failed: {e}")
        raise ValueError(f"Could not connect to map service (OpenRouteService). Please check internet connection and try again.")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Error parsing OpenRouteService response: {e}", exc_info=True)
        raise ValueError("Failed to understand route data from map service (OpenRouteService).")
    except Exception as e:
        logger.error(f"Unexpected error during OpenRouteService routing: {e}", exc_info=True)
        raise ValueError("An unexpected error occurred with the external map service (OpenRouteService).")


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