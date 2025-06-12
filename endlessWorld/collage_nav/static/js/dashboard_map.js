// Global variable to hold the map instance, to be set by initCustomMapLogic
// var mapInstance = null; // This will be set by the script in dashboard.html initially
// const DYNAMIC_MAP_ID_FROM_DJANGO = "{{ map_id|escapejs }}"; // Now a global JS var
// console.log("Django template DYNAMIC_MAP_ID_FROM_DJANGO:", DYNAMIC_MAP_ID_FROM_DJANGO); // Will use global

// These variables will be used by functions now made global, so define them in a scope accessible to them.
let currentRoutePolyline = null;
let animatedNavigationMarker = null;
let searchResultMarker = null;
let recommendationMarker = null;

// Variables for Get Directions
let selectedStartLocationId = null;
let selectedStartLocationName = '';
let selectedEndLocationId = null;
let selectedEndLocationName = '';

// Global Variables for Clicked Coordinates
let clickedLat = null;
let clickedLng = null;
let clickedPointMarker = null;
let selectedStartCoords = null;
let selectedEndCoords = null;

// Global Variables for Continuous GPS Updates
let currentPositionWatcherId = null;
let currentUserLat = null;
let currentUserLng = null;
let currentUserAccuracy = null;
let currentUserHeading = null;
let currentUserSpeed = null;
let isWatchingPosition = false;

// For displaying live position on map
let userLivePositionMarker = null;
let userAccuracyCircle = null;
let followMeActive = false;

// For Off-Route Notification
const OFF_ROUTE_THRESHOLD_METERS = 25; // Approx 25 meters
const VISUAL_SNAP_THRESHOLD_METERS = 15; // User marker visually snaps if within this distance
let isCurrentlyNotifyingOffRoute = false;
let originalDestination = null; // Stores details of the original destination for recalculation

function initCustomMapLogic(generatedMapId) {
    console.log("initCustomMapLogic called with map ID:", generatedMapId);

    // Use the global mapInstance from dashboard.html
    if (window[generatedMapId] && typeof window[generatedMapId].getCenter === 'function') {
        console.log("SUCCESS: Folium map instance found in initCustomMapLogic using ID:", generatedMapId);
        mapInstance = window[generatedMapId]; // Set the global mapInstance

        // For testing, let's try a simple map action here:
        if (mapInstance.getCenter) {
            console.log("Map center from initCustomMapLogic:", mapInstance.getCenter());
        }

    } else {
        console.error("ERROR: initCustomMapLogic was called, but window[generatedMapId] is not a valid map object.", generatedMapId);
        // Fallback logic (belt-and-suspenders)
        if (window.map_map && typeof window.map_map.getCenter === 'function') {
            console.warn("Found 'window.map_map' as fallback in initCustomMapLogic.");
            mapInstance = window.map_map;  // Set the global mapInstance
        } else {
             for (let key in window) {
                if (key.startsWith("map_") && key !== generatedMapId && window[key] && typeof window[key].getCenter === 'function') {
                    console.warn(`Found map instance by iteration as '${key}' in initCustomMapLogic fallback.`);
                    mapInstance = window[key]; // Set the global mapInstance
                    break;
                }
            }
        }
        if (!mapInstance) {
            console.error("CRITICAL: Map instance still not found even after initCustomMapLogic was called and fallbacks attempted.");
            // alert("Map critical initialization error. Please refresh.");
        }
    }

    // This check needs to be AFTER mapInstance is potentially set by the above logic
    if (mapInstance) {
        // Add map click listener once mapInstance is confirmed
        mapInstance.on('click', function(e) {
            // If followMeActive is true, a map click should probably disable it.
            if (followMeActive) {
                toggleFollowMeMode(); // This will set followMeActive to false and update UI
                console.log("Follow Me mode disabled due to map click.");
            }

            clickedLat = e.latlng.lat;
            clickedLng = e.latlng.lng;

            if (clickedPointMarker && mapInstance.hasLayer(clickedPointMarker)) {
                mapInstance.removeLayer(clickedPointMarker);
            }

            clickedPointMarker = L.marker([clickedLat, clickedLng]).addTo(mapInstance);

            const popupContent = `
                <div>
                    <strong>Set Location:</strong><br>
                    Lat: ${clickedLat.toFixed(5)}, Lon: ${clickedLng.toFixed(5)}<br>
                    <button class='btn btn-sm btn-primary mt-1' onclick='setClickedPointAsStart()'>Set as Start</button>
                    <button class='btn btn-sm btn-success mt-1 ms-1' onclick='setClickedPointAsDestination()'>Set as Destination</button>
                </div>
            `;
            clickedPointMarker.bindPopup(popupContent).openPopup();
        });

        // Add event listener for manual map pan (dragstart)
        mapInstance.on('dragstart', function() {
            if (followMeActive) {
                // No need to call toggleFollowMeMode() as it would flip followMeActive back
                followMeActive = false;
                const button = document.getElementById('toggleFollowMe');
                if (button) {
                    button.textContent = 'Follow Me: Off';
                    button.classList.remove('btn-success');
                    button.classList.add('btn-secondary');
                }
                console.log("Follow Me mode disabled due to manual map pan.");
            }
        });

        // Since mapInstance is confirmed here, this is a good place to start GPS watching.
        console.log("initCustomMapLogic: Map instance confirmed. Calling startWatchingPosition().");
        startWatchingPosition();
        loadAndDisplayGeofences(); // Call to load geofences
    } else {
        console.error("initCustomMapLogic: mapInstance is STILL null after all attempts. GPS and geofences will not load.");
    }
}

// Functions to handle setting clicked point as Start or Destination
function setClickedPointAsStart() {
    if (clickedLat === null || clickedLng === null) return;
    selectedStartCoords = { lat: clickedLat, lon: clickedLng };
    selectedStartLocationId = null; // Clear ID-based selection
    selectedStartLocationName = '';
    const startInput = document.getElementById('startPointInput');
    if (startInput) {
        startInput.value = `Map Pin: ${clickedLat.toFixed(5)}, ${clickedLng.toFixed(5)}`;
        startInput.disabled = false; // Ensure it's enabled
    }
    const useCurrentCheck = document.getElementById('useCurrentLocationCheck');
    if (useCurrentCheck) useCurrentCheck.checked = false;
    const startResults = document.getElementById('startPointResults');
    if (startResults) startResults.innerHTML = '';

    console.log("Map click set as Start:", selectedStartCoords);
    if (clickedPointMarker && clickedPointMarker.isPopupOpen()) clickedPointMarker.closePopup();
    // Optionally, change clickedPointMarker icon or color here if desired
}

