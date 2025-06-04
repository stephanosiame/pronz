// Main JavaScript for the application
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Dark mode toggle
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
        darkModeToggle.addEventListener('change', function() {
            document.body.classList.toggle('dark-mode');
            // You would typically also save this preference to the server
        });
    }
    
    // Initialize any map functionality
    if (typeof initMap === 'function') {
        initMap();
    }
});

// Function to handle location updates
function updateUserLocation(latitude, longitude) {
    // In a real implementation, you would send this to the server
    console.log(`Location updated: ${latitude}, ${longitude}`);
    
    // You would typically use fetch() to send this to your Django backend
    fetch('/api/update-location/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            latitude: latitude,
            longitude: longitude
        })
    }).then(response => response.json())
      .then(data => {
          if (data.success) {
              console.log('Location saved successfully');
          }
      });
}

// Helper function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}