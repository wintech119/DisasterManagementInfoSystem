/**
 * Form Utilities - CSP-compliant event handlers
 * Common patterns for auto-submit, confirmations, print, etc.
 */

document.addEventListener('DOMContentLoaded', function() {
    
    // Auto-submit forms when select changes
    const autoSubmitSelects = document.querySelectorAll('select[data-auto-submit="true"]');
    autoSubmitSelects.forEach(function(select) {
        select.addEventListener('change', function() {
            this.form.submit();
        });
    });
    
    // Print buttons
    const printButtons = document.querySelectorAll('[data-action="print"]');
    printButtons.forEach(function(btn) {
        btn.addEventListener('click', function() {
            window.print();
        });
    });
    
    // Go back buttons
    document.addEventListener('click', function(e) {
        const backBtn = e.target.closest('[data-action="go-back"]');
        if (backBtn) {
            history.back();
        }
    });
    
    // Close alert banners
    document.addEventListener('click', function(e) {
        const closeBtn = e.target.closest('[data-action="close-alert"]');
        if (closeBtn) {
            const alert = closeBtn.closest('.alert-banner, .alert');
            if (alert) {
                alert.remove();
            }
        }
    });
    
    // Stop propagation for nested clickable elements
    document.addEventListener('click', function(e) {
        const stopPropBtn = e.target.closest('[data-action="stop-propagation"]');
        if (stopPropBtn) {
            e.stopPropagation();
        }
    });
    
    // Clickable table rows with data-href attribute
    document.addEventListener('click', function(e) {
        const row = e.target.closest('tr[data-href]');
        if (row && !e.target.closest('[data-action="stop-propagation"]')) {
            const href = row.dataset.href;
            if (href) {
                window.location = href;
            }
        }
    });
    
    // Confirmation dialogs for forms
    const confirmForms = document.querySelectorAll('form[data-confirm]');
    confirmForms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const message = this.dataset.confirm;
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });
    
    // Confirmation dialogs for buttons
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(function(btn) {
        // Skip forms (handled above)
        if (btn.tagName === 'FORM') return;
        
        btn.addEventListener('click', function(e) {
            const message = this.dataset.confirm;
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });
});
