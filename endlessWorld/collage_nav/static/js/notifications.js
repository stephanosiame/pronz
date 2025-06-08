// --- Notification Bell JavaScript ---
document.addEventListener('DOMContentLoaded', function() {
    const notificationBellContainer = document.getElementById('notificationBellContainer');
    // If the bell container doesn't exist (e.g., user not authenticated), do nothing.
    if (!notificationBellContainer) {
        // console.log("Notification bell container not found, skipping notification JS setup.");
        return;
    }

    const unreadCountBadge = document.getElementById('notification-count');
    const notificationDropdownMenu = document.getElementById('notificationDropdownMenu');

    // Assumes getCookie is defined in main.js and loaded before this script.
    // If not, ensure getCookie or a similar CSRF token function is available here.

    async function fetchUnreadCount() {
        try {
            const response = await fetch('/api/notifications/unread_count/');
            if (!response.ok) {
                console.error('Failed to fetch unread count, status:', response.status);
                throw new Error('Failed to fetch unread count');
            }
            const data = await response.json();
            if (unreadCountBadge) {
                unreadCountBadge.textContent = data.unread_count > 0 ? data.unread_count : '';
                unreadCountBadge.style.display = data.unread_count > 0 ? 'inline-block' : 'none';
            }
        } catch (error) {
            console.error("Error fetching unread count:", error);
            if (unreadCountBadge) {
                unreadCountBadge.style.display = 'none';
            }
        }
    }

    async function fetchNotifications() {
        if (!notificationDropdownMenu) return;
        notificationDropdownMenu.innerHTML = '<li><a class="dropdown-item text-center" href="#">Loading...</a></li>'; // Show loading state

        try {
            const response = await fetch('/api/notifications/');
            if (!response.ok) {
                console.error('Failed to fetch notifications, status:', response.status);
                throw new Error('Failed to fetch notifications');
            }
            const data = await response.json();

            notificationDropdownMenu.innerHTML = ''; // Clear existing items

            if (data.notifications && data.notifications.length > 0) {
                data.notifications.forEach(notification => {
                    const listItem = document.createElement('li');
                    const linkItem = document.createElement('a');
                    linkItem.classList.add('dropdown-item', 'notification-item');
                    linkItem.href = '#';
                    linkItem.dataset.notificationId = notification.id;

                    if (notification.is_read) {
                        linkItem.classList.add('read');
                    }

                    linkItem.innerHTML = `
                        <div class="fw-bold">${notification.title}</div>
                        <div class="small message-preview">${notification.message}</div>
                        <div class="text-muted small fst-italic">${notification.published_at}</div>
                    `;

                    listItem.appendChild(linkItem);
                    notificationDropdownMenu.appendChild(listItem);
                });
            } else {
                notificationDropdownMenu.innerHTML = '<li><a class="dropdown-item text-center" href="#">No new notifications</a></li>';
            }
        } catch (error) {
            console.error("Error fetching notifications:", error);
            notificationDropdownMenu.innerHTML = '<li><a class="dropdown-item text-center text-danger" href="#">Failed to load notifications</a></li>';
        }
    }

    async function markAsRead(notificationId) {
        try {
            const csrfToken = getCookie('csrftoken'); // Use existing getCookie function from main.js
            if (!csrfToken) {
                console.error("CSRF token not found. Ensure getCookie is defined and main.js is loaded first.");
                alert("Could not process request. Please refresh the page.");
                return;
            }
            const response = await fetch(`/api/notifications/${notificationId}/mark_as_read/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
            });
            if (!response.ok) {
                console.error('Failed to mark as read, status:', response.status);
                throw new Error('Failed to mark as read');
            }
            const data = await response.json();
            if (data.success) {
                const itemToMark = notificationDropdownMenu.querySelector(`.notification-item[data-notification-id="${notificationId}"]`);
                if (itemToMark) {
                    itemToMark.classList.add('read');
                }
                fetchUnreadCount(); // Refresh unread count
            } else {
                console.error("Failed to mark as read:", data.error);
            }
        } catch (error) {
            console.error("Error marking as read:", error);
        }
    }

    // Initial fetch
    fetchUnreadCount();

    // Event listener for Bootstrap dropdown show event
    notificationBellContainer.addEventListener('show.bs.dropdown', function () {
        fetchNotifications();
    });

    // Event listener for clicks on notification items
    if (notificationDropdownMenu) {
        notificationDropdownMenu.addEventListener('click', function(event) {
            const targetLink = event.target.closest('a.notification-item');
            if (targetLink && targetLink.dataset.notificationId) {
                event.preventDefault(); // Prevent default anchor action
                if (!targetLink.classList.contains('read')) {
                    markAsRead(targetLink.dataset.notificationId);
                }
            }
        });
    }

    // Optional: Periodically refresh unread count
    // setInterval(fetchUnreadCount, 60000);
});
