let mapInstance = null;

// New global variables for manual route drawing - REMOVED
// let isDrawingManualRoute = false;
// let manualRoutePoints = [];
// let manualRoutePolyline = null;

// These variables were global in dashboard.html, ensure they are accessible within this module
// or passed as parameters where needed.
// let currentRoutePolyline = null; // Replaced by LRM
// let animatedNavigationMarker = null; // Replaced by LRM
let searchResultMarker = null;
let recommendationMarker = null; // window.recommendationMarker was used before, changed to local
let clickedLat = null;
let clickedLng = null;
let clickedPointMarker = null;
let selectedStartLocationId = null;
let selectedStartLocationName = '';
let selectedEndLocationId = null;
let selectedEndLocationName = '';
let selectedStartCoords = null;
let selectedEndCoords = null;
let currentPositionWatcherId = null;
let currentUserLat = null;
let currentUserLng = null;
let currentUserAccuracy = null;
let currentUserHeading = null;
let currentUserSpeed = null;
let isWatchingPosition = false;
let userLivePositionMarker = null;
let userAccuracyCircle = null;
// let followMeActive = false; // Removed as per request
const OFF_ROUTE_THRESHOLD_METERS = 25;
const VISUAL_SNAP_THRESHOLD_METERS = 15; // This might still be useful for snapping user to LRM route
let isCurrentlyNotifyingOffRoute = false;
let originalDestination = null; // Used by LRM for recalculation context (stores to_id, to_lat, to_lon, to_name)
let lrmControl = null; // For Leaflet Routing Machine control

// This function is expected to be called by the Folium map's generated HTML
window.initCustomMapLogic = function(generatedMapId) {
    console.log("initCustomMapLogic called with map ID:", generatedMapId);

    if (window[generatedMapId] && typeof window[generatedMapId].getCenter === 'function') {
        mapInstance = window[generatedMapId];
    } else {
        console.error("ERROR: initCustomMapLogic was called, but window[generatedMapId] is not a valid map object.", generatedMapId);
        if (window.map_map && typeof window.map_map.getCenter === 'function') { // Fallback
            mapInstance = window.map_map;
        } else { // Iterative fallback
             for (let key in window) {
                if (key.startsWith("map_") && key !== generatedMapId && window[key] && typeof window[key].getCenter === 'function') {
                    mapInstance = window[key];
                    break;
                }
            }
        }
    }

    if (!mapInstance) {
        console.error("CRITICAL: Map instance still not found.");
        // alert("Map critical initialization error. Please refresh.");
        return;
    }

    mapInstance.on('click', function(e) {
        // if (isDrawingManualRoute) { // Removed manual drawing logic
        //     manualRoutePoints.push(e.latlng);
        //     updateManualRoutePolyline();
        //     return;
        // }
        // if (followMeActive) { // Removed follow me logic
        //     toggleFollowMeMode(); // Optionally disable follow-me on map click
        // }
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

    mapInstance.on('dragstart', function() {
        if (followMeActive) {
            followMeActive = false;
            const button = document.getElementById('toggleFollowMe');
            if (button) {
                button.textContent = 'Follow Me: Off';
                button.classList.remove('btn-success');
                button.classList.add('btn-secondary');
            }
        }
    });

    startWatchingPosition();
    loadAndDisplayGeofences();

    const movingMarkerScript = document.createElement('script');
    movingMarkerScript.src = LEAFLET_MOVINGMARKER_JS_URL;
    movingMarkerScript.onload = function() {
        if (typeof L.Marker.movingMarker === 'function') {
            initializeDashboardAppLogic();
        } else {
            console.error("L.Marker.movingMarker is STILL NOT defined after loading script!");
            alert("Critical error: MovingMarker plugin did not initialize correctly.");
        }
    };
    movingMarkerScript.onerror = () => {
        console.error("Error loading leaflet.movingmarker.js dynamically.");
        alert("Error loading essential map component (MovingMarker).");
    };
    document.head.appendChild(movingMarkerScript);
};

// Helper function to fetch location coordinates by ID
function getLocationCoordinates(locationId) {
    console.log(`Fetching coordinates for location ID: ${locationId}`);
    return fetch(`${LOCATION_DETAILS_API_BASE_URL}${locationId}/`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Network response was not ok for location ID: ${locationId}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.latitude && data.longitude) {
                console.log(`Coordinates received for ${locationId}: ${data.latitude}, ${data.longitude}`);
                return { latlng: L.latLng(data.latitude, data.longitude), name: data.name }; // Return name too
            } else {
                throw new Error(data.error || 'Could not fetch coordinates for location ID: ' + locationId);
            }
        });
}

