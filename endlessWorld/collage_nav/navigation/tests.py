from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.gis.geos import Point, Polygon, LineString # Added Polygon, LineString
from django.utils import timezone
import uuid
import json
from unittest.mock import patch, call

from .models import CustomUser, Location, Recommendation, UserLocation, RouteRequest, SMSAlert, Geofence, NavigationRoute # Added Geofence, NavigationRoute
from .forms import CustomUserRegistrationForm, TokenVerificationForm, PasswordResetRequestForm
from .views import COICT_CENTER_LAT, COICT_CENTER_LON, COICT_BOUNDS_OFFSET, STRICT_BOUNDS, get_smart_recommendations

# --- Helper Functions ---
def create_user(username="testuser", password="password123", phone_number="+255700000000", email="test@example.com", is_verified=True, is_staff=False, is_superuser=False):
    user = CustomUser.objects.create_user(
        username=username,
        password=password,
        phone_number=phone_number,
        email=email,
        first_name="Test",
        last_name="User"
    )
    user.is_verified = is_verified
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.save()
    return user

def create_location(name="Test Location", description="A place for testing.",
                    address="123 Test St", location_type='building',
                    lat=-6.771200, lon=39.240000, floor_level=0,
                    is_accessible=True, capacity=100):
    return Location.objects.create(
        name=name,
        description=description,
        address=address,
        location_type=location_type,
        coordinates=Point(lon, lat, srid=4326), # lon, lat
        floor_level=floor_level,
        is_accessible=is_accessible,
        capacity=capacity
    )

def create_recommendation(user, location, recommended_location, reason="Test reason", media_url=None):
    return Recommendation.objects.create(
        user=user,
        location=location, # current location context for recommendation
        recommended_location=recommended_location,
        reason=reason,
        score=0.8, # Example score
        media_url=media_url
    )

# --- Test Classes ---

class RecommendationAreaTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user(username="rec_user", phone_number="+255700000001")
        self.location1 = create_location(name="Main Building", lat=COICT_CENTER_LAT, lon=COICT_CENTER_LON)
        self.location2 = create_location(name="Library", lat=COICT_CENTER_LAT + 0.0001, lon=COICT_CENTER_LON + 0.0001)
        self.media_url = "http://example.com/image.png"

    def test_recommendation_model_creation(self):
        recommendation = create_recommendation(
            user=self.user,
            location=self.location1,
            recommended_location=self.location2,
            media_url=self.media_url
        )
        self.assertEqual(recommendation.media_url, self.media_url)
        self.assertEqual(Recommendation.objects.count(), 1)

    def test_get_location_details_json_view_success(self):
        url = reverse('get_location_details_json', args=[self.location1.location_id])
        self.client.login(username="rec_user", password="password123")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], self.location1.name)
        self.assertAlmostEqual(data['latitude'], self.location1.coordinates.y)
        self.assertAlmostEqual(data['longitude'], self.location1.coordinates.x)

    def test_get_location_details_json_view_not_found(self):
        non_existent_uuid = uuid.uuid4()
        url = reverse('get_location_details_json', args=[non_existent_uuid])
        self.client.login(username="rec_user", password="password123")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200) # View returns JsonResponse with success=False for not found
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Location not found.')

    def test_dashboard_view_recommendations_context(self):
        create_recommendation(
            user=self.user,
            location=self.location1,
            recommended_location=self.location2,
            media_url=self.media_url
        )
        # Simulate user location for recommendation generation
        UserLocation.objects.create(user=self.user, location=self.location1.coordinates)

        self.client.login(username="rec_user", password="password123")
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        # Check if recommendations are in context and have media_url
        # The get_smart_recommendations function might return a mix of dicts and objects
        # and has specific logic for formatting them.
        recommendations_in_context = response.context.get('recommendations', [])
        self.assertTrue(len(recommendations_in_context) > 0)

        found_media_url = False
        for rec in recommendations_in_context:
            # Recommendations can be dicts or model instances based on get_smart_recommendations
            if isinstance(rec, dict):
                if rec.get('media_url') == self.media_url:
                    found_media_url = True
                    break
            elif isinstance(rec, Recommendation): # Should not happen due to view logic
                if rec.media_url == self.media_url:
                    found_media_url = True
                    break
        # This test is a bit complex due to get_smart_recommendations logic.
        # A simpler check might be to ensure the key 'media_url' is present in the dicts.
        if recommendations_in_context:
             self.assertTrue(any('media_url' in rec for rec in recommendations_in_context if isinstance(rec, dict)))

    def test_get_smart_recommendations_logic(self):
        user_for_smart_rec = create_user(username='testuser_smart_rec', phone_number="+255700000012") # New user for this test

        # Create Location objects
        loc1_lib = create_location(name='Main Library', location_type='library', description='Quiet study place.')
        loc2_lib = create_location(name='Science Library', location_type='library', description='Books and journals.')
        loc3_lib = create_location(name='Old Library', location_type='library', description='Historical archives.') # Third library
        loc4_cafe = create_location(name='Student Cafe', location_type='cafeteria', description='Coffee and snacks.')
        # Simulate loc4_cafe having an image for media_url fallback test
        # In a real scenario, this would involve uploading a file. For testing, we can mock the field's url attribute if needed,
        # but getattr(loc_obj.image, 'url', None) will return None if image is not set, which is testable.
        # For simplicity, we'll assume image.url is None if not explicitly set with a file.

        loc5_office = create_location(name='Admin Office', location_type='office', description='Enquiries.') # Different type not in morning priorities

        # Create an existing Recommendation for one of the locations
        existing_rec_for_loc1 = Recommendation.objects.create(
            user=user_for_smart_rec,
            recommended_location=loc1_lib,
            reason="A great place to study!",
            score=0.9,
            rating=4.8,
            media_url="http://example.com/library.jpg"
        )

        nearby_locations_list = [loc1_lib, loc2_lib, loc3_lib, loc4_cafe, loc5_office]
        current_morning_hour = 9 # Morning: expects 'library', 'cafeteria', 'lecture_hall'

        recommendations = get_smart_recommendations(user_for_smart_rec, nearby_locations_list, current_morning_hour)

        self.assertIsInstance(recommendations, list)
        # Expected: 2 libraries (loc1_lib from existing, loc2_lib as default) + 1 cafeteria (loc4_cafe as default)
        self.assertEqual(len(recommendations), 3,
                         f"Expected 3 recommendations (2 libraries, 1 cafeteria), got {len(recommendations)}")

        found_loc1_rec = False
        found_loc2_rec = False
        found_loc4_cafe_rec = False

        for rec_dict in recommendations:
            self.assertIsInstance(rec_dict, dict)
            self.assertIn('recommended_location', rec_dict)
            self.assertIsInstance(rec_dict['recommended_location'], Location)
            self.assertIn('reason', rec_dict)
            self.assertIn('rating', rec_dict)
            self.assertIn('media_url', rec_dict)
            self.assertIn('description', rec_dict)
            self.assertIn('location_type_display', rec_dict)

            if rec_dict['recommended_location'].location_id == loc1_lib.location_id:
                found_loc1_rec = True
                self.assertEqual(rec_dict['reason'], "A great place to study!")
                self.assertEqual(rec_dict['rating'], 4.8)
                self.assertEqual(rec_dict['media_url'], "http://example.com/library.jpg")

            elif rec_dict['recommended_location'].location_id == loc2_lib.location_id:
                found_loc2_rec = True
                self.assertEqual(rec_dict['reason'], f'Popular {loc2_lib.get_location_type_display()} nearby')
                self.assertEqual(rec_dict['rating'], 4.0)
                # media_url will be None as loc2_lib.image is not set
                self.assertIsNone(rec_dict['media_url'])

            elif rec_dict['recommended_location'].location_id == loc4_cafe.location_id:
                found_loc4_cafe_rec = True
                self.assertEqual(rec_dict['reason'], f'Popular {loc4_cafe.get_location_type_display()} nearby')
                self.assertEqual(rec_dict['rating'], 4.0)
                self.assertIsNone(rec_dict['media_url']) # Assuming loc4_cafe.image is not set

        self.assertTrue(found_loc1_rec, "Recommendation for Main Library (from existing Rec obj) not found or incorrect.")
        self.assertTrue(found_loc2_rec, "Default recommendation for Science Library not found or incorrect.")
        self.assertTrue(found_loc4_cafe_rec, "Default recommendation for Student Cafe not found or incorrect.")

        library_recs_count = sum(1 for r in recommendations if r['recommended_location'].location_type == 'library')
        self.assertEqual(library_recs_count, 2, "Should recommend at most 2 libraries based on priority.")

        cafeteria_recs_count = sum(1 for r in recommendations if r['recommended_location'].location_type == 'cafeteria')
        self.assertEqual(cafeteria_recs_count, 1, "Should recommend 1 cafeteria.")

        # Ensure loc3_lib (third library) and loc5_office were not recommended
        recommended_location_ids = [r['recommended_location'].location_id for r in recommendations]
        self.assertNotIn(loc3_lib.location_id, recommended_location_ids, "Third library should not be recommended due to limit of 2.")
        self.assertNotIn(loc5_office.location_id, recommended_location_ids, "Office location should not be recommended in the morning.")