function setClickedPointAsDestination() {
    if (clickedLat === null || clickedLng === null) return;
    selectedEndCoords = { lat: clickedLat, lon: clickedLng };
    selectedEndLocationId = null; // Clear ID-based selection
    selectedEndLocationName = `Map Pin: ${clickedLat.toFixed(5)}, ${clickedLng.toFixed(5)}`; // Set name for map pin
    const destInput = document.getElementById('destinationPointInput');
    if (destInput) destInput.value = selectedEndLocationName; // Update input field with this name
    const destResults = document.getElementById('destinationPointResults');
    if (destResults) destResults.innerHTML = '';

    console.log("Map click set as Destination:", selectedEndCoords);
    if (clickedPointMarker && clickedPointMarker.isPopupOpen()) clickedPointMarker.closePopup();
    // Optionally, change clickedPointMarker icon or color here if desired
}

// --- Continuous GPS Update Functions ---
function handlePositionUpdate(position) {
    currentUserLat = position.coords.latitude;
    currentUserLng = position.coords.longitude;
    currentUserAccuracy = position.coords.accuracy;
    currentUserHeading = position.coords.heading; // Can be null
    currentUserSpeed = position.coords.speed; // Can be null

    console.log(`Live Update: Lat: ${currentUserLat}, Lng: ${currentUserLng}, Acc: ${currentUserAccuracy}m, Head: ${currentUserHeading}, Spd: ${currentUserSpeed}`);
    updateUserMarkerOnMap(currentUserLat, currentUserLng, currentUserAccuracy, currentUserHeading);

    // If Follow Me mode is active, pan the map to the new user location
    if (followMeActive && mapInstance) {
        mapInstance.panTo([currentUserLat, currentUserLng]);
        // Optionally, ensure a certain zoom level during follow me
        // if (mapInstance.getZoom() < 17) mapInstance.setZoom(17);
    }
}

function updateUserMarkerOnMap(lat, lng, accuracy, heading) {
    if (!mapInstance) {
        console.warn("updateUserMarkerOnMap called before mapInstance is ready.");
        return;
    }

    const rawLatLng = L.latLng(lat, lng);
    let displayLatLng = rawLatLng; // Default to raw GPS position for the marker
    let actualSnappedPoint = null; // This will store the true closest point for off-route calculation

    if (currentRoutePolyline && typeof currentRoutePolyline.getLatLngs === 'function' && currentRoutePolyline.getLatLngs().length > 0) {
        actualSnappedPoint = getClosestPointOnPolyline(currentRoutePolyline, rawLatLng);

        if (actualSnappedPoint) {
            // Visual snapping: marker jumps to line only if very close
            if (rawLatLng.distanceTo(actualSnappedPoint) < VISUAL_SNAP_THRESHOLD_METERS) {
                displayLatLng = actualSnappedPoint;
            } else {
                displayLatLng = rawLatLng; // Marker stays at raw GPS position if further than visual threshold
            }

            // Off-route notification logic: uses actual distance to the closest point on the line
            const distanceToTrueClosestOnRoute = rawLatLng.distanceTo(actualSnappedPoint);
            if (distanceToTrueClosestOnRoute > OFF_ROUTE_THRESHOLD_METERS) {
                if (!isCurrentlyNotifyingOffRoute) {
                    console.log(`User is ${distanceToTrueClosestOnRoute.toFixed(1)}m off route. Visual snap: ${displayLatLng === actualSnappedPoint}. Threshold: ${OFF_ROUTE_THRESHOLD_METERS}m.`);
                    showOffRouteNotification(distanceToTrueClosestOnRoute);
                }
            } else {
                if (isCurrentlyNotifyingOffRoute) {
                    hideOffRouteNotification();
                }
            }
        } else { // No valid snapped point could be determined (e.g. polyline disappeared)
            displayLatLng = rawLatLng;
            if (isCurrentlyNotifyingOffRoute) { // Hide notification if it was shown
                hideOffRouteNotification();
            }
        }
    } else { // No route active
        displayLatLng = rawLatLng;
        if (isCurrentlyNotifyingOffRoute) { // Hide notification if it was shown
            hideOffRouteNotification();
        }
    }

    const userIcon = L.divIcon({
        className: 'live-position-marker',
        iconSize: [18, 18],
        iconAnchor: [9, 9] // Anchor in the center of the div
    });

    if (userLivePositionMarker) {
        userLivePositionMarker.setLatLng(displayLatLng); // Use displayLatLng for marker
    } else {
        userLivePositionMarker = L.marker(displayLatLng, { // Use displayLatLng for marker
            icon: userIcon,
            zIndexOffset: 1000,
            keyboard: false
        }).addTo(mapInstance);
    }

    // Accuracy circle should always be centered on the raw GPS data
    if (accuracy != null) {
        if (userAccuracyCircle) {
            userAccuracyCircle.setLatLng(rawLatLng).setRadius(accuracy); // Use rawLatLng for accuracy circle
        } else {
            userAccuracyCircle = L.circle(rawLatLng, { // Use rawLatLng for accuracy circle
                radius: accuracy,
                weight: 1,
                color: '#007bff',
                fillColor: '#007bff',
                fillOpacity: 0.1
            }).addTo(mapInstance);
        }
        // Optional: Ensure accuracy circle doesn't get its own popup or events if not desired
        // if (userAccuracyCircle) userAccuracyCircle.options.interactive = false;
    } else {
        // If accuracy is null, remove the circle if it exists
        if (userAccuracyCircle && mapInstance.hasLayer(userAccuracyCircle)) {
            mapInstance.removeLayer(userAccuracyCircle);
            userAccuracyCircle = null;
        }
    }
}