function initializeDashboardAppLogic() {
    // Fallback for mapInstance if initCustomMapLogic hasn't set it (should not be needed if Folium calls initCustomMapLogic)
    if (!mapInstance && DYNAMIC_MAP_ID_FROM_DJANGO && window[DYNAMIC_MAP_ID_FROM_DJANGO]) {
        mapInstance = window[DYNAMIC_MAP_ID_FROM_DJANGO];
    }
    if (!isWatchingPosition && mapInstance) { // Ensure GPS watching starts if map is now available
        startWatchingPosition();
        loadAndDisplayGeofences();
    }

    const searchInput = document.getElementById('searchInput');
    const searchResultsContainer = document.getElementById('searchResults');
    const startPointInput = document.getElementById('startPointInput');
    const startPointResultsContainer = document.getElementById('startPointResults');
    const destinationPointInput = document.getElementById('destinationPointInput');
    const destinationPointResultsContainer = document.getElementById('destinationPointResults');

    if (searchInput && searchResultsContainer) {
        searchInput.addEventListener('input', function() {
            displayLocationSuggestions(this.value, searchResultsContainer, searchInput, 'general');
        });
        // Prevent form submission from reloading page for the main search
        const searchForm = document.getElementById('searchForm');
        if (searchForm) {
            searchForm.addEventListener('submit', function(e) {
                e.preventDefault();
                displayLocationSuggestions(searchInput.value, searchResultsContainer, searchInput, 'general');
            });
        }
    }

    if (startPointInput && startPointResultsContainer) {
        startPointInput.addEventListener('input', function() {
            if (this.value.startsWith("Pin:") || this.value === "Current Location") return; // Don't search if it's a pin or current loc
            document.getElementById('useCurrentLocationCheck').checked = false; // Uncheck if typing
            selectedStartLocationId = null; // Clear previous selections
            selectedStartCoords = null;
            displayLocationSuggestions(this.value, startPointResultsContainer, startPointInput, 'start');
        });
    }

    if (destinationPointInput && destinationPointResultsContainer) {
        destinationPointInput.addEventListener('input', function() {
             if (this.value.startsWith("Pin:")) return; // Don't search if it's a pin
            selectedEndLocationId = null; // Clear previous selections
            selectedEndCoords = null;
            displayLocationSuggestions(this.value, destinationPointResultsContainer, destinationPointInput, 'destination');
        });
    }

    const useCurrentLocationCheck = document.getElementById('useCurrentLocationCheck');
    if (useCurrentLocationCheck) {
        useCurrentLocationCheck.addEventListener('change', function() {
            if (this.checked) {
                if (currentUserLat && currentUserLng) {
                    startPointInput.value = 'Current Location';
                    startPointInput.disabled = true;
                    selectedStartLocationId = null; // Clear ID selection
                    selectedStartCoords = null; // Clear pin selection
                    if(startPointResultsContainer) startPointResultsContainer.innerHTML = '';
                } else {
                    alert('Current location is not available. Please enable location services.');
                    this.checked = false; // Revert check
                }
            } else {
                startPointInput.value = '';
                startPointInput.disabled = false;
                startPointInput.focus();
            }
        });
    }

    const getDirectionsButton = document.getElementById('getDirectionsButton');
    if (getDirectionsButton) {
        getDirectionsButton.addEventListener('click', function() {
            if (!L.Routing || !mapInstance) {
                alert("Map or Routing library not loaded.");
                return;
            }

            let startPromise, endPromise;
            let tempOriginalDestination = {}; // To build context for potential recalculation

            // Determine start point promise
            if (useCurrentLocationCheck && useCurrentLocationCheck.checked) {
                if (currentUserLat != null && currentUserLng != null) {
                    startPromise = Promise.resolve({ latlng: L.latLng(currentUserLat, currentUserLng), name: "Current Location" });
                } else {
                    alert("Current location not available. Please enable location services or select a start point.");
                    return;
                }
            } else if (selectedStartCoords) {
                startPromise = Promise.resolve({ latlng: L.latLng(selectedStartCoords.lat, selectedStartCoords.lon), name: `Pin: ${selectedStartCoords.lat.toFixed(5)}, ${selectedStartCoords.lon.toFixed(5)}` });
            } else if (selectedStartLocationId) {
                startPromise = getLocationCoordinates(selectedStartLocationId);
            } else {
                 alert("Please select a start point.");
                 return;
            }

            // Determine end point promise
            if (selectedEndCoords) {
                endPromise = Promise.resolve({ latlng: L.latLng(selectedEndCoords.lat, selectedEndCoords.lon), name: `Pin: ${selectedEndCoords.lat.toFixed(5)}, ${selectedEndCoords.lon.toFixed(5)}` });
            } else if (selectedEndLocationId) {
                endPromise = getLocationCoordinates(selectedEndLocationId);
            } else {
                alert("Please select a destination point.");
                return;
            }

            Promise.all([startPromise, endPromise])
                .then(([startData, endData]) => {
                    if (!startData || !startData.latlng || !endData || !endData.latlng) {
                        alert("Could not determine valid start or end coordinates.");
                        return;
                    }

                    // Store details for potential recalculation
                    originalDestination = {
                        from_lat: startData.latlng.lat, from_lon: startData.latlng.lng, from_name: startData.name,
                        to_lat: endData.latlng.lat, to_lon: endData.latlng.lng, to_name: endData.name,
                        // Store IDs if they were used, for more precise recalculation context
                        from_id: selectedStartLocationId,
                        to_id: selectedEndLocationId
                    };
                    selectedStartLocationId = null; selectedEndLocationId = null; // Clear them after use for LRM
                    selectedStartCoords = null; selectedEndCoords = null;


                    if (lrmControl) { // Clear existing LRM control
                        if (typeof lrmControl.remove === 'function') lrmControl.remove();
                        lrmControl = null;
                    }

                    // if (manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) { // Clear manual route - REMOVED
                    //     mapInstance.removeLayer(manualRoutePolyline);
                    //     manualRoutePolyline = null; manualRoutePoints = [];
                    // }

                    lrmControl = L.Routing.control({
                        waypoints: [startData.latlng, endData.latlng],
                        router: new CustomRouter(),
                        routeWhileDragging: false, addWaypoints: true, show: true,
                    }).addTo(mapInstance);

                    hideOffRouteNotification();
                    if(clickedPointMarker && clickedPointMarker.isPopupOpen()) clickedPointMarker.closePopup();
                    if(searchResultMarker && searchResultMarker.isPopupOpen()) searchResultMarker.closePopup();

                    console.log("LRM control initialized.");
                })
                .catch(error => {
                    console.error("Error setting up LRM waypoints:", error);
                    alert("Error setting up route: " + error.message);
                });
        });
    }
    // Basic LRM demo is commented out.
}

