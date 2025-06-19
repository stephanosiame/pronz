let mapInstance = null;

// New global variables for manual route drawing
let isDrawingManualRoute = false;
let manualRoutePoints = [];
let manualRoutePolyline = null;

// These variables were global in dashboard.html, ensure they are accessible within this module
// or passed as parameters where needed.
let currentRoutePolyline = null;
let animatedNavigationMarker = null;
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
let followMeActive = false;
const OFF_ROUTE_THRESHOLD_METERS = 25;
const VISUAL_SNAP_THRESHOLD_METERS = 15;
let isCurrentlyNotifyingOffRoute = false;
let originalDestination = null;

// This function is expected to be called by the Folium map's generated HTML
// Make sure this function is globally accessible if called from outside this module,
// or adjust how Folium calls it. For now, assuming it's globally available via window.initCustomMapLogic
window.initCustomMapLogic = function(generatedMapId) {
    console.log("initCustomMapLogic called with map ID:", generatedMapId);

    if (window[generatedMapId] && typeof window[generatedMapId].getCenter === 'function') {
        console.log("SUCCESS: Folium map instance found in initCustomMapLogic using ID:", generatedMapId);
        mapInstance = window[generatedMapId];

        if (mapInstance.getCenter) {
            console.log("Map center from initCustomMapLogic:", mapInstance.getCenter());
        }

    } else {
        console.error("ERROR: initCustomMapLogic was called, but window[generatedMapId] is not a valid map object.", generatedMapId);
        if (window.map_map && typeof window.map_map.getCenter === 'function') {
            console.warn("Found 'window.map_map' as fallback in initCustomMapLogic.");
            mapInstance = window.map_map;
        } else {
             for (let key in window) {
                if (key.startsWith("map_") && key !== generatedMapId && window[key] && typeof window[key].getCenter === 'function') {
                    console.warn(`Found map instance by iteration as '${key}' in initCustomMapLogic fallback.`);
                    mapInstance = window[key];
                    break;
                }
            }
        }
    }

    if (!mapInstance) {
        console.error("CRITICAL: Map instance still not found even after initCustomMapLogic was called and fallbacks attempted.");
        // alert("Map critical initialization error. Please refresh.");
    } else {
        // Basic map event listeners
        mapInstance.on('click', function(e) {
            if (isDrawingManualRoute) {
                manualRoutePoints.push(e.latlng);
                updateManualRoutePolyline();
                // Prevent default click behavior (showing set start/destination popup)
                return;
            }
            // Else (if not in drawing mode):
            if (followMeActive) {
                toggleFollowMeMode();
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

        mapInstance.on('dragstart', function() {
            if (followMeActive) {
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

        // Start watching position and load geofences (can be here if they don't depend on MovingMarker)
        console.log("initCustomMapLogic: Map instance confirmed. Calling startWatchingPosition().");
        startWatchingPosition();
        console.log("initCustomMapLogic: Calling loadAndDisplayGeofences after startWatchingPosition.");
        loadAndDisplayGeofences();

        // Dynamically load Leaflet.MovingMarker
        console.log("Map instance confirmed. Dynamically loading leaflet.movingmarker.js...");
        const movingMarkerScript = document.createElement('script');
        movingMarkerScript.src = LEAFLET_MOVINGMARKER_JS_URL; // Use the global constant
        movingMarkerScript.onload = function() {
            console.log("leaflet.movingmarker.js loaded successfully.");
            if (typeof L.Marker.movingMarker === 'function') {
                console.log("L.Marker.movingMarker is now defined.");
                initializeDashboardAppLogic(); // Initialize the rest of the app logic
            } else {
                console.error("L.Marker.movingMarker is STILL NOT defined after loading script!");
                alert("Critical error: MovingMarker plugin did not initialize correctly.");
            }
        };
        movingMarkerScript.onerror = function() {
            console.error("Error loading leaflet.movingmarker.js dynamically.");
            alert("Error loading essential map component (MovingMarker). Some features may not work.");
        };
        document.head.appendChild(movingMarkerScript);
    }
}


function initializeDashboardAppLogic() {
    if (!mapInstance && DYNAMIC_MAP_ID_FROM_DJANGO) {
        if(window[DYNAMIC_MAP_ID_FROM_DJANGO] && typeof window[DYNAMIC_MAP_ID_FROM_DJANGO].getCenter === 'function') {
            mapInstance = window[DYNAMIC_MAP_ID_FROM_DJANGO];
            // This fallback for mapInstance might be redundant if initCustomMapLogic is robust
            // and if MovingMarker loaded, mapInstance should already be set.
            // However, keeping parts of the original DOMContentLoaded logic related to mapInstance check.
            // The calls to startWatchingPosition and loadAndDisplayGeofences might be duplicative
            // if initCustomMapLogic already handled them. Consider removing if they are.
            if (!isWatchingPosition && mapInstance) { // Check if already started
                 console.warn("initializeDashboardAppLogic: Fallback map found, GPS not started. Starting now.");
                 startWatchingPosition();
                 loadAndDisplayGeofences(); // Ensure geofences are loaded if map found this way
            }
        }
    } else if (mapInstance) {
        // If mapInstance was set by initCustomMapLogic, and MovingMarker loaded,
        // then startWatchingPosition and loadAndDisplayGeofences should ideally have been called.
        // This is a safety check.
        if (!isWatchingPosition) {
            console.warn("initializeDashboardAppLogic: mapInstance set, but GPS not started. Starting now (possible race condition).");
            startWatchingPosition();
            loadAndDisplayGeofences(); // Ensure geofences loaded
        }
    }

    const followMeButton = document.getElementById('toggleFollowMe');
    if (followMeButton) followMeButton.addEventListener('click', toggleFollowMeMode);

    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.trim();
            const resultsContainer = document.getElementById('searchResults');
            if (query.length >= 2) {
                fetch(`${SEARCH_LOCATIONS_URL}?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        resultsContainer.innerHTML = '';
                        if (data.locations.length > 0) {
                            data.locations.forEach(location => {
                                const item = document.createElement('a');
                                item.href = '#';
                                item.className = 'list-group-item list-group-item-action';
                                item.innerHTML = `<h6>${location.name}</h6><small class="text-muted">${location.location_type}</small><p class="mb-1">${location.description || ''}</p>`;
                                item.addEventListener('click', (e) => {
                                    e.preventDefault();
                                    showLocation(location.location_id);
                                });
                                resultsContainer.appendChild(item);
                            });
                        } else {
                            resultsContainer.innerHTML = '<div class="list-group-item">No results found</div>';
                        }
                    });
            } else {
                 resultsContainer.innerHTML = '';
            }
        });
    }

    const searchForm = document.getElementById('searchForm');
    if (searchForm) searchForm.addEventListener('submit', (e) => e.preventDefault());

    const startPointInput = document.getElementById('startPointInput');
    const startPointResults = document.getElementById('startPointResults');
    const destinationPointInput = document.getElementById('destinationPointInput');
    const destinationPointResults = document.getElementById('destinationPointResults');

    function displayLocationSuggestions(query, resultsContainer, onSelectCallback) {
        if (query.length < 2) {
            resultsContainer.innerHTML = ''; return;
        }
        fetch(`${SEARCH_LOCATIONS_URL}?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                resultsContainer.innerHTML = '';
                if (data.locations && data.locations.length > 0) {
                    data.locations.forEach(location => {
                        const item = document.createElement('a');
                        item.href = '#';
                        item.className = 'list-group-item list-group-item-action';
                        item.textContent = location.name;
                        item.addEventListener('click', (e) => {
                            e.preventDefault();
                            onSelectCallback(location.location_id, location.name);
                            resultsContainer.innerHTML = '';
                        });
                        resultsContainer.appendChild(item);
                    });
                } else {
                    resultsContainer.innerHTML = '<div class="list-group-item disabled">No results found</div>';
                }
            })
            .catch(error => console.error('Error fetching location suggestions:', error));
    }

    if (startPointInput) {
        startPointInput.addEventListener('input', function() {
            selectedStartLocationId = null;
            selectedStartLocationName = '';
            selectedStartCoords = null;
            displayLocationSuggestions(this.value, startPointResults, (locationId, locationName) => {
                selectedStartLocationId = locationId;
                selectedStartLocationName = locationName;
                startPointInput.value = locationName;
                const useCurrentChk = document.getElementById('useCurrentLocationCheck');
                if(useCurrentChk) useCurrentChk.checked = false;
                startPointInput.disabled = false;
            });
        });
    }

    if (destinationPointInput) {
        destinationPointInput.addEventListener('input', function() {
            selectedEndLocationId = null;
            selectedEndLocationName = '';
            selectedEndCoords = null;
            displayLocationSuggestions(this.value, destinationPointResults, (locationId, locationName) => {
                selectedEndLocationId = locationId;
                selectedEndLocationName = locationName;
                destinationPointInput.value = locationName;
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
                selectedStartCoords = null;
                startPointResults.innerHTML = '';
            } else {
                startPointInput.disabled = false;
                if (startPointInput.value === "Using current location") startPointInput.value = "";
            }
        });
    }

    const getDirectionsButton = document.getElementById('getDirectionsButton');
    if (getDirectionsButton) {
        getDirectionsButton.addEventListener('click', function() {
            const startSelected = selectedStartLocationId || selectedStartCoords || (useCurrentLocationCheck && useCurrentLocationCheck.checked);
            const endSelected = selectedEndLocationId || selectedEndCoords;

            if (!endSelected) { alert("Please select a destination point."); return; }
            if (!startSelected) { alert("Please select a start point."); return; }

            let navigationParams = {};
            if (selectedEndCoords) {
                navigationParams.to_latitude = selectedEndCoords.lat;
                navigationParams.to_longitude = selectedEndCoords.lon;
                navigationParams.to_name = `Map Pin: ${selectedEndCoords.lat.toFixed(5)}, ${selectedEndCoords.lon.toFixed(5)}`;
            } else if (selectedEndLocationId) {
                navigationParams.to_id = selectedEndLocationId;
                navigationParams.to_name = selectedEndLocationName;
            }

            if (useCurrentLocationCheck && useCurrentLocationCheck.checked) {
                getOriginForNavigation(function(origin) {
                    if (origin.type === 'error') { alert(`Could not determine current location: ${origin.message}`); return; }
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
            } else if (selectedStartCoords) {
                navigationParams.from_latitude = selectedStartCoords.lat;
                navigationParams.from_longitude = selectedStartCoords.lon;
                navigationParams.from_name = `Map Pin: ${selectedStartCoords.lat.toFixed(5)}, ${selectedStartCoords.lon.toFixed(5)}`;
                fetchAndDisplayRoute(navigationParams);
            } else if (selectedStartLocationId) {
                navigationParams.from_id = selectedStartLocationId;
                navigationParams.from_name = selectedStartLocationName;
                fetchAndDisplayRoute(navigationParams);
            }
        });
    }
}

function setClickedPointAsStart() {
    if (clickedLat === null || clickedLng === null) return;
    selectedStartCoords = { lat: clickedLat, lon: clickedLng };
    selectedStartLocationId = null;
    selectedStartLocationName = '';
    const startInput = document.getElementById('startPointInput');
    if (startInput) {
        startInput.value = `Map Pin: ${clickedLat.toFixed(5)}, ${clickedLng.toFixed(5)}`;
        startInput.disabled = false;
    }
    const useCurrentCheck = document.getElementById('useCurrentLocationCheck');
    if (useCurrentCheck) useCurrentCheck.checked = false;
    const startResults = document.getElementById('startPointResults');
    if (startResults) startResults.innerHTML = '';
    console.log("Map click set as Start:", selectedStartCoords);
    if (clickedPointMarker && clickedPointMarker.isPopupOpen()) clickedPointMarker.closePopup();
}

function setClickedPointAsDestination() {
    if (clickedLat === null || clickedLng === null) return;
    selectedEndCoords = { lat: clickedLat, lon: clickedLng };
    selectedEndLocationId = null;
    selectedEndLocationName = `Map Pin: ${clickedLat.toFixed(5)}, ${clickedLng.toFixed(5)}`;
    const destInput = document.getElementById('destinationPointInput');
    if (destInput) destInput.value = selectedEndLocationName;
    const destResults = document.getElementById('destinationPointResults');
    if (destResults) destResults.innerHTML = '';
    console.log("Map click set as Destination:", selectedEndCoords);
    if (clickedPointMarker && clickedPointMarker.isPopupOpen()) clickedPointMarker.closePopup();
}

function handlePositionUpdate(position) {
    currentUserLat = position.coords.latitude;
    currentUserLng = position.coords.longitude;
    currentUserAccuracy = position.coords.accuracy;
    currentUserHeading = position.coords.heading;
    currentUserSpeed = position.coords.speed;
    console.log(`Live Update: Lat: ${currentUserLat}, Lng: ${currentUserLng}, Acc: ${currentUserAccuracy}m, Head: ${currentUserHeading}, Spd: ${currentUserSpeed}`);
    updateUserMarkerOnMap(currentUserLat, currentUserLng, currentUserAccuracy, currentUserHeading);
    if (followMeActive && mapInstance) {
        mapInstance.panTo([currentUserLat, currentUserLng]);
    }
}

function updateUserMarkerOnMap(lat, lng, accuracy, heading) {
    if (!mapInstance) {
        console.warn("updateUserMarkerOnMap called before mapInstance is ready.");
        return;
    }
    const rawLatLng = L.latLng(lat, lng);
    let displayLatLng = rawLatLng;
    let actualSnappedPoint = null;

    if (currentRoutePolyline && typeof currentRoutePolyline.getLatLngs === 'function' && currentRoutePolyline.getLatLngs().length > 0) {
        actualSnappedPoint = getClosestPointOnPolyline(currentRoutePolyline, rawLatLng);
        if (actualSnappedPoint) {
            if (rawLatLng.distanceTo(actualSnappedPoint) < VISUAL_SNAP_THRESHOLD_METERS) {
                displayLatLng = actualSnappedPoint;
            } else {
                displayLatLng = rawLatLng;
            }
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
        } else {
            displayLatLng = rawLatLng;
            if (isCurrentlyNotifyingOffRoute) {
                hideOffRouteNotification();
            }
        }
    } else {
        displayLatLng = rawLatLng;
        if (isCurrentlyNotifyingOffRoute) {
            hideOffRouteNotification();
        }
    }

    const userIcon = L.divIcon({
        className: 'live-position-marker',
        iconSize: [18, 18],
        iconAnchor: [9, 9]
    });

    if (userLivePositionMarker) {
        userLivePositionMarker.setLatLng(displayLatLng);
    } else {
        userLivePositionMarker = L.marker(displayLatLng, {
            icon: userIcon,
            zIndexOffset: 1000,
            keyboard: false
        }).addTo(mapInstance);
    }

    if (accuracy != null) {
        if (userAccuracyCircle) {
            userAccuracyCircle.setLatLng(rawLatLng).setRadius(accuracy);
        } else {
            userAccuracyCircle = L.circle(rawLatLng, {
                radius: accuracy,
                weight: 1,
                color: '#007bff',
                fillColor: '#007bff',
                fillOpacity: 0.1
            }).addTo(mapInstance);
        }
    } else {
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
            alert("Geolocation permission denied. Live location updates will be disabled.");
            stopWatchingPosition();
            break;
        case error.POSITION_UNAVAILABLE: console.error("Location information is unavailable."); break;
        case error.TIMEOUT: console.error("The request to get user location timed out."); break;
        default: console.error("An unknown error occurred with geolocation."); break;
    }
}

function startWatchingPosition() {
    if (navigator.geolocation) {
        if (currentPositionWatcherId) {
            navigator.geolocation.clearWatch(currentPositionWatcherId);
        }
        const options = { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 };
        currentPositionWatcherId = navigator.geolocation.watchPosition(handlePositionUpdate, handlePositionError, options);
        isWatchingPosition = true;
        console.log("Started watching position. Watcher ID:", currentPositionWatcherId);
    } else {
        alert("Geolocation is not supported by this browser. Live location updates will not be available.");
    }
}

function stopWatchingPosition() {
    if (navigator.geolocation && currentPositionWatcherId) {
        navigator.geolocation.clearWatch(currentPositionWatcherId);
        currentPositionWatcherId = null;
        isWatchingPosition = false;
    }
}

function toggleFollowMeMode() {
    followMeActive = !followMeActive;
    const button = document.getElementById('toggleFollowMe');
    if (button) {
        if (followMeActive) {
            button.textContent = 'Follow Me: On';
            button.classList.remove('btn-secondary');
            button.classList.add('btn-success');
            if (currentUserLat && currentUserLng && mapInstance) {
                mapInstance.panTo([currentUserLat, currentUserLng]);
                if (mapInstance.getZoom() < 17) mapInstance.setZoom(17);
            }
        } else {
            button.textContent = 'Follow Me: Off';
            button.classList.remove('btn-success');
            button.classList.add('btn-secondary');
        }
    }
}

function showOffRouteNotification(distance) {
    isCurrentlyNotifyingOffRoute = true;
    const offRouteDiv = document.getElementById('offRouteNotification');
    if (offRouteDiv) {
        offRouteDiv.innerHTML = `You seem to be about <strong>${Math.round(distance)}m</strong> off route. <span id='recalculateRouteLink' style='text-decoration:underline; cursor:pointer; color:blue;'>Recalculate?</span>`;
        offRouteDiv.style.display = 'block';
        const recalcLink = document.getElementById('recalculateRouteLink');
        if (recalcLink) recalcLink.onclick = triggerRouteRecalculation;
    }
}

function hideOffRouteNotification() {
    isCurrentlyNotifyingOffRoute = false;
    const offRouteDiv = document.getElementById('offRouteNotification');
    if (offRouteDiv) offRouteDiv.style.display = 'none';
}

function triggerRouteRecalculation() {
    if (currentUserLat == null || currentUserLng == null) {
        alert("Cannot recalculate: Your current location is not available yet."); return;
    }
    if (!originalDestination) {
        alert("Cannot recalculate: Original destination details were not properly stored."); return;
    }
    const newNavParams = {
        from_latitude: currentUserLat,
        from_longitude: currentUserLng,
        from_name: "Your Current Location"
    };
    if (originalDestination.id) {
        newNavParams.to_id = originalDestination.id;
        newNavParams.to_name = originalDestination.name;
    } else if (originalDestination.lat != null && originalDestination.lon != null) {
        newNavParams.to_latitude = originalDestination.lat;
        newNavParams.to_longitude = originalDestination.lon;
        newNavParams.to_name = originalDestination.name;
    } else {
        alert("Cannot recalculate: Original destination details are invalid."); return;
    }
    fetchAndDisplayRoute(newNavParams);
    hideOffRouteNotification();
}

function getClosestPointOnPolyline(polyline, latLng) {
    if (!polyline || typeof polyline.getLatLngs !== 'function') return latLng;
    const polylineLatLngs = polyline.getLatLngs();
    if (polylineLatLngs.length < 2) return latLng;

    let minDistanceSq = Infinity;
    let closestPoint = null;
    const pX = latLng.lng;
    const pY = latLng.lat;

    for (let i = 0; i < polylineLatLngs.length - 1; i++) {
        let p1 = polylineLatLngs[i];
        let p2 = polylineLatLngs[i+1];
        const p1X = p1.lng; const p1Y = p1.lat;
        const p2X = p2.lng; const p2Y = p2.lat;
        const segLengthSq = (p2X - p1X) * (p2X - p1X) + (p2Y - p1Y) * (p2Y - p1Y);

        if (segLengthSq === 0) {
            const distSq = (pX - p1X) * (pX - p1X) + (pY - p1Y) * (pY - p1Y);
            if (distSq < minDistanceSq) {
                minDistanceSq = distSq;
                closestPoint = L.latLng(p1Y, p1X);
            }
            continue;
        }
        const t = ((pX - p1X) * (p2X - p1X) + (pY - p1Y) * (p2Y - p1Y)) / segLengthSq;
        let currentClosestX, currentClosestY;
        if (t < 0) { currentClosestX = p1X; currentClosestY = p1Y; }
        else if (t > 1) { currentClosestX = p2X; currentClosestY = p2Y; }
        else { currentClosestX = p1X + t * (p2X - p1X); currentClosestY = p1Y + t * (p2Y - p1Y); }
        const distToCurrentClosestSq = (pX - currentClosestX) * (pX - currentClosestX) + (pY - currentClosestY) * (pY - currentClosestY);
        if (distToCurrentClosestSq < minDistanceSq) {
            minDistanceSq = distToCurrentClosestSq;
            closestPoint = L.latLng(currentClosestY, currentClosestX);
        }
    }
    return closestPoint || latLng;
}

// Remove the old document.addEventListener('DOMContentLoaded', function() { ... }); block entirely.

function ensureMapInstance() {
    if (!mapInstance) {
        if (window[DYNAMIC_MAP_ID_FROM_DJANGO] && typeof window[DYNAMIC_MAP_ID_FROM_DJANGO].getCenter === 'function') {
             mapInstance = window[DYNAMIC_MAP_ID_FROM_DJANGO];
        } else {
             console.error("ensureMapInstance: Could not acquire mapInstance.");
             return null;
        }
    }
    return mapInstance;
}

function showLocation(locationId) {
    if (!ensureMapInstance()) { alert("Map is not available to display location."); return; }
    fetch(`${LOCATION_DETAILS_API_BASE_URL}${locationId}/`)
        .then(response => response.json())
        .then(locationData => {
            if (locationData.success && locationData.latitude && locationData.longitude) {
                const lat = locationData.latitude;
                const lon = locationData.longitude;
                mapInstance.panTo([lat, lon]);
                mapInstance.setZoom(18);
                if (searchResultMarker) mapInstance.removeLayer(searchResultMarker);
                const popupContent = `<b>${locationData.name}</b><br>Searched Location<hr><button class="btn btn-sm btn-primary w-100" onclick="setAsDestination('${locationId}', ${lat}, ${lon})">Navigate to Here</button>`;
                searchResultMarker = L.marker([lat, lon], {
                    icon: L.divIcon({ className: 'custom-location-marker', iconSize: [15, 15], iconAnchor: [7, 7] })
                }).addTo(mapInstance).bindPopup(popupContent).openPopup();
                document.getElementById('map').scrollIntoView({ behavior: 'smooth' });
            } else {
                alert("Could not fetch location details: " + (locationData.error || "Unknown error"));
            }
        })
        .catch(error => alert("Error fetching location details. Please check console."));
}

function getOriginForNavigation(callback) {
    function handleFallback() {
        fetch(GET_LAST_USER_LOCATION_URL)
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                if (data.success && data.latitude && data.longitude) {
                    callback({ type: 'coords', lat: data.latitude, lon: data.longitude, from: 'last_known' });
                } else {
                    if (DEFAULT_ORIGIN_ID_PLACEHOLDER === "YOUR_COICT_CENTER_LOCATION_ID_REPLACE_ME" || (DEFAULT_ORIGIN_ID_PLACEHOLDER || "").length !== 36) {
                         alert("Developer: Default Origin ID is not configured correctly.");
                         callback({type: 'error', message: 'Default origin ID not set or invalid.'}); return;
                    }
                    callback({ type: 'id', id: DEFAULT_ORIGIN_ID_PLACEHOLDER, from: 'default_fallback' });
                }
            })
            .catch(() => {
                if (DEFAULT_ORIGIN_ID_PLACEHOLDER === "YOUR_COICT_CENTER_LOCATION_ID_REPLACE_ME" || (DEFAULT_ORIGIN_ID_PLACEHOLDER || "").length !== 36) {
                     alert("Developer: Default Origin ID is not configured correctly.");
                     callback({type: 'error', message: 'Default origin ID not set or invalid after error.'}); return;
                }
                callback({ type: 'id', id: DEFAULT_ORIGIN_ID_PLACEHOLDER, from: 'default_fallback_on_error' });
            });
    }

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            position => callback({ type: 'coords', lat: position.coords.latitude, lon: position.coords.longitude, from: 'live_geolocation' }),
            () => handleFallback(),
            { timeout: 5000, enableHighAccuracy: true }
        );
    } else {
        handleFallback();
    }
}

function fetchAndDisplayRoute(navigationParams) {
    originalDestination = {};
    if (navigationParams.to_id) {
        originalDestination.id = navigationParams.to_id;
        originalDestination.name = navigationParams.to_name || 'Destination ID: ' + navigationParams.to_id;
    } else if (navigationParams.to_latitude && navigationParams.to_longitude) {
        originalDestination.lat = navigationParams.to_latitude;
        originalDestination.lon = navigationParams.to_longitude;
        originalDestination.name = navigationParams.to_name || `Map Pin: ${navigationParams.to_latitude.toFixed(5)}, ${navigationParams.to_longitude.toFixed(5)}`;
    } else {
        originalDestination = null; // Should not happen if called correctly
    }

    if (!ensureMapInstance()) { alert("Map is not available to display the route."); return; }

    // Clear existing routes (manual and automatic)
    if (currentRoutePolyline && mapInstance.hasLayer(currentRoutePolyline)) {
        mapInstance.removeLayer(currentRoutePolyline);
    }
    currentRoutePolyline = null;

    if (animatedNavigationMarker && mapInstance.hasLayer(animatedNavigationMarker)) {
        mapInstance.removeLayer(animatedNavigationMarker);
    }
    animatedNavigationMarker = null;

    if (manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) {
        mapInstance.removeLayer(manualRoutePolyline);
    }
    manualRoutePolyline = null;
    manualRoutePoints = []; // Also reset points for manual route

    let fetchBody = {};
    if (navigationParams.to_id) fetchBody.to_id = navigationParams.to_id;
    else if (navigationParams.to_latitude && navigationParams.to_longitude) {
        fetchBody.to_latitude = navigationParams.to_latitude;
        fetchBody.to_longitude = navigationParams.to_longitude;
    } else { alert("Destination information missing."); return; }

    if (navigationParams.from_id) fetchBody.from_id = navigationParams.from_id;
    else if (navigationParams.from_latitude && navigationParams.from_longitude) {
        fetchBody.from_latitude = navigationParams.from_latitude;
        fetchBody.from_longitude = navigationParams.from_longitude;
    } else { alert("Start location information missing."); return; }

    fetch(GET_DIRECTIONS_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
        body: JSON.stringify(fetchBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const latLngs = data.route.path.map(coord => L.latLng(coord[0], coord[1]));
            if (latLngs.length < 2) { alert("Route path is too short."); return; }
            currentRoutePolyline = L.polyline(latLngs, { color: 'blue', weight: 6, opacity: 0.7 }).addTo(mapInstance);
            mapInstance.fitBounds(currentRoutePolyline.getBounds().pad(0.1));
            const pointerIcon = L.icon({ iconUrl: NAVIGATION_POINTER_IMG_URL, iconSize: [25, 41], iconAnchor: [12, 41] });
            const totalDurationMs = data.route.estimated_time * 60 * 1000;
            animatedNavigationMarker = L.Marker.movingMarker(latLngs, [totalDurationMs], { autostart: true, loop: false, icon: pointerIcon });
            animatedNavigationMarker.on('end', function() {
                if(mapInstance && latLngs.length > 0) {
                     L.marker(latLngs[latLngs.length - 1], {icon: pointerIcon})
                        .addTo(mapInstance).bindPopup(`Arrived at ${data.route.destination.name || navigationParams.to_name || 'destination'}`).openPopup();
                }
                if(mapInstance && animatedNavigationMarker) mapInstance.removeLayer(animatedNavigationMarker);
            });
            mapInstance.addLayer(animatedNavigationMarker);

            const modal = new bootstrap.Modal(document.getElementById('directionsModal'));
            const routeDetailsEl = document.getElementById('routeDetails');
            const fromName = navigationParams.from_name || data.route.source.name;
            const toName = navigationParams.to_name || data.route.destination.name;
            routeDetailsEl.innerHTML = `<h6>From: ${fromName}</h6><h6>To: ${toName}</h6><p>Distance: ${data.route.distance.toFixed(0)}m</p><p>Time: ${data.route.estimated_time} min</p><hr><h6>Steps:</h6><ol>${data.route.steps.map(step => `<li>${step.instruction} (${step.distance.toFixed(0)}m, ${Math.round(step.duration/60)} min)</li>`).join('')}</ol>`;
            modal.show();
            document.getElementById('map').scrollIntoView({ behavior: 'smooth' });
        } else {
            alert("Error getting directions: " + (data.error || 'Unknown error'));
        }
    })
    .catch(err => alert("Could not retrieve new directions. Check console."));
}

// Make sure this is callable from HTML onclick
window.setAsDestination = function(destinationId, destLat, destLng) {
    if (!ensureMapInstance()) { alert("Map is not available."); return; }
    if (mapInstance && typeof mapInstance.closePopup === 'function') mapInstance.closePopup();

    fetch(`${LOCATION_DETAILS_API_BASE_URL}${destinationId}/`)
        .then(response => response.json())
        .then(locationData => {
            const destinationName = locationData.success ? locationData.name : `ID: ${destinationId}`;
            getOriginForNavigation(function(origin) {
                if (origin.type === 'error') { alert(`Could not get origin: ${origin.message}`); return; }
                let navParams = { to_id: destinationId, to_name: destinationName };
                if (origin.type === 'coords') {
                    navParams.from_latitude = origin.lat;
                    navParams.from_longitude = origin.lon;
                    navParams.from_name = "Current Location";
                } else {
                    navParams.from_id = origin.id;
                    navParams.from_name = origin.from;
                }
                fetchAndDisplayRoute(navParams);
            });
        })
        .catch(() => { // Fallback if name fetch fails
            getOriginForNavigation(function(origin) {
                if (origin.type === 'error') { alert(`Could not get origin: ${origin.message}`); return; }
                let navParams = { to_id: destinationId, to_name: `ID: ${destinationId}` };
                 if (origin.type === 'coords') {
                    navParams.from_latitude = origin.lat;
                    navParams.from_longitude = origin.lon;
                    navParams.from_name = "Current Location";
                } else {
                    navParams.from_id = origin.id;
                    navParams.from_name = origin.from;
                }
                fetchAndDisplayRoute(navParams);
            });
        });
}

// Make sure this is callable from HTML onclick
window.locateMe = function() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            position => {
                fetch(UPDATE_LOCATION_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
                    body: JSON.stringify({ latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy })
                }).then(response => response.json()).then(data => { if (data.success) window.location.reload(); });
            },
            () => alert("Could not get your location."),
            { enableHighAccuracy: true }
        );
    } else {
        alert("Geolocation is not supported by your browser.");
    }
}