function handlePositionError(error) {
    console.error(`Error getting live position: ${error.message} (Code: ${error.code})`);
    switch (error.code) {
        case error.PERMISSION_DENIED:
            console.error("User denied the request for Geolocation. Stopping position watching.");
            alert("Geolocation permission denied. Live location updates will be disabled. You can re-enable them by clicking 'Locate Me' or refreshing the page and allowing permission.");
            stopWatchingPosition(); // Stop trying if permission is explicitly denied
            break;
        case error.POSITION_UNAVAILABLE:
            console.error("Location information is unavailable.");
            break;
        case error.TIMEOUT:
            console.error("The request to get user location timed out.");
            break;
        default:
            console.error("An unknown error occurred with geolocation.");
            break;
    }
}

function startWatchingPosition() {
    if (navigator.geolocation) {
        if (currentPositionWatcherId) { // Clear any existing watcher
            navigator.geolocation.clearWatch(currentPositionWatcherId);
            console.log("Cleared previous position watcher.");
        }
        const options = { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 };
        currentPositionWatcherId = navigator.geolocation.watchPosition(handlePositionUpdate, handlePositionError, options);
        isWatchingPosition = true;
        console.log("Started watching position. Watcher ID:", currentPositionWatcherId);
    } else {
        console.error("Geolocation is not supported by this browser.");
        alert("Geolocation is not supported by this browser. Live location updates will not be available.");
    }
}

function stopWatchingPosition() {
    if (navigator.geolocation && currentPositionWatcherId) {
        navigator.geolocation.clearWatch(currentPositionWatcherId);
        console.log("Stopped watching position. Cleared Watcher ID:", currentPositionWatcherId);
        currentPositionWatcherId = null;
        isWatchingPosition = false;
    } else {
        console.log("No active position watcher to stop or geolocation not available.");
    }
}

function toggleFollowMeMode() {
    followMeActive = !followMeActive;
    const button = document.getElementById('toggleFollowMe');
    if (button) { // Ensure button exists
        if (followMeActive) {
            button.textContent = 'Follow Me: On';
            button.classList.remove('btn-secondary');
            button.classList.add('btn-success');
            if (currentUserLat && currentUserLng && mapInstance) { // Pan to current location if available
                mapInstance.panTo([currentUserLat, currentUserLng]);
                if (mapInstance.getZoom() < 17) mapInstance.setZoom(17); // Optionally zoom in
            }
        } else {
            button.textContent = 'Follow Me: Off';
            button.classList.remove('btn-success');
            button.classList.add('btn-secondary');
        }
    }
    console.log("Follow Me mode:", followMeActive ? "Active" : "Inactive");
}

// --- Off-Route Notification Functions ---
function showOffRouteNotification(distance) {
    isCurrentlyNotifyingOffRoute = true;
    const offRouteDiv = document.getElementById('offRouteNotification');
    if (offRouteDiv) {
        offRouteDiv.innerHTML = `You seem to be about <strong>${Math.round(distance)}m</strong> off route. <span id='recalculateRouteLink' style='text-decoration:underline; cursor:pointer; color:blue;'>Recalculate?</span>`;
        offRouteDiv.style.display = 'block';

        const recalcLink = document.getElementById('recalculateRouteLink');
        if (recalcLink) {
            recalcLink.onclick = triggerRouteRecalculation;
        }
    } else {
        console.warn(`Off-route (${Math.round(distance)}m). Recalculate? (Notification div not found)`);
    }
}

function hideOffRouteNotification() {
    isCurrentlyNotifyingOffRoute = false;
    const offRouteDiv = document.getElementById('offRouteNotification');
    if (offRouteDiv) {
        offRouteDiv.style.display = 'none';
    }
}

function triggerRouteRecalculation() {
    console.log("Route recalculation triggered.");
    if (currentUserLat == null || currentUserLng == null) { // Check for null explicitly
        alert("Cannot recalculate: Your current location is not available yet. Please wait for GPS signal.");
        console.warn("triggerRouteRecalculation: currentUserLat or currentUserLng is null.");
        return;
    }
    if (!originalDestination) {
        alert("Cannot recalculate: Original destination details were not properly stored.");
        console.warn("triggerRouteRecalculation: originalDestination is null.");
        return;
    }

    const newNavParams = {
        from_latitude: currentUserLat,
        from_longitude: currentUserLng,
        from_name: "Your Current Location" // For modal display
    };

    if (originalDestination.id) {
        newNavParams.to_id = originalDestination.id;
        newNavParams.to_name = originalDestination.name;
    } else if (originalDestination.lat != null && originalDestination.lon != null) { // Check for null explicitly
        newNavParams.to_latitude = originalDestination.lat;
        newNavParams.to_longitude = originalDestination.lon;
        newNavParams.to_name = originalDestination.name;
    } else {
        alert("Cannot recalculate: Original destination details are invalid or incomplete.");
        console.warn("triggerRouteRecalculation: originalDestination object is invalid:", originalDestination);
        return;
    }

    console.log("Recalculating route with new params:", newNavParams);
    fetchAndDisplayRoute(newNavParams); // This will also store the new destination as originalDestination again.
    hideOffRouteNotification(); // Hide the "off route" message
}
// --- End Off-Route Notification Functions ---