function showLocationOnMap(lat, lon, name) {
    if (!mapInstance) return;

    if (searchResultMarker && mapInstance.hasLayer(searchResultMarker)) {
        mapInstance.removeLayer(searchResultMarker);
    }
    // Custom icon for searched/selected location
    const customIcon = L.divIcon({
        className: 'custom-location-marker', // Defined in dashboard.html styles
        iconSize: [15, 15],
        iconAnchor: [7, 7]
    });

    searchResultMarker = L.marker([lat, lon], { icon: customIcon }).addTo(mapInstance);

    let popupContent = `<b>${name}</b><br>Lat: ${lat.toFixed(5)}, Lon: ${lon.toFixed(5)}`;
    // Assuming a global function setAsDestination is available from the original code
    // It might need locationId, so if the location object has it, it could be passed to showLocationOnMap
    // For now, this just shows coords. If loc.location_id is available, it can be used for setAsDestination.

    searchResultMarker.bindPopup(popupContent).openPopup();
    mapInstance.setView([lat, lon], 18); // Zoom in closer
}


function displayLocationSuggestions(query, resultsContainer, inputField, suggestionType) {
    if (!query || query.length < 2) { // Minimum 2 chars for text, coordinates will also be > 2 ("1,1")
        resultsContainer.innerHTML = '';
        resultsContainer.style.display = 'none';
        return;
    }

    fetch(`${SEARCH_LOCATIONS_URL}?q=${encodeURIComponent(query)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Network response was not ok: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            resultsContainer.innerHTML = ''; // Clear previous results
            if (data.locations && data.locations.length > 0) {
                const ul = document.createElement('ul');
                ul.className = 'list-group';
                data.locations.forEach(loc => {
                    const li = document.createElement('li');
                    li.className = 'list-group-item list-group-item-action';
                    let displayText = loc.name;
                    if (data.search_type_performed === 'coordinate' && loc.distance_meters !== undefined) {
                        displayText += ` <small class="text-muted">(${loc.distance_meters}m away)</small>`;
                    }
                    li.innerHTML = displayText; // Use innerHTML to render the small tag
                    li.addEventListener('click', function() {
                        inputField.value = loc.name;
                        resultsContainer.innerHTML = '';
                        resultsContainer.style.display = 'none';

                        if (suggestionType === 'start') {
                            selectedStartLocationId = loc.location_id;
                            selectedStartLocationName = loc.name;
                            selectedStartCoords = { lat: loc.latitude, lon: loc.longitude }; // Store coords too
                            document.getElementById('useCurrentLocationCheck').checked = false;
                            startPointInput.disabled = false;
                        } else if (suggestionType === 'destination') {
                            selectedEndLocationId = loc.location_id;
                            selectedEndLocationName = loc.name;
                            selectedEndCoords = { lat: loc.latitude, lon: loc.longitude }; // Store coords too
                        }
                        // For 'general' search, or any type, show it on map
                        showLocationOnMap(loc.latitude, loc.longitude, loc.name);
                    });
                    ul.appendChild(li);
                });
                resultsContainer.appendChild(ul);
                resultsContainer.style.display = 'block';
            } else {
                if (data.message){
                     resultsContainer.innerHTML = `<p class="list-group-item text-muted">${data.message}</p>`;
                } else {
                    resultsContainer.innerHTML = '<p class="list-group-item text-muted">No locations found.</p>';
                }
                resultsContainer.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error fetching location suggestions:', error);
            resultsContainer.innerHTML = '<p class="list-group-item text-danger">Error loading suggestions.</p>';
            resultsContainer.style.display = 'block';
        });
}

// Custom Router for Leaflet Routing Machine
const CustomRouter = L.Class.extend({
    initialize: function(options) { L.Util.setOptions(this, options); },
    route: function(waypoints, callback, context, options) {
        const fromLatLng = waypoints[0].latLng;
        const toLatLng = waypoints[1].latLng;
        const body = {
            from_latitude: fromLatLng.lat, from_longitude: fromLatLng.lng,
            to_latitude: toLatLng.lat, to_longitude: toLatLng.lng,
        };
        fetch(GET_DIRECTIONS_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
            body: JSON.stringify(body)
        })
        .then(response => { if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`); return response.json(); })
        .then(data => {
            if (data.success && data.routes && data.routes.length > 0) {
                const routes = data.routes.map(beRoute => {
                    const summary = beRoute.summary || { totalDistance: 0, totalTime: 0 };
                    return {
                        name: beRoute.name || "Route",
                        summary: { totalTime: summary.totalTime || 0, totalDistance: summary.totalDistance || 0 },
                        coordinates: beRoute.coordinates ? beRoute.coordinates.map(c => L.latLng(c[0], c[1])) : [],
                        waypoints: beRoute.waypoints ? beRoute.waypoints.map(wp => L.latLng(wp[0], wp[1])) : [],
                        instructions: beRoute.instructions ? beRoute.instructions.map(instr => ({ type: 'Feature', properties: instr, geometry: { type: 'Point', coordinates: [] } })) : []
                    };
                });
                callback.call(context, null, routes);
            } else {
                const errorMessage = data.error || "Could not retrieve route from the server.";
                console.error("CustomRouter Error:", errorMessage);
                alert(`Routing Error: ${errorMessage}`); // More prominent alert
                callback.call(context, { status: -1, message: errorMessage });
            }
        })
        .catch(error => {
            const networkErrorMessage = `Network error or server unavailable: ${error.message}`;
            console.error("CustomRouter Network Error:", networkErrorMessage);
            alert(`Routing Error: ${networkErrorMessage}`); // More prominent alert
            callback.call(context, { status: -1, message: networkErrorMessage });
        });
        return this;
    }
});

