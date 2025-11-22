"""
Content Security Policy (CSP) middleware for DMIS
Provides strict CSP headers with nonce-based protection against XSS attacks
"""
import secrets
from flask import g, request


def generate_csp_nonce():
    """Generate a cryptographically secure nonce for CSP"""
    return secrets.token_urlsafe(16)


def get_csp_nonce():
    """Get or create CSP nonce for current request"""
    if not hasattr(g, 'csp_nonce'):
        g.csp_nonce = generate_csp_nonce()
    return g.csp_nonce


def build_csp_header():
    """
    Build Content-Security-Policy header with strict directives
    
    Whitelisted domains:
    - cdn.jsdelivr.net: Bootstrap 5.3.3, Bootstrap Icons, Chart.js, Flatpickr
    
    Security features:
    - Nonce-based inline script/style protection
    - No wildcards or unsafe-eval
    - Frame protection (frame-ancestors 'none')
    - Form submission restricted to same origin
    """
    nonce = get_csp_nonce()
    
    csp_directives = [
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net",
        f"style-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net",
        "img-src 'self' data: https:",
        "font-src 'self' https://cdn.jsdelivr.net data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "manifest-src 'self'",
        "upgrade-insecure-requests"
    ]
    
    return "; ".join(csp_directives)


def add_csp_headers(response):
    """
    Add CSP and other security headers to response
    
    Args:
        response: Flask response object
        
    Returns:
        Modified response with security headers
    """
    response.headers['Content-Security-Policy'] = build_csp_header()
    
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    return response


def init_csp(app):
    """
    Initialize CSP middleware for Flask application
    
    Args:
        app: Flask application instance
    """
    
    @app.before_request
    def setup_csp_nonce():
        """Generate nonce for each request"""
        get_csp_nonce()
    
    @app.after_request
    def apply_csp_headers(response):
        """Apply CSP headers to all responses"""
        return add_csp_headers(response)
    
    @app.context_processor
    def inject_csp_nonce():
        """Make CSP nonce available in templates"""
        return {'csp_nonce': get_csp_nonce}