// Helper function to find the closest point on a polyline to a given latlng
function getClosestPointOnPolyline(polyline, latLng) {
    if (!polyline || typeof polyline.getLatLngs !== 'function') {
        return latLng; // Not a valid polyline
    }
    const polylineLatLngs = polyline.getLatLngs();

    if (polylineLatLngs.length < 2) {
        return latLng; // Not enough points to form a line
    }

    let minDistanceSq = Infinity;
    let closestPoint = null;

    // For calculations, we'll use simple x, y. For Leaflet, lat is y, lng is x.
    const pX = latLng.lng;
    const pY = latLng.lat;

    for (let i = 0; i < polylineLatLngs.length - 1; i++) {
        let p1 = polylineLatLngs[i];
        let p2 = polylineLatLngs[i+1];

        const p1X = p1.lng;
        const p1Y = p1.lat;
        const p2X = p2.lng;
        const p2Y = p2.lat;

        const segLengthSq = (p2X - p1X) * (p2X - p1X) + (p2Y - p1Y) * (p2Y - p1Y);

        if (segLengthSq === 0) { // Segment is a point
            const distSq = (pX - p1X) * (pX - p1X) + (pY - p1Y) * (pY - p1Y);
            if (distSq < minDistanceSq) {
                minDistanceSq = distSq;
                closestPoint = L.latLng(p1Y, p1X);
            }
            continue;
        }

        // Parameter t for projection of P onto the line segment P1P2
        // t = dot((P-P1), (P2-P1)) / |P2-P1|^2
        const t = ((pX - p1X) * (p2X - p1X) + (pY - p1Y) * (p2Y - p1Y)) / segLengthSq;

        let currentClosestX, currentClosestY;

        if (t < 0) { // Closest to P1
            currentClosestX = p1X;
            currentClosestY = p1Y;
        } else if (t > 1) { // Closest to P2
            currentClosestX = p2X;
            currentClosestY = p2Y;
        } else { // Projection falls onto the segment
            currentClosestX = p1X + t * (p2X - p1X);
            currentClosestY = p1Y + t * (p2Y - p1Y);
        }

        const distToCurrentClosestSq = (pX - currentClosestX) * (pX - currentClosestX) + (pY - currentClosestY) * (pY - currentClosestY);

        if (distToCurrentClosestSq < minDistanceSq) {
            minDistanceSq = distToCurrentClosestSq;
            closestPoint = L.latLng(currentClosestY, currentClosestX);
        }
    }
    return closestPoint || latLng; // Return original point if something went wrong (shouldn't happen if polyline has points)
}
// --- End Continuous GPS Update Functions ---