function setClickedPointAsStart() {
    if (clickedLat === null || clickedLng === null) return;
    selectedStartCoords = { lat: clickedLat, lon: clickedLng };
    selectedStartLocationId = null; // Clear ID selection
    selectedStartLocationName = '';
    const startInput = document.getElementById('startPointInput');
    if (startInput) {
        startInput.value = `Pin: ${clickedLat.toFixed(5)}, ${clickedLng.toFixed(5)}`;
        startInput.disabled = false;
    }
    document.getElementById('useCurrentLocationCheck').checked = false;
    document.getElementById('startPointResults').innerHTML = '';
    if (clickedPointMarker && clickedPointMarker.isPopupOpen()) clickedPointMarker.closePopup();
}

function setClickedPointAsDestination() {
    if (clickedLat === null || clickedLng === null) return;
    selectedEndCoords = { lat: clickedLat, lon: clickedLng };
    selectedEndLocationId = null; // Clear ID selection
    selectedEndLocationName = '';
    const destInput = document.getElementById('destinationPointInput');
    if (destInput) destInput.value = `Pin: ${clickedLat.toFixed(5)}, ${clickedLng.toFixed(5)}`;
    document.getElementById('destinationPointResults').innerHTML = '';
    if (clickedPointMarker && clickedPointMarker.isPopupOpen()) clickedPointMarker.closePopup();
}

