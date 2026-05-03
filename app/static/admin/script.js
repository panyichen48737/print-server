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

// SSE 实时推送
var sseSource = null;

function connectSSE() {
    if (sseSource) sseSource.close();
    sseSource = new EventSource('/api/events');

    sseSource.addEventListener('printer_status', function(e) {
        try { dispatchWS('printer_status', JSON.parse(e.data)); } catch(x) {}
    });

    sseSource.addEventListener('job_status', function(e) {
        try { dispatchWS('job_status', JSON.parse(e.data)); } catch(x) {}
    });

    sseSource.addEventListener('log', function(e) {
        try { dispatchWS('log', JSON.parse(e.data)); } catch(x) {}
    });

    sseSource.onerror = function() {
        console.log('SSE 连接断开，5秒后重连');
        if (sseSource) sseSource.close();
        setTimeout(connectSSE, 5000);
    };
}

connectSSE();

var wsHandlers = {};

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
