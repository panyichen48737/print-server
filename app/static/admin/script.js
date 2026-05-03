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

// Socket.IO 实时推送连接
var socket = io({
    transports: ['websocket', 'polling'],
    reconnectionDelay: 5000,
    reconnectionAttempts: Infinity
});

var wsHandlers = {};

socket.on('connect', function() {
    console.log('WebSocket 已连接');
});

socket.on('printer_status', function(data) {
    dispatchWS('printer_status', data);
});

socket.on('job_status', function(data) {
    dispatchWS('job_status', data);
});

function onWSMessage(eventType, callback) {
    if (!wsHandlers[eventType]) wsHandlers[eventType] = [];
    wsHandlers[eventType].push(callback);
}

function dispatchWS(eventType, data) {
    var handlers = wsHandlers[eventType] || [];
    for (var i = 0; i < handlers.length; i++) {
        handlers[i](data);
    }
    var allHandlers = wsHandlers['*'] || [];
    for (var i = 0; i < allHandlers.length; i++) {
        allHandlers[i](eventType, data);
    }
}
