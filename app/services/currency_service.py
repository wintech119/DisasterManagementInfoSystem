"""
Currency Conversion Service for DRIMS

This service handles fetching and caching exchange rates from Frankfurter.app (ECB-backed)
for converting foreign currencies to JMD. Rates are cached in the database to minimize
external API calls.

Key Features:
- Fetches rates from Frankfurter.app (free, no API key required)
- Caches rates in the currency_rate database table
- Provides JMD conversion for display purposes (read-only)
- Graceful fallback when rates are unavailable

Usage Example:
    from app.services.currency_service import CurrencyService
    
    # Get rate (will fetch from API if not cached)
    rate = CurrencyService.get_or_update_rate_to_jmd('USD', date.today())
    
    # Convert amount
    jmd_amount = CurrencyService.convert_to_jmd(100.00, 'USD', date.today())
"""

import logging
import requests
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Optional, List, Tuple
from flask import current_app

from app.db import db
from sqlalchemy import text

logger = logging.getLogger(__name__)


class CurrencyRate(db.Model):
    """Model for cached currency exchange rates."""
    __tablename__ = 'currency_rate'
    
    currency_code = db.Column(db.String(3), primary_key=True)
    rate_date = db.Column(db.Date, primary_key=True)
    rate_to_jmd = db.Column(db.Numeric(18, 8), nullable=False)
    source = db.Column(db.String(50), nullable=False, default='FRANKFURTER_ECB')
    create_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CurrencyRate {self.currency_code}={self.rate_to_jmd} JMD on {self.rate_date}>'


class CurrencyServiceError(Exception):
    """Base exception for currency service errors."""
    pass