document.addEventListener('DOMContentLoaded', function() {
    // Primary initialization of mapInstance and subsequent calls (like startWatchingPosition)
    // should happen via initCustomMapLogic, which is called by the Folium map's embedded script.
    // The global mapInstance is expected to be set by initCustomMapLogic.
    console.log("DOMContentLoaded event fired.");
    console.log("Attempting to use DYNAMIC_MAP_ID_FROM_DJANGO (available globally):", DYNAMIC_MAP_ID_FROM_DJANGO);


    // Fallback for mapInstance initialization if initCustomMapLogic was somehow missed or delayed,
    // though this should ideally not be the primary path.
    if (!mapInstance && DYNAMIC_MAP_ID_FROM_DJANGO) {
        console.log("DOMContentLoaded: mapInstance not yet set by initCustomMapLogic. Attempting to find map via DYNAMIC_MAP_ID_FROM_DJANGO:", DYNAMIC_MAP_ID_FROM_DJANGO);
        if(window[DYNAMIC_MAP_ID_FROM_DJANGO] && typeof window[DYNAMIC_MAP_ID_FROM_DJANGO].getCenter === 'function') {
            mapInstance = window[DYNAMIC_MAP_ID_FROM_DJANGO];
            console.log("Map instance set during DOMContentLoaded using DYNAMIC_MAP_ID_FROM_DJANGO (fallback).");
            // If mapInstance is found here, and startWatchingPosition hasn't been called yet (e.g. if initCustomMapLogic didn't call it)
            // This indicates a potential issue with initCustomMapLogic not being called or map not ready then.
            // For robustness, we could call startWatchingPosition here IF it hasn't been started.
            if (!isWatchingPosition && mapInstance) { // Check a flag to prevent multiple starts
                 console.warn("DOMContentLoaded: mapInstance found (fallback), but GPS watching not started. Starting now.");
                 startWatchingPosition();
                 loadAndDisplayGeofences(); // Also load geofences
            }
        } else {
            console.warn("DOMContentLoaded: Map instance still not found using DYNAMIC_MAP_ID_FROM_DJANGO.");
        }
    } else if (mapInstance) {
        console.log("DOMContentLoaded: mapInstance was already set (likely by initCustomMapLogic).");
        // If initCustomMapLogic already ran and set mapInstance, it should have also called startWatchingPosition and loadAndDisplayGeofences.
        // However, if there's a race condition, we can add checks here.
        if (!isWatchingPosition) {
            console.warn("DOMContentLoaded: mapInstance is set, but GPS watching not started. Starting now (possible race condition fix).");
            startWatchingPosition();
        }
        // Assuming loadAndDisplayGeofences is also called in initCustomMapLogic after mapInstance is set.
        // If not, it could be called here too, guarded by a flag if necessary.
    }


    // Attach event listener for the Follow Me button
    const followMeButton = document.getElementById('toggleFollowMe');
        if (followMeButton) {
            followMeButton.addEventListener('click', toggleFollowMeMode);
        }

        // Search input listener
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', function() {
                const query = this.value.trim();
                if (query.length >= 2) {
                    fetch(`${SEARCH_LOCATIONS_URL}?q=${encodeURIComponent(query)}`) // Use global var
                        .then(response => response.json())
                        .then(data => {
                            const resultsContainer = document.getElementById('searchResults');
                            resultsContainer.innerHTML = '';
                            if (data.locations.length > 0) {
                                data.locations.forEach(location => {
                                    const item = document.createElement('a');
                                    item.href = '#';
                                    item.className = 'list-group-item list-group-item-action';
                                    item.innerHTML = `
                                        <h6>${location.name}</h6>
                                        <small class="text-muted">${location.location_type}</small>
                                        <p class="mb-1">${location.description || ''}</p>
                                    `;
                                    // Programmatic event listener for search result clicks
                                    item.addEventListener('click', (e) => {
                                        e.preventDefault();
                                        showLocation(location.location_id); // Calls global showLocation
                                    });
                                    resultsContainer.appendChild(item);
                                });
                            } else {
                                resultsContainer.innerHTML = '<div class="list-group-item">No results found</div>';
                            }
                        })
                        .catch(error => {
                            console.error('Error fetching search results:', error);
                            document.getElementById('searchResults').innerHTML = '<div class="list-group-item list-group-item-danger">Error loading results</div>';
                        });
                } else {
                     document.getElementById('searchResults').innerHTML = ''; // Clear results if query is too short
                }
            });
        }

        const searchForm = document.getElementById('searchForm');
        if (searchForm) {
            searchForm.addEventListener('submit', function(e) {
                e.preventDefault(); // Prevent form submission
            });
        }

        // --- Start of Get Directions JavaScript (New Block) ---

        const startPointInput = document.getElementById('startPointInput');
        const startPointResults = document.getElementById('startPointResults');
        const destinationPointInput = document.getElementById('destinationPointInput');
        const destinationPointResults = document.getElementById('destinationPointResults');
        // const getDirectionsButton = document.getElementById('getDirectionsButton'); // Will be used later
        // const useCurrentLocationCheck = document.getElementById('useCurrentLocationCheck'); // Will be used later

        function displayLocationSuggestions(query, resultsContainer, onSelectCallback) {
            if (query.length < 2) {
                resultsContainer.innerHTML = '';
                return;
            }
            fetch(`${SEARCH_LOCATIONS_URL}?q=${encodeURIComponent(query)}`) // Use global var
                .then(response => response.json())
                .then(data => {
                    resultsContainer.innerHTML = '';
                    if (data.locations && data.locations.length > 0) {
                        data.locations.forEach(location => {
                            const item = document.createElement('a');
                            item.href = '#';
                            item.className = 'list-group-item list-group-item-action';
                            item.textContent = location.name;
                            item.dataset.locationId = location.location_id;
                            item.dataset.locationName = location.name;
                            item.addEventListener('click', (e) => {
                                e.preventDefault();
                                onSelectCallback(location.location_id, location.name);
                                resultsContainer.innerHTML = ''; // Clear results after selection
                            });
                            resultsContainer.appendChild(item);
                        });
                    } else {
                        resultsContainer.innerHTML = '<div class="list-group-item disabled">No results found</div>';
                    }
                })
                .catch(error => {
                    console.error('Error fetching location suggestions:', error);
                    resultsContainer.innerHTML = '<div class="list-group-item list-group-item-danger">Error loading suggestions</div>';
                });
        }

        if (startPointInput) {
            startPointInput.addEventListener('input', function() {
                // Disable checkbox if user starts typing in start input
                const useCurrentCheck = document.getElementById('useCurrentLocationCheck');
                if (useCurrentCheck && useCurrentCheck.checked) {
                    // Optionally uncheck or just allow typing to override
                    // For now, let typing override without unchecking, selection will handle logic
                }
                selectedStartLocationId = null; // Reset if user types again
                selectedStartLocationName = '';
                selectedStartCoords = null; // Clear map-clicked start coords
                displayLocationSuggestions(this.value, startPointResults, (locationId, locationName) => {
                    selectedStartLocationId = locationId;
                    selectedStartLocationName = locationName;
                    startPointInput.value = locationName;
                    console.log("Start Point Selected:", selectedStartLocationName, "(ID:", selectedStartLocationId, ")");
                    const useCurrentChk = document.getElementById('useCurrentLocationCheck');
                    if(useCurrentChk) useCurrentChk.checked = false;
                    startPointInput.disabled = false;
                });
            });
        }

        if (destinationPointInput) {
            destinationPointInput.addEventListener('input', function() {
                selectedEndLocationId = null; // Reset if user types again
                selectedEndLocationName = '';
                selectedEndCoords = null; // Clear map-clicked end coords
                displayLocationSuggestions(this.value, destinationPointResults, (locationId, locationName) => {
                    selectedEndLocationId = locationId;
                    selectedEndLocationName = locationName;
                    destinationPointInput.value = locationName;
                    console.log("Destination Point Selected:", selectedEndLocationName, "(ID:", selectedEndLocationId, ")");
                });
            });
        }

        const useCurrentLocationCheck = document.getElementById('useCurrentLocationCheck');
        if (useCurrentLocationCheck) {
            useCurrentLocationCheck.addEventListener('change', function() {
                if (this.checked) {
                    startPointInput.disabled = true;
                    startPointInput.value = "Using current location";
                    selectedStartLocationId = null;
                    selectedStartLocationName = "Current Location";
                    selectedStartCoords = null; // Clear map-clicked start coords
                    startPointResults.innerHTML = '';
                } else {
                    startPointInput.disabled = false;
                    if (startPointInput.value === "Using current location") {
                         startPointInput.value = "";
                    }
                }
            });
        }

        const getDirectionsButton = document.getElementById('getDirectionsButton');
        if (getDirectionsButton) {
            getDirectionsButton.addEventListener('click', function() {
                // Updated Validation
                const startSelected = selectedStartLocationId || selectedStartCoords || useCurrentLocationCheck.checked;
                const endSelected = selectedEndLocationId || selectedEndCoords;

                if (!endSelected) {
                    alert("Please select a destination point (either from search or map click).");
                    return;
                }
                if (!startSelected) {
                    alert("Please select a start point (from search, map click, or 'Use my current location').");
                    return;
                }

                let navigationParams = {};

                // Determine Destination
                if (selectedEndCoords) {
                    navigationParams.to_latitude = selectedEndCoords.lat;
                    navigationParams.to_longitude = selectedEndCoords.lon;
                    navigationParams.to_name = `Map Pin: ${selectedEndCoords.lat.toFixed(5)}, ${selectedEndCoords.lon.toFixed(5)}`;
                } else if (selectedEndLocationId) {
                    navigationParams.to_id = selectedEndLocationId;
                    navigationParams.to_name = selectedEndLocationName;
                } else { // Should be caught by validation, but as a safeguard
                    alert("Destination not properly selected."); return;
                }


                // Determine Start
                if (useCurrentLocationCheck.checked) {
                    console.log("Initiating Get Directions using current location for start.");
                    getOriginForNavigation(function(origin) {
                        if (origin.type === 'error') {
                            alert(`Could not determine current location: ${origin.message}`);
                            return;
                        }
                        if (origin.type === 'coords') {
                            navigationParams.from_latitude = origin.lat;
                            navigationParams.from_longitude = origin.lon;
                            navigationParams.from_name = "Current Location";
                        } else {
                            navigationParams.from_id = origin.id;
                            navigationParams.from_name = origin.from;
                        }
                        console.log("Navigation params with current location as start:", navigationParams);
                        fetchAndDisplayRoute(navigationParams);
                    });
                } else if (selectedStartCoords) {
                    navigationParams.from_latitude = selectedStartCoords.lat;
                    navigationParams.from_longitude = selectedStartCoords.lon;
                    navigationParams.from_name = `Map Pin: ${selectedStartCoords.lat.toFixed(5)}, ${selectedStartCoords.lon.toFixed(5)}`;
                    console.log("Initiating Get Directions using map-clicked start point:", navigationParams);
                    fetchAndDisplayRoute(navigationParams);
                } else if (selectedStartLocationId) {
                    navigationParams.from_id = selectedStartLocationId;
                    navigationParams.from_name = selectedStartLocationName;
                    console.log("Initiating Get Directions using selected start ID:", navigationParams);
                    fetchAndDisplayRoute(navigationParams);
                } else { // Should be caught by validation
                     alert("Start point not properly selected."); return;
                }
            });
        }
        // --- End of Get Directions JavaScript (New Block) ---
    });

    // Map interaction functions are now global
    // Helper to ensure mapInstance is available for functions called by onclick or programmatically
    // This function can be simplified if initCustomMapLogic is the sole reliable initializer.
    function ensureMapInstance() {
        if (!mapInstance) {
            console.warn("ensureMapInstance: mapInstance is not set. Attempting to retrieve it via DYNAMIC_MAP_ID_FROM_DJANGO:", DYNAMIC_MAP_ID_FROM_DJANGO); // Use global
            if (window[DYNAMIC_MAP_ID_FROM_DJANGO] && typeof window[DYNAMIC_MAP_ID_FROM_DJANGO].getCenter === 'function') { // Use global
                 mapInstance = window[DYNAMIC_MAP_ID_FROM_DJANGO]; // Use global
                 console.log("ensureMapInstance: mapInstance acquired using DYNAMIC_MAP_ID_FROM_DJANGO.");
            } else {
                 console.error("ensureMapInstance: Could not acquire mapInstance. Map interactions will likely fail.");
                 return null;
            }
        }
        return mapInstance;
    }

    // Search functionality (event listener setup in DOMContentLoaded)

    // Show location on map
    function showLocation(locationId) {
        console.log("Attempting to show searched location on map for Location ID:", locationId);
        if (!ensureMapInstance()) { // Use the helper to get/confirm mapInstance
            alert("Map is not available to display location.");
            return;
        }

        fetch(`${LOCATION_DETAILS_API_BASE_URL}${locationId}/`) // Use global var
            .then(response => response.json())
            .then(locationData => {
                if (locationData.success && locationData.latitude && locationData.longitude) {
                    const lat = locationData.latitude;
                    const lon = locationData.longitude;
                    console.log(`Fetched coordinates for ${locationData.name}: Lat ${lat}, Lon ${lon}`);

                    mapInstance.panTo([lat, lon]);
                    mapInstance.setZoom(18);

                    if (searchResultMarker) { // Use the scoped searchResultMarker
                        mapInstance.removeLayer(searchResultMarker);
                    }

                    const popupContent = `
                        <b>${locationData.name}</b><br>
                        Searched Location<hr>
                        <button class="btn btn-sm btn-primary w-100" onclick="setAsDestination('${locationId}', ${lat}, ${lon})">
                            Navigate to Here
                        </button>
                    `;

                    searchResultMarker = L.marker([lat, lon], {
                        icon: L.divIcon({
                            className: 'custom-location-marker', // Your custom CSS class
                            iconSize: [15, 15], // Size of the icon
                            iconAnchor: [7, 7]  // Anchor point (center)
                        })
                    }).addTo(mapInstance)
                        .bindPopup(popupContent)
                        .openPopup();

                    console.log("Map panned and zoomed. Custom location marker added.");
                    document.getElementById('map').scrollIntoView({ behavior: 'smooth' });
                } else {
                    console.error("Failed to fetch location details for search:", locationData.error);
                    alert("Could not fetch location details: " + (locationData.error || "Unknown error"));
                }
            })
            .catch(error => {
                console.error("Error fetching location details for search:", error);
                alert("Error fetching location details. Please check console.");
            });
    }

    function getOriginForNavigation(callback) {
        const DEFAULT_ORIGIN_ID_PLACEHOLDER = "YOUR_COICT_CENTER_LOCATION_ID_REPLACE_ME"; // DEVELOPER MUST REPLACE

        function handleFallback(errorType = "last_known_failed") {
            fetch(GET_LAST_USER_LOCATION_URL) // Use global var
                .then(response => {
                    if (!response.ok) throw new Error(`Network response for last_known_location was not ok (${response.status})`);
                    return response.json();
                })
                .then(data => {
                    if (data.success && data.latitude && data.longitude) {
                        console.log("Using last known location as origin:", data);
                        callback({ type: 'coords', lat: data.latitude, lon: data.longitude, from: 'last_known' });
                    } else {
                        console.warn("Last known location not available or invalid, falling back to default ID. Server response:", data);
                        if (DEFAULT_ORIGIN_ID_PLACEHOLDER === "YOUR_COICT_CENTER_LOCATION_ID_REPLACE_ME" || DEFAULT_ORIGIN_ID_PLACEHOLDER.length !== 36) {
                             alert("Developer: Default Origin ID (COICT_CENTER_LOCATION_ID) is not configured correctly in dashboard.html.");
                             callback({type: 'error', message: 'Default origin ID not set or invalid.'});
                             return;
                        }
                        console.warn("Using default origin ID:", DEFAULT_ORIGIN_ID_PLACEHOLDER);
                        callback({ type: 'id', id: DEFAULT_ORIGIN_ID_PLACEHOLDER, from: 'default_fallback' });
                    }
                })
                .catch(err => {
                    console.error("Error fetching last known location or initial fallback failed:", err);
                     if (DEFAULT_ORIGIN_ID_PLACEHOLDER === "YOUR_COICT_CENTER_LOCATION_ID_REPLACE_ME" || DEFAULT_ORIGIN_ID_PLACEHOLDER.length !== 36) {
                         alert("Developer: Default Origin ID (COICT_CENTER_LOCATION_ID) is not configured correctly in dashboard.html.");
                         callback({type: 'error', message: 'Default origin ID not set or invalid after error.'});
                         return;
                    }
                    console.warn("Using default origin ID after error:", DEFAULT_ORIGIN_ID_PLACEHOLDER);
                    callback({ type: 'id', id: DEFAULT_ORIGIN_ID_PLACEHOLDER, from: 'default_fallback_on_error' });
                });
        }

        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                function(position) { // Success
                    console.log("Using live geolocation as origin.");
                    callback({
                        type: 'coords',
                        lat: position.coords.latitude,
                        lon: position.coords.longitude,
                        from: 'live_geolocation'
                    });
                },
                function(error) { // Geolocation failed or denied
                    console.warn("Live geolocation failed:", error.message, ". Attempting fallback.");
                    handleFallback("live_geolocation_failed");
                },
                { timeout: 5000, enableHighAccuracy: true }
            );
        } else { // Geolocation not supported by browser
            console.warn("Geolocation not supported by this browser. Attempting fallback.");
            handleFallback("geolocation_not_supported");
        }
    }

    function fetchAndDisplayRoute(navigationParams) {
        console.log("fetchAndDisplayRoute called with params:", navigationParams);

        originalDestination = {};
        if (navigationParams.to_id) {
            originalDestination.id = navigationParams.to_id;
            originalDestination.name = navigationParams.to_name || selectedEndLocationName || 'Selected Destination ID: ' + navigationParams.to_id;
        } else if (navigationParams.to_latitude && navigationParams.to_longitude) {
            originalDestination.lat = navigationParams.to_latitude;
            originalDestination.lon = navigationParams.to_longitude;
            originalDestination.name = navigationParams.to_name || `Map Pin: ${navigationParams.to_latitude.toFixed(5)}, ${navigationParams.to_longitude.toFixed(5)}`;
        } else {
            originalDestination = null;
            console.error("Cannot store original destination: Missing to_id or to_lat/lon in navigationParams for fetchAndDisplayRoute.", navigationParams);
        }
        console.log("Original destination for recalculation stored:", originalDestination);

        if (!ensureMapInstance()) {
            alert("Map is not available to display the route.");
            return;
        }

        if (currentRoutePolyline && mapInstance.hasLayer(currentRoutePolyline)) mapInstance.removeLayer(currentRoutePolyline);
        if (animatedNavigationMarker && mapInstance.hasLayer(animatedNavigationMarker)) mapInstance.removeLayer(animatedNavigationMarker);
        currentRoutePolyline = null;
        animatedNavigationMarker = null;

        let fetchBody = { /* to_id or to_latitude/longitude will be added below */ };

        if (navigationParams.to_id) {
            fetchBody.to_id = navigationParams.to_id;
        } else if (navigationParams.to_latitude && navigationParams.to_longitude) {
            fetchBody.to_latitude = navigationParams.to_latitude;
            fetchBody.to_longitude = navigationParams.to_longitude;
        } else {
            alert("Destination information missing for navigation.");
            console.error("Insufficient destination info in fetchAndDisplayRoute:", navigationParams);
            return;
        }

        if (navigationParams.from_id) {
            fetchBody.from_id = navigationParams.from_id;
        } else if (navigationParams.from_latitude && navigationParams.from_longitude) {
            fetchBody.from_latitude = navigationParams.from_latitude;
            fetchBody.from_longitude = navigationParams.from_longitude;
        } else {
            alert("Start location information missing for navigation.");
            console.error("Insufficient start location info in fetchAndDisplayRoute:", navigationParams);
            return;
        }

        console.log("Fetching directions with body:", fetchBody);

        fetch(GET_DIRECTIONS_URL, { // Use global var
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN }, // Use global var
            body: JSON.stringify(fetchBody)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (currentRoutePolyline) mapInstance.removeLayer(currentRoutePolyline);
                if (animatedNavigationMarker) mapInstance.removeLayer(animatedNavigationMarker);

                const latLngs = data.route.path.map(coord => L.latLng(coord[0], coord[1]));
                if (latLngs.length < 2) {
                    alert("Route path is too short to display."); return;
                }
                currentRoutePolyline = L.polyline(latLngs, { color: 'blue', weight: 6, opacity: 0.7 }).addTo(mapInstance);
                mapInstance.fitBounds(currentRoutePolyline.getBounds().pad(0.1));

                const pointerIcon = L.icon({
                    iconUrl: NAVIGATION_POINTER_IMG_URL, // Use global var
                    iconSize: [25, 41], iconAnchor: [12, 41]
                });

                const totalDurationMs = data.route.estimated_time * 60 * 1000;
                animatedNavigationMarker = L.Marker.movingMarker(latLngs, [totalDurationMs], {
                    autostart: true, loop: false, icon: pointerIcon
                });

                animatedNavigationMarker.on('end', function() {
                    console.log("Navigation animation finished for custom route.");
                    if(mapInstance && latLngs.length > 0) {
                         L.marker(latLngs[latLngs.length - 1], {icon: pointerIcon})
                            .addTo(mapInstance)
                            .bindPopup(`Arrived at ${data.route.destination.name || navigationParams.to_name || 'destination'}`)
                            .openPopup();
                    }
                    if(mapInstance && animatedNavigationMarker) mapInstance.removeLayer(animatedNavigationMarker);
                });
                mapInstance.addLayer(animatedNavigationMarker);

                const modal = new bootstrap.Modal(document.getElementById('directionsModal'));
                const routeDetailsEl = document.getElementById('routeDetails');

                const fromName = navigationParams.from_name || data.route.source.name;
                const toName = navigationParams.to_name || data.route.destination.name;

                routeDetailsEl.innerHTML = `
                    <h6>From: ${fromName}</h6>
                    <h6>To: ${toName}</h6>
                    <p>Distance: ${data.route.distance.toFixed(0)} meters</p>
                    <p>Estimated time: ${data.route.estimated_time} minutes</p>
                    <hr><h6>Steps:</h6>
                    <ol>${data.route.steps.map(step => `<li>${step.instruction} (${step.distance.toFixed(0)}m, ${Math.round(step.duration/60)} min)</li>`).join('')}</ol>
                `;
                modal.show();
                document.getElementById('map').scrollIntoView({ behavior: 'smooth' });
            } else {
                alert("Error getting directions: " + (data.error || 'Unknown error'));
            }
        })
        .catch(err => {
            console.error("Error in fetchAndDisplayRoute's fetch call:", err);
            alert("Could not retrieve new directions. Please check console.");
        });
    }

    function setAsDestination(destinationId, destLat, destLng) {
        console.log(`Preparing navigation to Destination ID: ${destinationId} (from map click)`);
        if (!ensureMapInstance()) {
            alert("Map is not available to set destination.");
            return;
        }
        if (mapInstance && typeof mapInstance.closePopup === 'function') {
            mapInstance.closePopup();
        }

        fetch(`${LOCATION_DETAILS_API_BASE_URL}${destinationId}/`) // Use global var
            .then(response => response.json())
            .then(locationData => {
                const destinationName = locationData.success ? locationData.name : `ID: ${destinationId}`;

                getOriginForNavigation(function(origin) {
                    if (origin.type === 'error') {
                        alert(`Could not determine origin for navigation: ${origin.message}`);
                        return;
                    }

                    let navigationParams = {
                        to_id: destinationId,
                        to_name: destinationName
                    };

                    if (origin.type === 'coords') {
                        navigationParams.from_latitude = origin.lat;
                        navigationParams.from_longitude = origin.lon;
                        navigationParams.from_name = "Current Location";
                    } else {
                        navigationParams.from_id = origin.id;
                        navigationParams.from_name = origin.from;
                    }
                    fetchAndDisplayRoute(navigationParams);
                });
            })
            .catch(err => {
                console.error("Error fetching destination details for name:", err);
                getOriginForNavigation(function(origin) {
                    if (origin.type === 'error') {
                        alert(`Could not determine origin for navigation: ${origin.message}`);
                        return;
                    }
                    let navigationParams = { to_id: destinationId, to_name: `ID: ${destinationId}` };
                     if (origin.type === 'coords') {
                        navigationParams.from_latitude = origin.lat;
                        navigationParams.from_longitude = origin.lon;
                        navigationParams.from_name = "Current Location";
                    } else {
                        navigationParams.from_id = origin.id;
                        navigationParams.from_name = origin.from;
                    }
                    fetchAndDisplayRoute(navigationParams);
                });
            });
    }

    function locateMe() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                position => {
                    const { latitude, longitude, accuracy } = position.coords;

                    fetch(UPDATE_LOCATION_URL, { // Use global var
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': CSRF_TOKEN // Use global var
                        },
                        body: JSON.stringify({
                            latitude: latitude,
                            longitude: longitude,
                            accuracy: accuracy
                        })
                    }).then(response => response.json())
                      .then(data => {
                          if (data.success) {
                              window.location.reload();
                          }
                      });
                },
                error => {
                    console.error("Geolocation error:", error);
                    alert("Could not get your location. Please ensure location services are enabled.");
                },
                { enableHighAccuracy: true }
            );
        } else {
            alert("Geolocation is not supported by your browser.");
        }
    }

    function zoomIn() {
        if (ensureMapInstance()) mapInstance.zoomIn();
    }

    function zoomOut() {
        if (ensureMapInstance()) mapInstance.zoomOut();
    }

    function showRecommendationOnMap(locationId, mediaUrl) {
        console.log("Attempting to show recommendation on map for Location ID:", locationId, "Media URL:", mediaUrl);

        if (!ensureMapInstance()) {
            alert("Error: Map object not found. Cannot display recommendation on map.");
            return;
        }

        fetch(`${LOCATION_DETAILS_API_BASE_URL}${locationId}/`) // Use global var
            .then(response => response.json())
            .then(data => {
                if (data.success && data.latitude && data.longitude) {
                    const lat = data.latitude;
                    const lon = data.longitude;

                    console.log(`Fetched coordinates for ${data.name}: Lat ${lat}, Lon ${lon}`);

                    mapInstance.panTo([lat, lon]);
                    mapInstance.setZoom(18);

                    if (recommendationMarker) { // Use global recommendationMarker
                        mapInstance.removeLayer(recommendationMarker);
                    }

                    recommendationMarker = L.marker([lat, lon], { // Assign to global
                        icon: L.divIcon({
                            className: 'custom-recommendation-marker',
                            iconSize: [15, 15],
                            iconAnchor: [7, 7]
                        })
                    }).addTo(mapInstance)
                        .bindPopup(`<b>${data.name}</b><br><img src="${mediaUrl}" alt="${data.name}" style="width:100px;height:auto;">`)
                        .openPopup();

                    console.log("Map panned and zoomed. Custom recommendation marker added.");
                    document.getElementById('map').scrollIntoView({ behavior: 'smooth' });

                } else {
                    console.error("Failed to fetch location details or missing coordinates:", data.error);
                    alert("Could not fetch location details: " + (data.error || "Unknown error"));
                }
            })
            .catch(error => {
                console.error("Error fetching location details:", error);
                alert("Error fetching location details. Please check console.");
            });
    }

