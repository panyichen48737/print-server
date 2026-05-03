// Admin UI Scripts
(function() {
    'use strict';

    // Sidebar toggle (mobile)
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('open');
        });

        // Close sidebar on outside click (mobile)
        document.addEventListener('click', function(e) {
            if (window.innerWidth <= 768 &&
                !sidebar.contains(e.target) &&
                !sidebarToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    // Auto-dismiss toasts
    document.querySelectorAll('.toast').forEach(function(toast) {
        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    });

})();

// Confirmation dialog
function confirmAction(message, callback) {
    const overlay = document.getElementById('confirmModal');
    if (!overlay) return;

    overlay.querySelector('.modal-message').textContent = message;
    overlay.classList.add('show');

    overlay.querySelector('.btn-confirm').onclick = function() {
        overlay.classList.remove('show');
        if (callback) callback();
    };

    overlay.querySelector('.btn-cancel').onclick = function() {
        overlay.classList.remove('show');
    };

    // Close on overlay click
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) overlay.classList.remove('show');
    });
}

// Show toast notification
function showToast(message, type) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast ' + (type || 'success');
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(function() { toast.remove(); }, 300);
    }, 4000);
}