class CurrencyService:
    """
    Centralized service for currency conversion using Frankfurter.app.
    
    All methods are designed to fail gracefully - if a rate cannot be retrieved,
    methods return None rather than raising exceptions, allowing the app to
    continue functioning.
    """
    
    FRANKFURTER_BASE_URL = 'https://api.frankfurter.app'
    HTTP_TIMEOUT = 5  # seconds
    SOURCE_NAME = 'FRANKFURTER_ECB'
    
    @staticmethod
    def get_cached_rate(currency_code: str, rate_date: date) -> Optional[Decimal]:
        """
        Get a cached exchange rate from the database.
        
        Args:
            currency_code: ISO 4217 currency code (e.g., 'USD', 'EUR')
            rate_date: The date for which to retrieve the rate
            
        Returns:
            The exchange rate to JMD, or None if not cached
        """
        if not currency_code:
            return None
            
        currency_code = currency_code.upper().strip()
        
        if currency_code == 'JMD':
            return Decimal('1')
        
        try:
            rate = CurrencyRate.query.filter_by(
                currency_code=currency_code,
                rate_date=rate_date
            ).first()
            
            if rate:
                return Decimal(str(rate.rate_to_jmd))
            
            rate = CurrencyRate.query.filter(
                CurrencyRate.currency_code == currency_code,
                CurrencyRate.rate_date <= rate_date
            ).order_by(CurrencyRate.rate_date.desc()).first()
            
            if rate:
                logger.debug(f"Using fallback rate from {rate.rate_date} for {currency_code}")
                return Decimal(str(rate.rate_to_jmd))
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached rate for {currency_code}: {e}")
            return None
    
    @staticmethod
    def store_rate(currency_code: str, rate_date: date, rate_to_jmd: Decimal, 
                   source: str = 'FRANKFURTER_ECB') -> bool:
        """
        Store or update an exchange rate in the database.
        
        Args:
            currency_code: ISO 4217 currency code
            rate_date: The date the rate applies to
            rate_to_jmd: Exchange rate (how many JMD for 1 unit of currency)
            source: Rate source identifier
            
        Returns:
            True if successful, False otherwise
        """
        if not currency_code or currency_code.upper() == 'JMD':
            return False
            
        currency_code = currency_code.upper().strip()
        
        try:
            existing = CurrencyRate.query.filter_by(
                currency_code=currency_code,
                rate_date=rate_date
            ).first()
            
            if existing:
                existing.rate_to_jmd = rate_to_jmd
                existing.source = source
                existing.create_dtime = datetime.utcnow()
            else:
                new_rate = CurrencyRate(
                    currency_code=currency_code,
                    rate_date=rate_date,
                    rate_to_jmd=rate_to_jmd,
                    source=source,
                    create_dtime=datetime.utcnow()
                )
                db.session.add(new_rate)
            
            db.session.commit()
            logger.info(f"Stored rate: 1 {currency_code} = {rate_to_jmd} JMD for {rate_date}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error storing rate for {currency_code}: {e}")
            return False
    
    @staticmethod
    def fetch_rate_from_frankfurter(currency_code: str, rate_date: Optional[date] = None) -> Optional[Decimal]:
        """
        Fetch an exchange rate from Frankfurter.app API.
        
        Frankfurter provides ECB rates. We need to calculate the cross-rate to JMD
        since ECB doesn't directly provide JMD rates.
        
        Args:
            currency_code: ISO 4217 currency code (e.g., 'USD', 'EUR')
            rate_date: Optional date for historical rate; None for latest
            
        Returns:
            Exchange rate to JMD, or None if fetch failed
        """
        if not currency_code:
            return None
            
        currency_code = currency_code.upper().strip()
        
        if currency_code == 'JMD':
            return Decimal('1')
        
        try:
            if rate_date:
                date_str = rate_date.strftime('%Y-%m-%d')
                url = f"{CurrencyService.FRANKFURTER_BASE_URL}/{date_str}"
            else:
                url = f"{CurrencyService.FRANKFURTER_BASE_URL}/latest"
            
            params = {'from': currency_code, 'to': 'USD'}
            
            logger.info(f"Fetching rate from Frankfurter: {url} with params {params}")
            
            response = requests.get(url, params=params, timeout=CurrencyService.HTTP_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            if 'rates' not in data or 'USD' not in data['rates']:
                logger.warning(f"No USD rate found in Frankfurter response for {currency_code}")
                return None
            
            rate_to_usd = Decimal(str(data['rates']['USD']))
            
            usd_to_jmd = CurrencyService._get_usd_jmd_rate()
            
            rate_to_jmd = rate_to_usd * usd_to_jmd
            
            logger.info(f"Calculated rate: 1 {currency_code} = {rate_to_usd} USD = {rate_to_jmd} JMD")
            
            return rate_to_jmd
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching rate for {currency_code} from Frankfurter")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"HTTP error fetching rate for {currency_code}: {e}")
            return None
        except (KeyError, ValueError, InvalidOperation) as e:
            logger.warning(f"Error parsing Frankfurter response for {currency_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching rate for {currency_code}: {e}")
            return None
    
    @staticmethod
    def _get_usd_jmd_rate() -> Decimal:
        """
        Get the USD to JMD exchange rate.
        
        Frankfurter/ECB doesn't provide JMD directly. We use a reasonable
        approximation based on current rates (approximately 157 JMD per USD as of 2025).
        This can be updated periodically via the refresh command.
        
        Returns:
            Decimal rate for 1 USD to JMD
        """
        try:
            cached = CurrencyRate.query.filter_by(
                currency_code='USD'
            ).order_by(CurrencyRate.rate_date.desc()).first()
            
            if cached:
                return Decimal(str(cached.rate_to_jmd))
        except Exception:
            pass
        
        return Decimal('157.50')
    
    @staticmethod
    def get_or_update_rate_to_jmd(currency_code: str, rate_date: date) -> Optional[Decimal]:
        """
        Get exchange rate to JMD, fetching from API if not cached.
        
        This is the main entry point for currency conversion. It first checks
        the cache, and if not found, fetches from Frankfurter and stores it.
        
        Args:
            currency_code: ISO 4217 currency code
            rate_date: The date for which to get the rate
            
        Returns:
            Exchange rate to JMD, or None if unavailable
        """
        if not currency_code:
            return None
            
        currency_code = currency_code.upper().strip()
        
        if currency_code == 'JMD':
            return Decimal('1')
        
        cached_rate = CurrencyService.get_cached_rate(currency_code, rate_date)
        if cached_rate is not None:
            return cached_rate
        
        fetched_rate = CurrencyService.fetch_rate_from_frankfurter(currency_code, rate_date)
        
        if fetched_rate is not None:
            CurrencyService.store_rate(currency_code, rate_date, fetched_rate)
            return fetched_rate
        
        return None
    
    @staticmethod
    def convert_to_jmd(amount: Decimal, currency_code: str, 
                       rate_date: Optional[date] = None) -> Optional[Decimal]:
        """
        Convert an amount to JMD.
        
        Args:
            amount: The amount to convert
            currency_code: The source currency code
            rate_date: Optional date for historical rate; defaults to today
            
        Returns:
            Converted amount in JMD, or None if conversion failed
        """
        if amount is None:
            return None
            
        if not currency_code:
            return None
            
        currency_code = currency_code.upper().strip()
        
        if currency_code == 'JMD':
            return Decimal(str(amount))
        
        if rate_date is None:
            rate_date = date.today()
        
        rate = CurrencyService.get_or_update_rate_to_jmd(currency_code, rate_date)
        
        if rate is None:
            return None
        
        try:
            return Decimal(str(amount)) * rate
        except (InvalidOperation, TypeError):
            return None
    
    @staticmethod
    def get_donation_currencies() -> List[str]:
        """
        Get the list of distinct currency codes used in donations.
        
        Returns:
            List of unique currency codes from donation records
        """
        try:
            result = db.session.execute(
                text("SELECT DISTINCT currency_code FROM donation_item WHERE currency_code IS NOT NULL ORDER BY currency_code")
            )
            return [row[0] for row in result.fetchall() if row[0]]
        except Exception as e:
            logger.error(f"Error getting donation currencies: {e}")
            return []
    
    @staticmethod
    def refresh_all_rates(target_date: Optional[date] = None) -> Tuple[int, int]:
        """
        Refresh exchange rates for all currencies used in donations.
        
        Args:
            target_date: Date for which to fetch rates; defaults to today
            
        Returns:
            Tuple of (successful_count, failed_count)
        """
        if target_date is None:
            target_date = date.today()
        
        currencies = CurrencyService.get_donation_currencies()
        
        currencies_to_refresh = [c for c in currencies if c.upper() != 'JMD']
        
        success_count = 0
        fail_count = 0
        
        for currency_code in currencies_to_refresh:
            try:
                rate = CurrencyService.fetch_rate_from_frankfurter(currency_code, target_date)
                if rate is not None:
                    if CurrencyService.store_rate(currency_code, target_date, rate):
                        success_count += 1
                        logger.info(f"Refreshed rate for {currency_code}: {rate} JMD")
                    else:
                        fail_count += 1
                else:
                    fail_count += 1
                    logger.warning(f"Failed to fetch rate for {currency_code}")
            except Exception as e:
                fail_count += 1
                logger.error(f"Error refreshing rate for {currency_code}: {e}")
        
        return success_count, fail_count
    
    @staticmethod
    def set_usd_jmd_rate(rate: Decimal, rate_date: Optional[date] = None) -> bool:
        """
        Manually set the USD to JMD exchange rate.
        
        Since ECB doesn't provide JMD rates directly, this allows administrators
        to set/update the USD/JMD rate manually.
        
        Args:
            rate: The USD to JMD exchange rate
            rate_date: Date for the rate; defaults to today
            
        Returns:
            True if successful, False otherwise
        """
        if rate_date is None:
            rate_date = date.today()
        
        return CurrencyService.store_rate('USD', rate_date, rate, 'MANUAL')