// --- Geofence Display Functionality ---
function loadAndDisplayGeofences() {
    if (!ensureMapInstance()) {
        console.warn("Map instance not ready for loading geofences.");
        return;
    }

    fetch(GEOFENCES_API_URL) // Use global var
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.geofences && data.geofences.length > 0) {
                data.geofences.forEach(gf => {
                    if (gf.boundary_geojson && gf.boundary_geojson.coordinates) { // Check for coordinates as well
                        try {
                            L.geoJSON(gf.boundary_geojson, {
                                style: function (feature) {
                                    // Example: Use a default style, or customize based on gf properties
                                    return { color: "#ff7800", weight: 2, opacity: 0.65, fillColor: "#ff7800", fillOpacity: 0.1 };
                                }
                            }).bindPopup(`<b>${gf.name}</b><br>${gf.description || 'Geofenced Area'}`)
                              .addTo(mapInstance);
                        } catch (e) {
                            console.error("Error creating GeoJSON layer for geofence:", gf.name, e);
                        }
                    } else {
                        console.warn("Geofence data missing boundary_geojson or coordinates:", gf);
                    }
                });
                console.log(`${data.geofences.length} geofences loaded and displayed.`);
            } else {
                console.log("No active geofences to display or API returned empty list.");
            }
        })
        .catch(error => {
            console.error("Error fetching or displaying geofences:", error);
            // Optionally, inform the user on the UI, but avoid alerts for background tasks
        });
}
// --- End Geofence Display Functionality ---