function handlePositionUpdate(position) { /* ... existing ... */ }

function updateUserMarkerOnMap(lat, lng, accuracy, heading) {
    if (!mapInstance) return;
    const rawLatLng = L.latLng(lat, lng);
    let displayLatLng = rawLatLng;
    // Snapping logic and off-route notification based on old currentRoutePolyline is removed.
    // If needed, these would be re-implemented to work with LRM's route.
    const userIcon = L.divIcon({ className: 'live-position-marker', iconSize: [18, 18], iconAnchor: [9, 9] });
    if (userLivePositionMarker) {
        userLivePositionMarker.setLatLng(displayLatLng);
    } else {
        userLivePositionMarker = L.marker(displayLatLng, { icon: userIcon, zIndexOffset: 1000, keyboard: false }).addTo(mapInstance);
    }
    if (accuracy != null) {
        if (userAccuracyCircle) {
            userAccuracyCircle.setLatLng(rawLatLng).setRadius(accuracy);
        } else {
            userAccuracyCircle = L.circle(rawLatLng, { radius: accuracy, weight: 1, color: '#007bff', fillColor: '#007bff', fillOpacity: 0.1 }).addTo(mapInstance);
        }
    } else {
        if (userAccuracyCircle && mapInstance.hasLayer(userAccuracyCircle)) { mapInstance.removeLayer(userAccuracyCircle); userAccuracyCircle = null; }
    }
}

function handlePositionError(error) { /* ... existing ... */ }
function startWatchingPosition() { /* ... existing ... */ }
function stopWatchingPosition() { /* ... existing ... */ }
// function toggleFollowMeMode() { /* ... existing ... */ } // Removed
function showOffRouteNotification(distance) { /* ... existing ... */ }
function hideOffRouteNotification() { /* ... existing ... */ }

function triggerRouteRecalculation() {
    if (currentUserLat == null || currentUserLng == null) {
        alert("Current location not available for recalculation."); return;
    }
    if (!lrmControl || !originalDestination || originalDestination.to_lat == null || originalDestination.to_lon == null) {
        alert("Cannot recalculate: LRM control or complete original destination details not available."); return;
    }
    const startLatLng = L.latLng(currentUserLat, currentUserLng);
    const endLatLng = L.latLng(originalDestination.to_lat, originalDestination.to_lon);
    lrmControl.setWaypoints([startLatLng, endLatLng]);
    hideOffRouteNotification();
}

function getClosestPointOnPolyline(polyline, latLng) { /* ... existing ... */ }
function ensureMapInstance() { /* ... existing ... */ }
function showLocation(locationId) { /* ... existing ... */ }
// function getOriginForNavigation(callback) { /* ... potentially less used ... */ }
// function fetchAndDisplayRoute(navigationParams) { /* COMMENTED OUT - Replaced by LRM */ }

