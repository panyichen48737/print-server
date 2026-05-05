// Admin UI Scripts
(function() {
    'use strict';

    /* ── API Fetch wrapper ── */
    function apiFetch(url, options) {
        var opts = options || {};
        opts.headers = opts.headers || {};
        opts.headers['Accept'] = 'application/json';

        return fetch(url, opts).then(function(r) {
            if (!r.ok) {
                return r.json().then(function(data) {
                    throw new Error(data.error || '请求失败 (' + r.status + ')');
                }).catch(function(err) {
                    if (err instanceof SyntaxError) {
                        throw new Error('请求失败 (' + r.status + ')');
                    }
                    throw err;
                });
            }
            return r.json();
        }).catch(function(err) {
            showToast('网络错误: ' + (err.message || '请检查网络连接'), 'error');
            throw err;
        });
    }

    /* ── Loading state wrapper ── */
    function withLoading(btn, promise) {
        if (!btn) return promise;
        btn.disabled = true;
        // Preserve width by setting explicit min-width before changing content
        var origW = btn.offsetWidth;
        btn.dataset.originalHtml = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-sm"></span> 处理中...';
        if (btn.offsetWidth < origW) {
            btn.style.minWidth = origW + 'px';
        }
        return (promise || Promise.resolve()).finally(function() {
            btn.disabled = false;
            btn.innerHTML = btn.dataset.originalHtml || '';
            btn.style.minWidth = '';
        });
    }

    /* ── Debounce ── */
    function debounce(fn, delay) {
        var timer = null;
        return function() {
            var args = arguments;
            var ctx = this;
            clearTimeout(timer);
            timer = setTimeout(function() { fn.apply(ctx, args); }, delay);
        };
    }

    /* ── Warn on unsaved form changes ── */
    function warnUnsavedChanges(formSelector, message) {
        var form = document.querySelector(formSelector);
        if (!form) return function(){};
        var msg = message || '有未保存的修改，确定要离开吗？';
        var origData = new FormData(form);
        function checkChanged() {
            var curr = new FormData(form);
            if (origData.length !== curr.length) return true;
            for (var key of origData.keys()) {
                if (origData.get(key) !== curr.get(key)) return true;
            }
            return false;
        }
        function beforeUnload(e) {
            if (!checkChanged()) return;
            e.preventDefault();
            e.returnValue = msg;
            return msg;
        }
        window.addEventListener('beforeunload', beforeUnload);
        // Remove warning on form submit
        form.addEventListener('submit', function() {
            window.removeEventListener('beforeunload', beforeUnload);
        }, { once: true });
        return function() { window.removeEventListener('beforeunload', beforeUnload); };
    }

    /* ── Sidebar toggle (mobile) ── */
    var sidebarToggle = document.getElementById('sidebarToggle');
    var sidebar = document.getElementById('sidebar');
    var sidebarBackdrop = document.getElementById('sidebarBackdrop');

    if (sidebarToggle && sidebar) {
        sidebarToggle.setAttribute('aria-label', '切换侧栏');
        sidebarToggle.setAttribute('aria-expanded', 'false');

        function openSidebar() {
            sidebar.classList.add('open');
            sidebarToggle.setAttribute('aria-expanded', 'true');
            document.body.style.overflow = 'hidden';
        }

        function closeSidebar() {
            sidebar.classList.remove('open');
            sidebarToggle.setAttribute('aria-expanded', 'false');
            document.body.style.overflow = '';
        }

        sidebarToggle.addEventListener('click', function() {
            var isOpen = sidebar.classList.contains('open');
            if (isOpen) closeSidebar(); else openSidebar();
        });

        // Close sidebar on backdrop click
        if (sidebarBackdrop) {
            sidebarBackdrop.addEventListener('click', closeSidebar);
        }

        // Close sidebar on outside click (mobile)
        document.addEventListener('click', function(e) {
            if (window.innerWidth <= 768 &&
                !sidebar.contains(e.target) &&
                !sidebarToggle.contains(e.target)) {
                closeSidebar();
            }
        });
    }

    /* ── Debounced resize handler for sidebar ── */
    window.addEventListener('resize', debounce(function() {
        if (window.innerWidth > 768 && sidebar) {
            sidebar.classList.remove('open');
            if (sidebarToggle) sidebarToggle.setAttribute('aria-expanded', 'false');
        }
    }, 200));

    /* ── Escape key closes modals ── */
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.show').forEach(function(m) {
                m.classList.remove('show');
            });
        }
    });

    /* ── Theme toggle ── */
    (function() {
        var themeToggle = document.getElementById('themeToggle');
        var html = document.documentElement;

        function setTheme(theme) {
            html.setAttribute('data-theme', theme);
            try { localStorage.setItem('theme', theme); } catch(e) {}
            if (themeToggle) {
                themeToggle.setAttribute('aria-label', theme === 'dark' ? '切换到浅色主题' : '切换到深色主题');
                themeToggle.innerHTML = theme === 'dark'
                    ? '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img" aria-hidden="true"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>'
                    : '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
            }
        }

        // Restore saved theme or use dark as default
        var saved;
        try { saved = localStorage.getItem('theme'); } catch(e) {}
        setTheme(saved || 'dark');

        if (themeToggle) {
            themeToggle.addEventListener('click', function() {
                var current = html.getAttribute('data-theme');
                setTheme(current === 'dark' ? 'light' : 'dark');
            });
        }
    })();

    /* ── Toast system with auto-dismiss ── */
    function showToast(message, type) {
        var container = document.getElementById('toastContainer');
        if (!container) return;

        var toast = document.createElement('div');
        toast.className = 'toast ' + (type || 'success');
        toast.textContent = message;
        toast.setAttribute('role', 'alert');
        container.appendChild(toast);

        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    }

    // Auto-dismiss initial toasts
    document.querySelectorAll('.toast').forEach(function(toast) {
        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    });

    /* ── Auto-dismiss HTMX result messages ── */
    document.addEventListener('htmx:afterSwap', function(evt) {
        var target = evt.detail.target;
        if (!target) return;
        // Auto-dismiss result spans after 4s
        var resultEls = target.querySelectorAll('[data-auto-dismiss]');
        resultEls.forEach(function(el) {
            var delay = parseInt(el.getAttribute('data-auto-dismiss')) || 4000;
            setTimeout(function() {
                el.style.transition = 'opacity 0.3s';
                el.style.opacity = '0';
                setTimeout(function() { el.textContent = ''; el.style.opacity = '1'; }, 300);
            }, delay);
        });
    });

    /* ── Confirmation dialog ── */
    function confirmAction(message, callback) {
        var overlay = document.getElementById('confirmModal');
        if (!overlay) return;

        overlay.querySelector('.modal-message').textContent = message;
        overlay.classList.add('show');

        var confirmBtn = overlay.querySelector('.btn-confirm');
        var cancelBtn = overlay.querySelector('.btn-cancel');

        function cleanup() {
            overlay.classList.remove('show');
            confirmBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
            overlay.removeEventListener('click', onOverlayClick);
            document.removeEventListener('keydown', onKeydown);
        }

        function onConfirm() {
            cleanup();
            if (callback) callback();
        }

        function onCancel() {
            cleanup();
        }

        function onOverlayClick(e) {
            if (e.target === overlay) cleanup();
        }

        function onKeydown(e) {
            if (e.key === 'Escape') cleanup();
        }

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        overlay.addEventListener('click', onOverlayClick);
        document.addEventListener('keydown', onKeydown);

        // Focus management
        setTimeout(function() {
            confirmBtn.focus();
        }, 50);
    }

    /* ── SSE with exponential backoff ── */
    var sseSource = null;
    var sseRetryDelay = 1000;
    var sseMaxRetryDelay = 30000;

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

        sseSource.onopen = function() {
            sseRetryDelay = 1000; // Reset on successful connection
        };

        sseSource.onerror = function() {
            if (sseSource) sseSource.close();
            var delay = sseRetryDelay;
            sseRetryDelay = Math.min(sseRetryDelay * 2, sseMaxRetryDelay);
            setTimeout(connectSSE, delay);
        };
    }

    connectSSE();

    /* ── Event system ── */
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

    /* ── Copy to clipboard ── */
    function copyToClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function() {
                showToast('已复制到剪贴板', 'success');
            }).catch(function() {
                fallbackCopy(text);
            });
        } else {
            fallbackCopy(text);
        }
    }

    function fallbackCopy(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand('copy');
            showToast('已复制到剪贴板', 'success');
        } catch(e) {
            showToast('复制失败', 'error');
        }
        document.body.removeChild(ta);
    }

    /* ── Export globals ── */
    window.apiFetch = apiFetch;
    window.withLoading = withLoading;
    window.debounce = debounce;
    window.warnUnsavedChanges = warnUnsavedChanges;
    window.showToast = showToast;
    window.confirmAction = confirmAction;
    window.onWSMessage = onWSMessage;
    window.dispatchWS = dispatchWS;
    window.connectSSE = connectSSE;
    window.copyToClipboard = copyToClipboard;
})();