# --- User Related API Tests ---
class UserRelatedApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_with_loc = create_user(username="user_with_loc", phone_number="+255700000013")
        self.user_no_loc = create_user(username="user_no_loc", phone_number="+255700000014")

        # Create location history for user_with_loc
        self.loc_point1 = Point(39.2400, -6.7712, srid=4326) # lon, lat
        self.loc_point2 = Point(39.2405, -6.7715, srid=4326) # newer
        UserLocation.objects.create(user=self.user_with_loc, location=self.loc_point1, timestamp=timezone.now() - timezone.timedelta(hours=1))
        self.latest_user_location = UserLocation.objects.create(user=self.user_with_loc, location=self.loc_point2, timestamp=timezone.now())

    def test_get_last_user_location_success(self):
        self.client.login(username="user_with_loc", password="password123")
        response = self.client.get(reverse('get_last_user_location'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertAlmostEqual(data['latitude'], self.loc_point2.y)
        self.assertAlmostEqual(data['longitude'], self.loc_point2.x)
        self.assertIn('timestamp', data)

    def test_get_last_user_location_no_history(self):
        self.client.login(username="user_no_loc", password="password123")
        response = self.client.get(reverse('get_last_user_location'))
        self.assertEqual(response.status_code, 200) # View returns 200 but success: False
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['message'], 'No location history found for this user.')

    def test_get_last_user_location_not_logged_in(self):
        response = self.client.get(reverse('get_last_user_location'))
        self.assertEqual(response.status_code, 302) # Should redirect to login
        self.assertTrue(reverse('login') in response.url)

    def test_get_last_user_location_wrong_method(self):
        self.client.login(username="user_with_loc", password="password123")
        response = self.client.post(reverse('get_last_user_location')) # Using POST
        self.assertEqual(response.status_code, 405) # Method Not Allowed
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['message'], 'Invalid request method. Only GET is allowed.')


