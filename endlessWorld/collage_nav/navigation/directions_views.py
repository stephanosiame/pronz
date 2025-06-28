from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib.gis.geos import Point
from django.utils import timezone
import json
import logging
import os
from django.conf import settings

from .models import Location, UserLocation, RouteRequest, SMSAlert
from .utils import (
    send_sms,
    calculate_route,
    is_within_coict_boundary # Assuming this is needed by get_directions
)

# Logger instance
logger = logging.getLogger(__name__)

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

            if from_location_id:
                from_location_obj = get_object_or_404(Location, location_id=from_location_id)
                if not is_within_coict_boundary(from_location_obj.coordinates):
                    return JsonResponse({'success': False, 'error': 'Origin location is outside CoICT campus boundary'}, status=400)
            elif from_lat is not None and from_lon is not None:
                from_point = Point(float(from_lon), float(from_lat), srid=4326)
                if not is_within_coict_boundary(from_point):
                    return JsonResponse({'success': False, 'error': 'Origin coordinates are outside CoICT campus boundary'}, status=400)
                from_coords_tuple = (float(from_lat), float(from_lon))
            else:
                last_user_locs = UserLocation.objects.filter(user=request.user).order_by('-timestamp')[:10]
                for last_loc in last_user_locs:
                    if last_loc.location and is_within_coict_boundary(last_loc.location):
                        from_coords_tuple = (last_loc.location.y, last_loc.location.x)
                        break
                if not from_coords_tuple:
                    return JsonResponse({'success': False, 'error': 'No valid origin location within CoICT campus boundary'}, status=400)

            if to_location_id:
                to_location_obj = get_object_or_404(Location, location_id=to_location_id)
                if not is_within_coict_boundary(to_location_obj.coordinates):
                    return JsonResponse({'success': False, 'error': 'Destination location is outside CoICT campus boundary'}, status=400)
            elif to_lat is not None and to_lon is not None:
                to_point = Point(float(to_lon), float(to_lat), srid=4326)
                if not is_within_coict_boundary(to_point):
                    return JsonResponse({'success': False, 'error': 'Destination coordinates are outside CoICT campus boundary'}, status=400)
                to_coords_tuple = (float(to_lat), float(to_lon))
            else:
                return JsonResponse({'success': False, 'error': 'Destination location or coordinates missing'}, status=400)

            route_data_list = []
            try:
                route_data_list = calculate_route(
                    from_location=from_location_obj,
                    to_location=to_location_obj,
                    transport_mode=transport_mode,
                    from_coordinates=from_coords_tuple,
                    to_coordinates=to_coords_tuple
                )
            except ValueError as ve:
                error_message = str(ve)
                logger.error(f"Routing Error in get_directions: {error_message}", exc_info=True)
                if "CoICT campus map data is currently unavailable or empty for local routing" in error_message:
                    user_friendly_message = "Campus-specific map data is missing or not detailed enough for routing."
                    return JsonResponse({'success': False, 'error': user_friendly_message}, status=503)
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
                        user=request.user, from_location=from_location_obj, to_location=to_location_obj,
                        transport_mode=transport_mode, timestamp=timezone.now()
                    )
                    if request.user.notifications_enabled and actual_route_info.get('summary', {}).get('totalDistance', 0) > 500:
                        distance_km = actual_route_info.get('summary', {}).get('totalDistance',0) / 1000
                        time_min = actual_route_info.get('summary', {}).get('totalTime',0) / 60
                        message_sms = f"Campus route to {to_location_obj.name} is {distance_km:.1f}km. Est. time: {time_min:.0f} min."
                        send_sms(request.user.phone_number, message_sms)
                        SMSAlert.objects.create(user=request.user, message=message_sms, alert_type='navigation', is_sent=True, sent_at=timezone.now())
                return JsonResponse(response_payload)
            else:
                logger.error("get_directions: calculate_route did not return valid route data or an exception.")
                return JsonResponse({'success': False, 'error': 'Failed to calculate route due to an unexpected internal issue.'}, status=500)

        except Location.DoesNotExist:
            logger.warning(f"Location.DoesNotExist in get_directions for user {request.user.id}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Origin or destination location not found within campus boundary.'}, status=404)
        except ValueError as ve:
            logger.warning(f"ValueError before calculate_route in get_directions: {str(ve)}")
            return JsonResponse({'success': False, 'error': str(ve)}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error in get_directions for user {request.user.id}: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'An unexpected server error occurred. Please try again.'}, status=500)

    return JsonResponse({'success': False, 'error': 'Invalid request method. Please use POST.'}, status=405)

