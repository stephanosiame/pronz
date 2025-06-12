import logging
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from shapely.geometry import Polygon as ShapelyPolygon, LineString as ShapelyLineString, Point as ShapelyPoint
from shapely.wkt import loads as load_wkt
import osmnx as ox

# Assuming your Location model and COICT_BOUNDARY_POLYGON are accessible
# Adjust imports based on your actual project structure if necessary
from navigation.models import Location  # Adjust if your app name is different
from navigation.utils import COICT_BOUNDARY_POLYGON # Get the boundary polygon

logger = logging.getLogger(__name__)

# OSM features to import. Example: buildings.
# See OSMnx documentation for how to specify tags:
# https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.features.features_from_polygon
TAGS_TO_IMPORT = {'building': True}

# Mapping from OSM building types (examples) to Location.LOCATION_TYPES choices
# This will need to be expanded based on actual OSM data and your Location types
OSM_TO_LOCATION_TYPE_MAPPING = {
    'yes': 'building', # Generic building
    'school': 'building', # Could also be 'education' if you add it
    'university': 'building',
    'dormitory': 'dormitory',
    'lecture_hall': 'lecture_hall',
    # Add more mappings as needed
}

class Command(BaseCommand):
    help = 'Imports OSM features (e.g., buildings, amenities) into the Location model for the CoICT area.'

    def handle(self, *args, **options):
        self.stdout.write("Starting OSM feature import process...")

        if COICT_BOUNDARY_POLYGON is None:
            self.stderr.write(self.style.ERROR("COICT_BOUNDARY_POLYGON is not defined or loaded. Aborting."))
            return

        try:
            # Convert Django GEOS Polygon to Shapely Polygon for OSMnx
            shapely_coict_boundary = load_wkt(COICT_BOUNDARY_POLYGON.wkt)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error converting boundary polygon: {e}"))
            return

        self.stdout.write(f"Fetching features with tags: {TAGS_TO_IMPORT} within the CoICT boundary.")
        try:
            features_gdf = ox.features_from_polygon(shapely_coict_boundary, tags=TAGS_TO_IMPORT)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error fetching OSM features with osmnx: {e}"))
            return

        if features_gdf.empty:
            self.stdout.write(self.style.WARNING("No features found for the given tags and boundary."))
            return

        self.stdout.write(f"Found {len(features_gdf)} features. Processing and importing into Location model...")

        created_count = 0
        updated_count = 0

        for index, row in features_gdf.iterrows():
            geometry = row.geometry
            name = row.get('name', None)
            osm_id = str(row.get('osmid', None)) # OSM ID can be useful

            if not geometry:
                self.stdout.write(self.style.WARNING(f"Skipping feature with no geometry (OSM ID: {osm_id}, Name: {name})."))
                continue

            # Determine location point (centroid for polygons/linestrings)
            location_point = None
            if isinstance(geometry, (ShapelyPolygon, ShapelyLineString)):
                centroid = geometry.centroid
                location_point = Point(centroid.x, centroid.y, srid=4326)
            elif isinstance(geometry, ShapelyPoint):
                location_point = Point(geometry.x, geometry.y, srid=4326)
            else:
                self.stdout.write(self.style.WARNING(f"Skipping feature with unhandled geometry type: {type(geometry)} (OSM ID: {osm_id}, Name: {name})."))
                continue

            if not name:
                name = f"Unnamed Feature (OSM ID: {osm_id})" # Default name if OSM name is missing

            # Try to determine location type
            location_type_value = 'landmark' # Default
            if 'building' in row and row['building'] in OSM_TO_LOCATION_TYPE_MAPPING:
                location_type_value = OSM_TO_LOCATION_TYPE_MAPPING[row['building']]
            elif 'amenity' in row and row['amenity'] in OSM_TO_LOCATION_TYPE_MAPPING: # Example if you import amenities
                 location_type_value = OSM_TO_LOCATION_TYPE_MAPPING[row['amenity']]


            # Create or update Location object
            # Using name and coordinates for uniqueness for now, consider using OSM ID if stable
            try:
                loc, created = Location.objects.update_or_create(
                    name=name, # This might lead to issues if names are not unique
                    # Consider adding a unique OSM ID field to Location model for better matching
                    # coordinates__dwithin=(location_point, 0.00001), # Check for nearby points (adjust tolerance)
                    defaults={
                        'coordinates': location_point,
                        'location_type': location_type_value,
                        'description': row.get('description', '') or f"OSM ID: {osm_id}", # Add description if available
                        'address': row.get('addr:full', '') or row.get('addr:street', ''), # Example address tags
                        # Set other fields as needed, e.g. from other OSM tags
                    }
                )
                # A more robust way for update_or_create would be to have a unique 'osm_id' field in Location model.
                # For example:
                # osm_feature_id = f"osm_{osm_id}_{index}" # Create a unique ID
                # loc, created = Location.objects.update_or_create(
                #    osm_external_id=osm_feature_id, # Assuming you add `osm_external_id` to Location model
                #    defaults={ ... }
                # )


                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Created Location: {loc.name} (Type: {loc.location_type})"))
                else:
                    updated_count += 1
                    self.stdout.write(f"Updated Location: {loc.name}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error creating/updating Location for OSM ID {osm_id} (Name: {name}): {e}"))

        self.stdout.write(self.style.SUCCESS(f"Import complete. Created: {created_count}, Updated: {updated_count}"))
        self.stdout.write("Remember to run this command in your local environment where the database is set up and migrations have been applied.")