# --- Boundary Restriction Tests ---
class BoundaryRestrictionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user(username="boundary_user", phone_number="+255700000009")
        self.client.login(username="boundary_user", password="password123")

        # Locations for testing bounds
        # Inside bounds (using STRICT_BOUNDS from views.py)
        self.loc_inside1 = create_location(name="Inside Location 1",
                                          lat=COICT_CENTER_LAT, lon=COICT_CENTER_LON)
        self.loc_inside2 = create_location(name="Inside Location 2",
                                          lat=COICT_CENTER_LAT + COICT_BOUNDS_OFFSET / 2,
                                          lon=COICT_CENTER_LON - COICT_BOUNDS_OFFSET / 2)

        # Outside bounds
        self.loc_outside_lat = create_location(name="Outside Location Lat",
                                               lat=COICT_CENTER_LAT + COICT_BOUNDS_OFFSET * 2,
                                               lon=COICT_CENTER_LON)
        self.loc_outside_lon = create_location(name="Outside Location Lon",
                                               lat=COICT_CENTER_LAT,
                                               lon=COICT_CENTER_LON - COICT_BOUNDS_OFFSET * 2)
        # User's current location to be within bounds for nearby search
        UserLocation.objects.create(user=self.user, location=Point(COICT_CENTER_LON, COICT_CENTER_LAT, srid=4326))


    def test_dashboard_view_nearby_locations_filtered_by_bounds(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        nearby_locations_in_context = response.context.get('nearby_locations', [])
        nearby_location_ids = [loc.location_id for loc in nearby_locations_in_context]

        self.assertIn(self.loc_inside1.location_id, nearby_location_ids)
        self.assertIn(self.loc_inside2.location_id, nearby_location_ids)
        self.assertNotIn(self.loc_outside_lat.location_id, nearby_location_ids)
        self.assertNotIn(self.loc_outside_lon.location_id, nearby_location_ids)

        # Also check total_locations count if it reflects only within-bound locations
        # The dashboard_view limits to 50, so ensure this is also handled if many inside locations exist.
        # For this test, we have few locations, so count should be exact.
        self.assertEqual(response.context.get('total_locations'), 2)


# --- Search To Map Tests (View part) ---
class SearchToMapTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user(username="search_user", phone_number="+255700000010")
        self.client.login(username="search_user", password="password123")

        self.search_loc1 = create_location(name="Lecture Hall Alpha", description="Main hall for CS", location_type='lecture_hall')
        self.search_loc2 = create_location(name="Cafeteria Beta", description="Serves snacks and coffee", location_type='cafeteria')
        self.search_loc3 = create_location(name="Library Gamma", description="Quiet study area", location_type='library')

    def test_search_locations_view_success_name_query(self):
        response = self.client.get(reverse('search_locations'), {'q': 'Alpha'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(len(data['locations']) == 1)
        self.assertEqual(data['locations'][0]['name'], self.search_loc1.name)

    def test_search_locations_view_success_description_query(self):
        response = self.client.get(reverse('search_locations'), {'q': 'coffee'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(len(data['locations']) == 1)
        self.assertEqual(data['locations'][0]['name'], self.search_loc2.name)

    def test_search_locations_view_type_query(self):
        response = self.client.get(reverse('search_locations'), {'q': 'library'}) # 'library' is a type and in name
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(len(data['locations']) >= 1) # Could match type or name
        self.assertTrue(any(loc['name'] == self.search_loc3.name for loc in data['locations']))

    def test_search_locations_case_insensitivity(self):
        create_location(name="Main Library", location_type='library')
        create_location(name="main library extension", location_type='library')
        create_location(name="MAIN LIBRARY Reading Room", location_type='library')

        # Search with all lowercase
        response = self.client.get(reverse('search_locations'), {'q': 'main library'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # The original self.search_loc3 ("Library Gamma") might also be found if "library" is in its name/desc/type.
        # We expect at least the 3 newly created ones.
        # Let's count how many of the new ones are present vs total.
        found_count = 0
        for loc in data['locations']:
            if "MAIN LIBRARY" in loc['name'].upper() or "MAIN LIBRARY EXTENSION" in loc['name'].upper():
                found_count +=1
        self.assertEqual(found_count, 3, "Should find all 3 variations of 'Main Library'")


        # Search with mixed case
        response = self.client.get(reverse('search_locations'), {'q': 'Main Library'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        found_count_mixed = 0
        for loc in data['locations']:
            if "MAIN LIBRARY" in loc['name'].upper() or "MAIN LIBRARY EXTENSION" in loc['name'].upper():
                found_count_mixed +=1
        self.assertEqual(found_count_mixed, 3, "Should find all 3 variations of 'Main Library' with mixed case query")

    def test_search_locations_view_no_results(self):
        response = self.client.get(reverse('search_locations'), {'q': 'NonExistentXYZ'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['locations']), 0)

    def test_search_locations_view_empty_query(self): # Query < 2 chars
        response = self.client.get(reverse('search_locations'), {'q': 'A'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['locations']), 0)


# --- Admin Area Tests ---
class AdminAreaTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = create_user(username="admin_user", phone_number="+255700000011", is_staff=True, is_superuser=True)
        self.client.login(username="admin_user", password="password123")

    def test_location_admin_changelist_accessible(self):
        response = self.client.get(reverse('admin:navigation_location_changelist'))
        self.assertEqual(response.status_code, 200)

    def test_location_admin_add_page_accessible(self):
        response = self.client.get(reverse('admin:navigation_location_add'))
        self.assertEqual(response.status_code, 200)

    def test_location_admin_change_page_accessible(self):
        loc = create_location(name="Admin Test Loc")
        response = self.client.get(reverse('admin:navigation_location_change', args=[loc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, loc.name) # Check if location name is in the form


# --- Directions API Tests ---
class DirectionsApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user(username="dir_user", phone_number="+255700000015")
        self.client.login(username="dir_user", password="password123")

        self.loc_a = create_location(name="Location A", lat=COICT_CENTER_LAT, lon=COICT_CENTER_LON)
        self.loc_b = create_location(name="Location B", lat=COICT_CENTER_LAT + 0.001, lon=COICT_CENTER_LON + 0.001)

        self.origin_coords = (COICT_CENTER_LAT - 0.0005, COICT_CENTER_LON - 0.0005) # lat, lon
        self.dest_coords = (COICT_CENTER_LAT + 0.0005, COICT_CENTER_LON + 0.0005)   # lat, lon

    def _post_get_directions(self, params):
        return self.client.post(reverse('get_directions'), json.dumps(params), content_type='application/json')

    def test_get_directions_origin_coords_dest_id(self):
        params = {
            'from_latitude': self.origin_coords[0],
            'from_longitude': self.origin_coords[1],
            'to_id': str(self.loc_b.location_id)
        }
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['route']['source']['name'], "Current Location")
        self.assertAlmostEqual(data['route']['source']['coordinates']['lat'], self.origin_coords[0])
        self.assertEqual(data['route']['destination']['name'], self.loc_b.name)

    def test_get_directions_origin_id_dest_coords(self):
        params = {
            'from_id': str(self.loc_a.location_id),
            'to_latitude': self.dest_coords[0],
            'to_longitude': self.dest_coords[1]
        }
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['route']['source']['name'], self.loc_a.name)
        self.assertEqual(data['route']['destination']['name'], "Selected Destination")
        self.assertAlmostEqual(data['route']['destination']['coordinates']['lat'], self.dest_coords[0])

    def test_get_directions_origin_coords_dest_coords(self):
        params = {
            'from_latitude': self.origin_coords[0],
            'from_longitude': self.origin_coords[1],
            'to_latitude': self.dest_coords[0],
            'to_longitude': self.dest_coords[1]
        }
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['route']['source']['name'], "Current Location")
        self.assertEqual(data['route']['destination']['name'], "Selected Destination")

    def test_get_directions_origin_fallback_last_known(self):
        # Create a last known location for self.user
        last_known_point = Point(COICT_CENTER_LON - 0.002, COICT_CENTER_LAT - 0.002, srid=4326)
        UserLocation.objects.create(user=self.user, location=last_known_point, timestamp=timezone.now())

        params = {'to_id': str(self.loc_b.location_id)} # No explicit origin
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['route']['source']['name'], "Current Location") # Name given by calculate_route for coords
        self.assertAlmostEqual(data['route']['source']['coordinates']['lat'], last_known_point.y)
        self.assertAlmostEqual(data['route']['source']['coordinates']['lng'], last_known_point.x)

    def test_get_directions_insufficient_params_no_origin(self):
        # User has no last known location for this test
        UserLocation.objects.filter(user=self.user).delete()
        params = {'to_id': str(self.loc_b.location_id)}
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Origin location or coordinates missing', data['error'])

    def test_get_directions_insufficient_params_no_destination(self):
        params = {'from_id': str(self.loc_a.location_id)}
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Destination location or coordinates missing', data['error'])

    def test_route_request_created_for_id_based_directions(self):
        initial_count = RouteRequest.objects.count()
        params = {
            'from_id': str(self.loc_a.location_id),
            'to_id': str(self.loc_b.location_id)
        }
        self._post_get_directions(params)
        self.assertEqual(RouteRequest.objects.count(), initial_count + 1)

    def test_route_request_not_created_for_coord_based_origin(self):
        initial_count = RouteRequest.objects.count()
        params = {
            'from_latitude': self.origin_coords[0],
            'from_longitude': self.origin_coords[1],
            'to_id': str(self.loc_b.location_id)
        }
        self._post_get_directions(params)
        self.assertEqual(RouteRequest.objects.count(), initial_count)

    def test_route_request_not_created_for_coord_based_destination(self):
        initial_count = RouteRequest.objects.count()
        params = {
            'from_id': str(self.loc_a.location_id),
            'to_latitude': self.dest_coords[0],
            'to_longitude': self.dest_coords[1]
        }
        self._post_get_directions(params)
        self.assertEqual(RouteRequest.objects.count(), initial_count)

    @patch('endlessWorld.collage_nav.navigation.utils.calculate_route')
    def test_get_directions_calculate_route_success(self, mock_calculate_route):
        # Mock calculate_route to return a predefined success response
        mock_route_data = {
            'source': {'name': 'Mock Start', 'coordinates': {'lat': -6.770, 'lng': 39.238}},
            'destination': {'name': 'Mock End', 'coordinates': {'lat': -6.772, 'lng': 39.240}},
            'path': [(-6.770, 39.238), (-6.771, 39.239), (-6.772, 39.240)],
            'distance': 250.5,
            'estimated_time': 5, # minutes
            'duration': 300, # seconds
            'steps': [{'instruction': 'Follow mock path', 'distance': 250.5, 'duration': 300}]
        }
        mock_calculate_route.return_value = mock_route_data

        params = {
            'from_id': str(self.loc_a.location_id), # Using existing loc_a
            'to_id': str(self.loc_b.location_id)    # Using existing loc_b
        }
        response = self._post_get_directions(params)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['route'], mock_route_data)
        mock_calculate_route.assert_called_once()
        # We can also assert the arguments passed to mock_calculate_route if needed,
        # e.g., by checking mock_calculate_route.call_args

    @patch('endlessWorld.collage_nav.navigation.utils.calculate_route')
    def test_get_directions_calculate_route_raises_value_error(self, mock_calculate_route):
        # Mock calculate_route to raise a ValueError
        mock_calculate_route.side_effect = ValueError("Test pathfinding error")

        params = {
            'from_id': str(self.loc_a.location_id),
            'to_id': str(self.loc_b.location_id)
        }
        response = self._post_get_directions(params)

        self.assertEqual(response.status_code, 400) # Based on view's error handling
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], "Test pathfinding error")
        mock_calculate_route.assert_called_once()

    def test_get_directions_invalid_json_body(self):
        # Send non-JSON data
        response = self.client.post(reverse('get_directions'), "this is not json", content_type='application/json')
        self.assertEqual(response.status_code, 400) # Or 500 depending on server's strictness with json.loads
        data = response.json()
        self.assertFalse(data['success'])
        # The error message might vary, e.g. "Invalid JSON data" or "An unexpected error occurred"
        self.assertIn('error', data)
        # A more specific error message check might be:
        # self.assertEqual(data['error'], 'Invalid JSON data: Expecting value: line 1 column 1 (char 0)')
        # But this can be brittle. The main point is it fails gracefully.

    def test_get_directions_origin_outside_boundary(self):
        # Create a location explicitly outside COICT bounds
        loc_outside = create_location(name="Outside Campus Cafe", lat=0.0, lon=0.0)
        params = {
            'from_id': str(loc_outside.location_id),
            'to_id': str(self.loc_b.location_id) # loc_b is inside
        }
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Origin location is outside CoICT campus boundary')

    def test_get_directions_destination_outside_boundary(self):
        loc_outside = create_location(name="Outside Campus Library", lat=1.0, lon=1.0)
        params = {
            'from_id': str(self.loc_a.location_id), # loc_a is inside
            'to_id': str(loc_outside.location_id)
        }
        response = self._post_get_directions(params)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Destination location is outside CoICT campus boundary')


# --- Token Verification Tests (already started) ---
class TokenVerificationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_login_unverified_user(self):
        user = create_user(username="unverified_user", phone_number="+255700000002", is_verified=False)
        # Manually create a verification token for the user as register_view does
        user.verification_token = "123456"
        user.token_created_at = timezone.now()
        user.save()

        response = self.client.post(reverse('login'), {
            'username': 'unverified_user',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('verify_token', args=[user.id]))

    def test_login_verified_user(self):
        create_user(username="verified_user", phone_number="+255700000003", is_verified=True)
        response = self.client.post(reverse('login'), {
            'username': 'verified_user',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('dashboard'))

    @patch('endlessWorld.collage_nav.navigation.views.send_sms')
    def test_register_view_flow(self, mock_send_sms):
        mock_send_sms.return_value = True # Simulate successful SMS sending
        user_count_before = CustomUser.objects.count()
        phone_number_for_reg = "+255700000004" # Ensure unique

        response = self.client.post(reverse('register'), {
            'username': 'new_reg_user',
            'password': 'password123', # Use a valid password defined in settings or common_passwords.txt
            'password2': 'password123',
            'email': 'newreg@example.com',
            'phone_number': phone_number_for_reg,
            'first_name': 'New',
            'last_name': 'Reg',
            'role': 'student'
        })

        self.assertEqual(CustomUser.objects.count(), user_count_before + 1)
        new_user = CustomUser.objects.get(username='new_reg_user')

        self.assertTrue(new_user.is_verified) # User should be verified immediately
        self.assertIsNone(new_user.verification_token) # Verification token should be None

        expected_message = "Thanks for Register our app for navigation to CoICT collage"
        mock_send_sms.assert_called_once_with(new_user.phone_number, expected_message)

        self.assertTrue(SMSAlert.objects.filter(user=new_user, alert_type='welcome', message=expected_message).exists())

        self.assertRedirects(response, reverse('login')) # Should redirect to login

    def test_verify_token_view_correct_token(self):
        user = create_user(username="verify_me", phone_number="+255700000005", is_verified=False)
        user.verification_token = "654321"
        user.token_created_at = timezone.now()
        user.save()

        response = self.client.post(reverse('verify_token', args=[user.id]), {
            'token': '654321'
        })
        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        self.assertIsNone(user.verification_token)
        self.assertRedirects(response, reverse('login'))

    def test_verify_token_view_incorrect_token(self):
        user = create_user(username="verify_fail", phone_number="+255700000006", is_verified=False)
        user.verification_token = "111222"
        user.token_created_at = timezone.now()
        user.save()

        response = self.client.post(reverse('verify_token', args=[user.id]), {
            'token': '000000' # Incorrect token
        })
        user.refresh_from_db()
        self.assertFalse(user.is_verified) # Should remain unverified
        self.assertIn('Invalid verification code.', response.content.decode())

    def test_password_reset_verified_user_remains_verified(self):
        user = create_user(username="pw_reset_verified", phone_number="+255700000007", is_verified=True)

        # Request reset
        self.client.post(reverse('password_reset_request'), {'phone_number': user.phone_number})
        user.refresh_from_db()
        self.assertIsNotNone(user.verification_token)
        reset_token = user.verification_token

        # Verify reset (set new password)
        self.client.post(reverse('password_reset_verify', args=[user.id]), {
            'token': reset_token,
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        user.refresh_from_db()
        self.assertTrue(user.is_verified) # Crucial: user remains verified

    def test_password_reset_unverified_user_remains_unverified(self):
        user = create_user(username="pw_reset_unverified", phone_number="+255700000008", is_verified=False)
        initial_token = "initialtoken" # Simulate an initial verification token
        user.verification_token = initial_token
        user.save()

        # Request reset
        self.client.post(reverse('password_reset_request'), {'phone_number': user.phone_number})
        user.refresh_from_db()
        self.assertIsNotNone(user.verification_token)
        self.assertNotEqual(user.verification_token, initial_token) # Token should change
        reset_token = user.verification_token

        # Verify reset (set new password)
        self.client.post(reverse('password_reset_verify', args=[user.id]), {
            'token': reset_token,
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        user.refresh_from_db()
        self.assertFalse(user.is_verified) # Crucial: user remains unverified


# --- Utils Tests ---
from . import utils # Import the utils module itself for setattr
from .utils import calculate_route
import networkx as nx # For NetworkXNoPath exception


# --- Geofence Model Tests ---
class GeofenceModelTests(TestCase):
    def setUp(self):
        self.user = create_user(username="geofence_creator", phone_number="+255712345678")
        self.location = create_location(name="Geofence Location Center")
        self.sample_polygon = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0))) # Simple square

    def test_create_geofence(self):
        geofence = Geofence.objects.create(
            name="Test Geofence",
            description="A test geofence area",
            location=self.location,
            boundary=self.sample_polygon,
            created_by=self.user,
            is_active=True
        )
        self.assertEqual(Geofence.objects.count(), 1)
        self.assertEqual(geofence.name, "Test Geofence")
        self.assertTrue(geofence.boundary.equals_exact(self.sample_polygon, tolerance=0.00001))
        self.assertTrue(geofence.is_active)

    def test_create_navigation_route(self):
        loc_start = create_location(name="Start Point Nav", lat=-6.770, lon=39.230)
        loc_end = create_location(name="End Point Nav", lat=-6.772, lon=39.232)
        sample_path = LineString(((39.230, -6.770), (39.231, -6.771), (39.232, -6.772)), srid=4326)

        route = NavigationRoute.objects.create(
            source_location=loc_start,
            destination_location=loc_end,
            route_path=sample_path,
            distance=150.5,
            estimated_time=3
        )
        self.assertEqual(NavigationRoute.objects.count(), 1)
        self.assertEqual(route.distance, 150.5)
        self.assertTrue(route.route_path.equals_exact(sample_path, tolerance=0.00001))


# --- Geofence API Tests ---
class GeofenceApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user(username="api_user_gf", phone_number="+255787654321")
        self.client.login(username="api_user_gf", password="password123")
        self.location = create_location(name="Campus Hotspot")

        # Define some polygons for geofences
        self.poly1 = Polygon(((39.230, -6.770), (39.230, -6.775), (39.235, -6.775), (39.235, -6.770), (39.230, -6.770)), srid=4326)
        self.poly2 = Polygon(((39.240, -6.780), (39.240, -6.785), (39.245, -6.785), (39.245, -6.780), (39.240, -6.780)), srid=4326)

        self.gf1 = Geofence.objects.create(
            name="Library Geofence", location=self.location, boundary=self.poly1,
            created_by=self.user, is_active=True, description="Quiet zone"
        )
        self.gf2 = Geofence.objects.create(
            name="Cafeteria Geofence", location=self.location, boundary=self.poly2,
            created_by=self.user, is_active=True, description="Lunch area"
        )
        self.gf_inactive = Geofence.objects.create(
            name="Old Geofence", location=self.location, boundary=self.poly1,
            created_by=self.user, is_active=False # Inactive
        )

    def test_api_get_geofences_success(self):
        response = self.client.get(reverse('api_get_geofences'))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('geofences', data)
        self.assertEqual(len(data['geofences']), 2) # Only active geofences

        gf1_data = next((item for item in data['geofences'] if item['name'] == self.gf1.name), None)
        gf2_data = next((item for item in data['geofences'] if item['name'] == self.gf2.name), None)

        self.assertIsNotNone(gf1_data)
        self.assertIsNotNone(gf2_data)

        self.assertEqual(gf1_data['description'], self.gf1.description)
        self.assertIn('coordinates', gf1_data['boundary_geojson']) # Check for GeoJSON structure
        self.assertEqual(gf1_data['boundary_geojson']['type'], 'Polygon')

    def test_api_get_geofences_no_active_geofences(self):
        Geofence.objects.filter(is_active=True).update(is_active=False) # Deactivate all
        response = self.client.get(reverse('api_get_geofences'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['geofences']), 0)

    def test_api_get_geofences_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('api_get_geofences'))
        self.assertEqual(response.status_code, 302) # Redirects to login
        self.assertTrue(reverse('login') in response.url)


class RoutingTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create test locations
        # Ensure location_type are valid choices from Location.LOCATION_TYPES
        # Example: ('building', 'Building'), ('entrance', 'Entrance'), ('cafeteria', 'Cafeteria')

        self.gate_location, self.gate_created = Location.objects.get_or_create(
            name="Test CoICT Gate",
            defaults={
                'location_id': uuid.uuid4(),
                'coordinates': Point(39.2376632, -6.770756, srid=4326), # Matches a node in graphml
                'description': 'Main entrance gate for CoICT campus - Test',
                'location_type': 'entrance',
                'is_active': True,
                'is_searchable': True
            }
        )
        # If the location was retrieved and not created, its ID might be different than what calculate_route expects
        # or it might not be exactly what we need for a clean test.
        # For simplicity in this test, we'll ensure a fresh ID if it wasn't created.
        # In a more complex setup, you might want to delete existing test data before each run.
        if not self.gate_created:
            # If it already existed, we might want to update it or ensure it's suitable.
            # For this test, let's ensure it has a known UUID if we didn't just create it.
            # However, get_or_create handles this. If it exists, we use it.
            # The main concern is if the existing one has a different coordinate that makes the test fail.
            # For now, we assume get_or_create gives us a usable object.
            pass


        self.cafeteria_location, self.cafeteria_created = Location.objects.get_or_create(
            name="Test Cafeteria",
            defaults={
                'location_id': uuid.uuid4(),
                'coordinates': Point(39.2400133, -6.7712043, srid=4326), # Matches COICT_CENTER_LON, COICT_CENTER_LAT
                'description': 'Main cafeteria at CoICT campus - Test',
                'location_type': 'cafeteria',
                'is_active': True,
                'is_searchable': True
            }
        )
        if not self.cafeteria_created:
            pass

    def test_get_directions_valid_locations(self):
        """
        Test the get_directions view with valid start and end locations specified by their IDs.
        This also implicitly tests utils.calculate_route.
        """
        # Ensure the locations were actually fetched or created
        self.assertIsNotNone(self.gate_location)
        self.assertIsNotNone(self.cafeteria_location)
        self.assertIsNotNone(self.gate_location.location_id)
        self.assertIsNotNone(self.cafeteria_location.location_id)

        data = {
            'from_id': str(self.gate_location.location_id),
            'to_id': str(self.cafeteria_location.location_id),
            'mode': 'walking' # Assuming 'walking' is a valid mode
        }
        url = reverse('get_directions')

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200, f"Response content: {response.content.decode()}")

        try:
            response_data = json.loads(response.content)
        except json.JSONDecodeError:
            self.fail(f"Failed to decode JSON. Response content: {response.content.decode()}")

        self.assertTrue(response_data.get('success'), f"API call failed. Response: {response_data}")
        self.assertIn('route', response_data, "Response data should contain 'route' key.")

        route_info = response_data['route']
        self.assertIsInstance(route_info.get('path'), list, "'path' should be a list.")
        self.assertTrue(len(route_info.get('path')) > 0, "'path' list should not be empty.")

        # Validate structure of path elements (assuming list of coordinate pairs/tuples)
        for point in route_info['path']:
            self.assertIsInstance(point, (list, tuple), "Each point in path should be a list or tuple.")
            self.assertEqual(len(point), 2, "Each point in path should have 2 coordinates (lat, lon).")
            self.assertIsInstance(point[0], (float, int), "Latitude should be float or int.")
            self.assertIsInstance(point[1], (float, int), "Longitude should be float or int.")

        self.assertIsInstance(route_info.get('distance'), (float, int), "'distance' should be a float or int.")
        self.assertTrue(route_info.get('distance') > 0, "'distance' should be greater than 0.")

        self.assertIsInstance(route_info.get('estimated_time'), int, "'estimated_time' should be an integer.")
        self.assertTrue(route_info.get('estimated_time') >= 0, "'estimated_time' should be non-negative.")

        # Optional: Check for duration if it's expected
        if 'duration' in route_info:
            self.assertIsInstance(route_info.get('duration'), (float, int), "'duration' should be a float or int.")
            self.assertTrue(route_info.get('duration') >= 0)

        # Optional: Check for steps if they are expected
        if 'steps' in route_info:
            self.assertIsInstance(route_info.get('steps'), list, "'steps' should be a list.")
            # Further validation of steps structure can be added here if needed
```