@login_required
def get_campus_directions_view(request):
    from_route_query = request.GET.get('from_route', '').strip().lower()
    to_route_query = request.GET.get('to_route', '').strip().lower()

    if not from_route_query and not to_route_query:
        return JsonResponse({'route': None, 'message': 'Please provide at least a starting or ending route.'}, status=400)

    target_query, descriptive_query_for_message, message_prefix = None, "", ""

    if from_route_query and not to_route_query:
        target_query, descriptive_query_for_message = from_route_query, request.GET.get('from_route', '')
        message_prefix = f"Displaying route for '{descriptive_query_for_message}'"
    elif not from_route_query and to_route_query:
        target_query, descriptive_query_for_message = to_route_query, request.GET.get('to_route', '')
        message_prefix = f"Displaying route for '{descriptive_query_for_message}'"
    elif from_route_query == to_route_query:
        target_query, descriptive_query_for_message = from_route_query, request.GET.get('from_route', '')
        message_prefix = f"Route from '{descriptive_query_for_message}' to '{request.GET.get('to_route', '')}' (same route)"
    else:
        return JsonResponse({'route': None, 'message': "Multi-segment routing not yet supported."}, status=400)

    file_path = os.path.join(settings.BASE_DIR, 'navigation', 'data', 'coict_routes.geojson')
    if not os.path.exists(file_path):
        logger.error(f"GeoJSON file not found: {file_path}")
        return JsonResponse({'route': None, 'message': 'Route data file not found.'}, status=500)
    try:
        with open(file_path, 'r') as f: geojson_data = json.load(f)
        found_route_feature = None
        for feature in geojson_data.get('features', []):
            props = feature.get('properties', {})
            area, desc = str(props.get('area', '')).lower(), str(props.get('description', '')).lower()
            if target_query == area or target_query == desc or target_query == desc.replace("route ", "") or \
               (target_query.isdigit() and area.isdigit() and int(target_query) == int(area)):
                found_route_feature = feature; break
        if found_route_feature:
            if request.user.is_authenticated and getattr(request.user, 'notifications_enabled', False) and getattr(request.user, 'phone_number', None):
                route_name = found_route_feature.get("properties", {}).get("description", "selected route")
                sms_text = f"CoICT Nav: Details for {route_name} ready. {message_prefix}."[:160]
                sent = send_sms(request.user.phone_number, sms_text)
                SMSAlert.objects.create(user=request.user, message=sms_text, alert_type='campus_direction', is_sent=sent, sent_at=timezone.now() if sent else None)
            return JsonResponse({'route': found_route_feature, 'message': f"{message_prefix}."}, status=200)
        return JsonResponse({'route': None, 'message': f"Route '{descriptive_query_for_message}' not found."}, status=404)
    except json.JSONDecodeError:
        logger.error(f"Decode error: {file_path}"); return JsonResponse({'route': None, 'message': 'Route data error.'}, status=500)
    except Exception as e:
        logger.error(f"Campus directions error: {e}", exc_info=True); return JsonResponse({'route': None, 'message': 'Server error.'}, status=500)

@login_required
def page_get_campus_directions(request):
    """Renders the HTML page for getting campus directions."""
    return render(request, 'navigation/directions_campus_form.html')