window.setAsDestination = function(destinationId, destLat, destLng) { // Used by showLocation popup
    if (!ensureMapInstance() || !L.Routing) { alert("Map or Routing library not ready."); return; }
    if (mapInstance.closePopup) mapInstance.closePopup();

    let startLatLngPromise;
    if (currentUserLat != null && currentUserLng != null) {
        startLatLngPromise = Promise.resolve({ latlng: L.latLng(currentUserLat, currentUserLng), name: "Current Location" });
    } else { // Fallback to default origin if current location isn't available
        startLatLngPromise = getLocationCoordinates(DEFAULT_ORIGIN_ID_PLACEHOLDER) // Assuming DEFAULT_ORIGIN_ID_PLACEHOLDER is a valid ID
            .catch(err => {
                console.error("Default start location fetch failed:", err);
                alert("Could not determine start location for navigation.");
                return null;
            });
    }

    Promise.all([startLatLngPromise, getLocationCoordinates(destinationId)])
        .then(([startData, endData]) => {
            if (!startData || !startData.latlng || !endData || !endData.latlng) {
                alert("Could not set LRM destination due to missing start/end coordinates.");
                return;
            }
            if (lrmControl) {
                lrmControl.setWaypoints([startData.latlng, endData.latlng]);
            } else {
                 lrmControl = L.Routing.control({
                    waypoints: [startData.latlng, endData.latlng],
                    router: new CustomRouter(), show: true
                }).addTo(mapInstance);
            }
            originalDestination = { // Update context for recalc
                from_lat: startData.latlng.lat, from_lon: startData.latlng.lng, from_name: startData.name,
                to_id: destinationId, to_lat: endData.latlng.lat, to_lon: endData.latlng.lng, to_name: endData.name
            };
        })
        .catch(error => {
            console.error("Error in setAsDestination for LRM:", error);
            alert("Error setting LRM destination: " + error.message);
        });
};

window.locateMe = function() { /* ... existing ... */ };
window.zoomIn = function() { /* ... existing ... */ };
window.zoomOut = function() { /* ... existing ... */ };
window.showRecommendationOnMap = function(locationId, mediaUrl) { /* ... existing ... */ };
function loadAndDisplayGeofences() { /* ... existing ... */ }

// function startManualRouteDrawing() { // REMOVED
//     if (!ensureMapInstance()) { alert("Map is not available for drawing."); return; }
//     if (lrmControl) { // Clear LRM if active
//         if (typeof lrmControl.remove === 'function') lrmControl.remove();
//         lrmControl = null;
//     }
//     isDrawingManualRoute = true;
//     manualRoutePoints = [];
//     if (manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) mapInstance.removeLayer(manualRoutePolyline);
//     manualRoutePolyline = null;
//     if (mapInstance._container) mapInstance._container.style.cursor = 'crosshair';
//     const startDrawBtn = document.getElementById('startDrawRouteBtn'); if (startDrawBtn) startDrawBtn.disabled = true;
//     const finishDrawBtn = document.getElementById('finishDrawRouteBtn'); if (finishDrawBtn) finishDrawBtn.disabled = false;
//     const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn'); if (cancelDrawBtn) cancelDrawBtn.disabled = false;
//     console.log("Manual route drawing started. LRM control (if any) cleared.");
// }
// function updateManualRoutePolyline() { /* ... existing ... */ } // REMOVED (part of manual drawing)
// function finishManualRouteDrawing() { /* ... existing ... */ } // REMOVED
// window.cancelManualRouteDrawing = function() { /* ... existing ... */ }; // REMOVED

window.clearAllMapRoutes = function() {
    if (!ensureMapInstance()) { console.warn("Map not available to clear routes."); return; }
    if (lrmControl) { // Clear LRM route/control
        if (typeof lrmControl.remove === 'function') lrmControl.remove();
        lrmControl = null;
        console.log("LRM control cleared.");
    }
    // if (manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) { // Clear manual route - REMOVED
    //     mapInstance.removeLayer(manualRoutePolyline);
    //     console.log("Manual route polyline cleared.");
    // }
    // manualRoutePolyline = null; manualRoutePoints = []; // REMOVED
    // isDrawingManualRoute = false; // REMOVED
    if (mapInstance._container) mapInstance._container.style.cursor = '';
    // const startDrawBtn = document.getElementById('startDrawRouteBtn'); if (startDrawBtn) startDrawBtn.disabled = false; // REMOVED
    // const finishDrawBtn = document.getElementById('finishDrawRouteBtn'); if (finishDrawBtn) finishDrawBtn.disabled = true; // REMOVED
    // const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn'); if (cancelDrawBtn) cancelDrawBtn.disabled = true; // REMOVED
    console.log("All map routes cleared. Drawing mode reset.");
};

document.addEventListener('DOMContentLoaded', function() {
    // const finishDrawBtn = document.getElementById('finishDrawRouteBtn'); if (finishDrawBtn) finishDrawBtn.disabled = true; // REMOVED
    // const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn'); if (cancelDrawBtn) cancelDrawBtn.disabled = true; // REMOVED
});
[end of endlessWorld/collage_nav/static/js/dashboard_map.js]
