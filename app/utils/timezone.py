"""
Timezone Utilities for DRIMS
All datetime operations use Jamaica Standard Time (UTC-05:00)
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

JAMAICA_TZ = timezone(timedelta(hours=-5))

def now() -> datetime:
    """
    Get current datetime in Jamaica Standard Time (UTC-05:00).
    Returns timezone-aware datetime object.
    
    Use this instead of datetime.utcnow() or datetime.now()
    throughout the application.
    """
    return datetime.now(JAMAICA_TZ)

def to_jamaica_time(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a datetime to Jamaica Standard Time.
    
    Args:
        dt: Datetime to convert (can be naive or aware)
        
    Returns:
        Timezone-aware datetime in Jamaica time, or None if input is None
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        return dt.replace(tzinfo=JAMAICA_TZ)
    
    return dt.astimezone(JAMAICA_TZ)

def make_aware(dt: datetime) -> datetime:
    """
    Make a naive datetime timezone-aware in Jamaica time.
    If already aware, converts to Jamaica time.
    
    Args:
        dt: Datetime to make aware
        
    Returns:
        Timezone-aware datetime in Jamaica time
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=JAMAICA_TZ)
    return dt.astimezone(JAMAICA_TZ)

def format_datetime(dt: Optional[datetime], format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Format a datetime for display, ensuring it's in Jamaica time.
    
    Args:
        dt: Datetime to format
        format_str: strftime format string
        
    Returns:
        Formatted datetime string, or empty string if dt is None
    """
    if dt is None:
        return ''
    
    jamaica_dt = to_jamaica_time(dt)
    return jamaica_dt.strftime(format_str)

def get_date_only(dt: Optional[datetime] = None) -> datetime:
    """
    Get date at midnight in Jamaica time.
    
    Args:
        dt: Optional datetime (defaults to current time)
        
    Returns:
        Datetime at midnight in Jamaica time
    """
    if dt is None:
        dt = now()
    else:
        dt = to_jamaica_time(dt)
    
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)