// Make sure these are callable from HTML onclick
window.zoomIn = function() { if (ensureMapInstance()) mapInstance.zoomIn(); else alert("Map not ready for zoom."); }
window.zoomOut = function() { if (ensureMapInstance()) mapInstance.zoomOut(); else alert("Map not ready for zoom."); }

// Make sure this is callable from HTML onclick
window.showRecommendationOnMap = function(locationId, mediaUrl) {
    if (!ensureMapInstance()) { alert("Map not available."); return; }
    fetch(`${LOCATION_DETAILS_API_BASE_URL}${locationId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.latitude && data.longitude) {
                const lat = data.latitude; const lon = data.longitude;
                mapInstance.panTo([lat, lon]);
                mapInstance.setZoom(18);
                if (recommendationMarker) mapInstance.removeLayer(recommendationMarker);
                recommendationMarker = L.marker([lat, lon], {
                    icon: L.divIcon({ className: 'custom-recommendation-marker', iconSize: [15, 15], iconAnchor: [7, 7] })
                }).addTo(mapInstance).bindPopup(`<b>${data.name}</b><br><img src="${mediaUrl}" alt="${data.name}" style="width:100px;height:auto;">`).openPopup();
                document.getElementById('map').scrollIntoView({ behavior: 'smooth' });
            } else {
                alert("Could not fetch recommendation location details: " + (data.error || "Unknown error"));
            }
        })
        .catch(error => alert("Error fetching recommendation details. Check console."));
}

function loadAndDisplayGeofences() {
    if (!ensureMapInstance()) {
        setTimeout(loadAndDisplayGeofences, 500); return;
    }
    fetch(GEOFENCES_API_URL)
        .then(response => {
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
        })
        .then(data => {
            if (data.geofences && data.geofences.length > 0) {
                data.geofences.forEach(gf => {
                    if (gf.boundary_geojson && mapInstance) {
                        try {
                            L.geoJSON(gf.boundary_geojson, {
                                style: () => ({color: "#FF5733", weight: 2, opacity: 0.7, fillOpacity: 0.1})
                            }).bindPopup(`<b>${gf.name}</b><br>${gf.description || 'Geofenced Area'}`).addTo(mapInstance);
                        } catch (e) { console.error("Error adding GeoJSON layer for geofence:", gf.name, e); }
                    }
                });
            }
        })
        .catch(error => console.error("Error fetching or displaying geofences:", error));
}

// Functions for manual route drawing
function startManualRouteDrawing() {
    if (!ensureMapInstance()) { alert("Map is not available for drawing."); return; }
    isDrawingManualRoute = true;
    manualRoutePoints = [];

    // Clear existing manual route polyline
    if (manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) {
        mapInstance.removeLayer(manualRoutePolyline);
    }
    manualRoutePolyline = null;

    // Clear existing automatic route and its animation
    if (currentRoutePolyline && mapInstance.hasLayer(currentRoutePolyline)) {
        mapInstance.removeLayer(currentRoutePolyline);
    }
    currentRoutePolyline = null;
    if (animatedNavigationMarker && mapInstance.hasLayer(animatedNavigationMarker)) {
        mapInstance.removeLayer(animatedNavigationMarker);
    }
    animatedNavigationMarker = null;

    // Optional: Change mouse cursor
    if (mapInstance && mapInstance._container) {
        mapInstance._container.style.cursor = 'crosshair';
    }
    // Button state handling
    const startDrawBtn = document.getElementById('startDrawRouteBtn');
    if (startDrawBtn) startDrawBtn.disabled = true;
    const finishDrawBtn = document.getElementById('finishDrawRouteBtn');
    if (finishDrawBtn) finishDrawBtn.disabled = false;
    const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn');
    if (cancelDrawBtn) cancelDrawBtn.disabled = false;

    console.log("Manual route drawing started. Previous routes cleared.");
}

function updateManualRoutePolyline() {
    if (!mapInstance) return;
    if (manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) {
        mapInstance.removeLayer(manualRoutePolyline);
    }
    if (manualRoutePoints.length >= 2) {
        manualRoutePolyline = L.polyline(manualRoutePoints, {
            color: 'red', // Distinctive color
            weight: 4,
            opacity: 0.7,
            dashArray: '5, 10' // Dashed line
        }).addTo(mapInstance);
    }
}

function finishManualRouteDrawing() {
    isDrawingManualRoute = false;
    // Optional: Change mouse cursor back to default
    if (mapInstance && mapInstance._container) {
        mapInstance._container.style.cursor = '';
    }
    // Button state handling
    const startDrawBtn = document.getElementById('startDrawRouteBtn');
    if (startDrawBtn) startDrawBtn.disabled = false;
    const finishDrawBtn = document.getElementById('finishDrawRouteBtn');
    if (finishDrawBtn) finishDrawBtn.disabled = true; // Disable until next drawing session
    const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn');
    if (cancelDrawBtn) cancelDrawBtn.disabled = true; // Disable until next drawing session

    console.log("Manual route drawing finished.");
    // The manualRoutePolyline should remain on the map.
    // Optional: if manualRoutePoints has less than 2 points, consider removing the polyline or alerting user.
    if (manualRoutePoints.length < 2 && manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) {
        mapInstance.removeLayer(manualRoutePolyline);
        manualRoutePolyline = null;
        console.log("Manual route drawing cancelled or insufficient points.");
    }
}

// Expose functions to global scope for HTML buttons
window.startManualRouteDrawing = startManualRouteDrawing;
window.finishManualRouteDrawing = finishManualRouteDrawing;
// It might be useful to have a cancel function as well
window.cancelManualRouteDrawing = function() {
    isDrawingManualRoute = false;
    manualRoutePoints = [];
    if (manualRoutePolyline && mapInstance && mapInstance.hasLayer(manualRoutePolyline)) {
        mapInstance.removeLayer(manualRoutePolyline);
    }
    manualRoutePolyline = null;
    if (mapInstance && mapInstance._container) {
        mapInstance._container.style.cursor = '';
    }
    // Button state handling
    const startDrawBtn = document.getElementById('startDrawRouteBtn');
    if (startDrawBtn) startDrawBtn.disabled = false;
    const finishDrawBtn = document.getElementById('finishDrawRouteBtn');
    if (finishDrawBtn) finishDrawBtn.disabled = true;
    const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn');
    if (cancelDrawBtn) cancelDrawBtn.disabled = true;

    console.log("Manual route drawing cancelled.");
};

// Optional but Good Practice: General function to clear all routes
window.clearAllMapRoutes = function() {
    if (!ensureMapInstance()) {
        console.warn("Map not available to clear routes.");
        return;
    }

    // Clear automatic route
    if (currentRoutePolyline && mapInstance.hasLayer(currentRoutePolyline)) {
        mapInstance.removeLayer(currentRoutePolyline);
        console.log("Automatic route polyline cleared.");
    }
    currentRoutePolyline = null;

    if (animatedNavigationMarker && mapInstance.hasLayer(animatedNavigationMarker)) {
        mapInstance.removeLayer(animatedNavigationMarker);
        console.log("Animated navigation marker cleared.");
    }
    animatedNavigationMarker = null;

    // Clear manual route
    if (manualRoutePolyline && mapInstance.hasLayer(manualRoutePolyline)) {
        mapInstance.removeLayer(manualRoutePolyline);
        console.log("Manual route polyline cleared.");
    }
    manualRoutePolyline = null;
    manualRoutePoints = [];

    // Optional: Clear other markers if desired (e.g., search results, clicked points)
    // if (searchResultMarker && mapInstance.hasLayer(searchResultMarker)) {
    //     mapInstance.removeLayer(searchResultMarker);
    //     searchResultMarker = null;
    // }
    // if (clickedPointMarker && mapInstance.hasLayer(clickedPointMarker)) {
    //     mapInstance.removeLayer(clickedPointMarker);
    //     clickedPointMarker = null;
    // }
    // if (recommendationMarker && mapInstance.hasLayer(recommendationMarker)) {
    //    mapInstance.removeLayer(recommendationMarker);
    //    recommendationMarker = null;
    // }
    // Also ensure drawing mode is fully reset if active
    isDrawingManualRoute = false;
    if (mapInstance && mapInstance._container) {
        mapInstance._container.style.cursor = ''; // Reset cursor
    }
    // Reset button states
    const startDrawBtn = document.getElementById('startDrawRouteBtn');
    if (startDrawBtn) startDrawBtn.disabled = false;
    const finishDrawBtn = document.getElementById('finishDrawRouteBtn');
    if (finishDrawBtn) finishDrawBtn.disabled = true;
    const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn');
    if (cancelDrawBtn) cancelDrawBtn.disabled = true;

    console.log("All map routes and associated markers cleared. Drawing mode reset.");
};

// Initialize button states on page load
document.addEventListener('DOMContentLoaded', function() {
    // Ensure mapInstance is available before trying to use it for button states
    // However, initial button states can be set without mapInstance.
    const finishDrawBtn = document.getElementById('finishDrawRouteBtn');
    if (finishDrawBtn) finishDrawBtn.disabled = true;
    const cancelDrawBtn = document.getElementById('cancelDrawRouteBtn');
    if (cancelDrawBtn) cancelDrawBtn.disabled = true;

    // initCustomMapLogic is already called by Folium's script tag,
    // so further map-dependent initializations should happen inside or after initCustomMapLogic
});
