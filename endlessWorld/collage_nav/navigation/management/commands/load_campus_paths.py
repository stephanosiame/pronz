import json
from django.core.management.base import BaseCommand
from navigation.models import CampusPath

class Command(BaseCommand):
    help = 'Loads predefined campus paths from GeoJSON data into the CampusPath model'

    ROUTE_DATA_GEOJSON = [
        {
          "type": "Feature",
          "properties": { "area": 1, "description": "Route 1" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24033, -6.77232], [39.24018, -6.77221], [39.24018, -6.77221], [39.24015, -6.77208],
              [39.24009, -6.77188], [39.24008, -6.77175], [39.24008, -6.77167], [39.2401, -6.77155],
              [39.24011, -6.77144], [39.24011, -6.77144], [39.23995, -6.7713], [39.23981, -6.7712],
              [39.2397, -6.77115], [39.23948, -6.77139], [39.23948, -6.77139]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 2, "description": "Route 2" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24033, -6.77232], [39.24018, -6.77221], [39.24018, -6.77221], [39.24015, -6.77208],
              [39.24009, -6.77188], [39.24008, -6.77175], [39.24008, -6.77167], [39.2401, -6.77155],
              [39.24011, -6.77144], [39.24011, -6.77144], [39.23999, -6.77133], [39.23999, -6.77133]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 3, "description": "Route 3" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24033, -6.77232], [39.24018, -6.77221], [39.24018, -6.77221], [39.24061, -6.77175],
              [39.24061, -6.77175]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 4, "description": "Route 4" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.23954, -6.77171], [39.24018, -6.77221], [39.24018, -6.77221], [39.24061, -6.77175],
              [39.24061, -6.77175]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 5, "description": "Route 5" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24, -6.77134], [39.24011, -6.77144], [39.2401, -6.77155], [39.24008, -6.77167],
              [39.24008, -6.77175], [39.24009, -6.77188], [39.24015, -6.77208], [39.24018, -6.77221],
              [39.24018, -6.77221], [39.24061, -6.77175], [39.24061, -6.77175]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 6, "description": "Route 6" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24011, -6.7714], [39.24011, -6.77144], [39.2401, -6.77155], [39.24008, -6.77167],
              [39.24008, -6.77175], [39.24009, -6.77188], [39.24015, -6.77208], [39.24018, -6.77221],
              [39.24018, -6.77221], [39.24066, -6.77169], [39.24066, -6.77169]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 7, "description": "Route 7" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24002, -6.77106], [39.24001, -6.77107], [39.2399, -6.7712], [39.23989, -6.77122],
              [39.2399, -6.77123], [39.23996, -6.77129], [39.23997, -6.7713], [39.24, -6.77133],
              [39.2401, -6.77139], [39.24011, -6.77144], [39.2401, -6.77155], [39.24008, -6.77167],
              [39.24008, -6.77175], [39.24009, -6.77188], [39.24015, -6.77208], [39.24018, -6.77221],
              [39.24018, -6.77221], [39.24066, -6.77169], [39.24066, -6.77169]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 8, "description": "Route 8" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24002, -6.77106], [39.24001, -6.77107], [39.2399, -6.7712], [39.23989, -6.77122],
              [39.2399, -6.77123], [39.23996, -6.77129], [39.23997, -6.7713], [39.24, -6.77133],
              [39.2401, -6.77139], [39.24011, -6.77144], [39.24011, -6.77144]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 9, "description": "Route 9" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.24002, -6.77106], [39.24001, -6.77107], [39.2399, -6.7712], [39.23989, -6.77122],
              [39.2399, -6.77123], [39.23996, -6.77129], [39.23997, -6.7713], [39.24, -6.77133],
              [39.2401, -6.77139], [39.24011, -6.77144], [39.24011, -6.77144], [39.23995, -6.7713],
              [39.23981, -6.7712], [39.23981, -6.7712], [39.2397, -6.77133], [39.2397, -6.77133]
            ]
          }
        },
        {
          "type": "Feature",
          "properties": { "area": 10, "description": "Route 10" },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [39.2397, -6.77115], [39.23981, -6.7712], [39.23981, -6.7712], [39.2397, -6.77133],
              [39.2397, -6.77133]
            ]
          }
        }
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to load campus paths...'))

        loaded_count = 0
        skipped_count = 0

        for route_feature_json in self.ROUTE_DATA_GEOJSON:
            try:
                area_id = route_feature_json.get("properties", {}).get("area")
                description = route_feature_json.get("properties", {}).get("description", f"Path for Area {area_id}")

                # Use description as name, fallback if not present
                path_name = description or f"Campus Path Area {area_id}"

                # Check if a path with this name or area_id already exists to avoid duplicates
                # This is a simple check; more complex logic might be needed for updates.
                if CampusPath.objects.filter(name=path_name).exists() or \
                   (area_id is not None and CampusPath.objects.filter(area_id=area_id).exists()):
                    self.stdout.write(self.style.WARNING(f'Skipping existing path: {path_name} (Area {area_id})'))
                    skipped_count +=1
                    continue

                CampusPath.objects.create(
                    name=path_name,
                    area_id=area_id,
                    description=f"Predefined campus navigation path for {description}.", # A more generic description
                    geojson_feature=route_feature_json
                )
                loaded_count += 1
                self.stdout.write(self.style.SUCCESS(f'Successfully loaded: {path_name}'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error loading path {description or "Unknown"}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Finished loading campus paths. Loaded: {loaded_count}, Skipped: {skipped_count}'))
