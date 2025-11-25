"""
Currency Conversion Service

Provides currency conversion functionality for converting amounts to Jamaican Dollars (JMD).
Uses config-driven exchange rates without requiring database schema changes.

Exchange rates are loaded from environment variables or configuration.
Default rates are provided as fallback for common currencies.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple, Dict
import os
import json
import logging

logger = logging.getLogger(__name__)

DEFAULT_EXCHANGE_RATES = {
    'JMD': Decimal('1.00'),
    'USD': Decimal('155.50'),
    'EUR': Decimal('170.25'),
    'GBP': Decimal('198.75'),
    'CAD': Decimal('115.30'),
    'BBD': Decimal('77.75'),
    'TTD': Decimal('23.10'),
    'XCD': Decimal('57.60'),
    'AWG': Decimal('86.60'),
    'BSD': Decimal('155.50'),
    'BZD': Decimal('77.75'),
    'GYD': Decimal('0.74'),
    'HTG': Decimal('1.18'),
    'SRD': Decimal('4.30'),
    'KYD': Decimal('190.25'),
    'BMD': Decimal('155.50'),
    'ANG': Decimal('86.60'),
    'CUP': Decimal('6.50'),
    'DOP': Decimal('2.65'),
    'MXN': Decimal('9.05'),
    'CHF': Decimal('175.80'),
    'JPY': Decimal('1.04'),
    'CNY': Decimal('21.50'),
    'INR': Decimal('1.85'),
    'AUD': Decimal('102.40'),
    'NZD': Decimal('94.50'),
    'SGD': Decimal('116.80'),
    'HKD': Decimal('19.95'),
}


class CurrencyConversionError(Exception):
    """Exception raised when currency conversion fails."""
    
    def __init__(self, message: str, currency_code: str = None):
        self.message = message
        self.currency_code = currency_code
        super().__init__(self.message)


class CurrencyConversionService:
    """
    Service for converting amounts from various currencies to JMD.
    
    Exchange rates can be configured via:
    1. EXCHANGE_RATES environment variable (JSON string)
    2. EXCHANGE_RATES_FILE environment variable (path to JSON file)
    3. Default rates built into the service
    
    Example environment variable:
        EXCHANGE_RATES='{"USD": "155.50", "EUR": "170.25", "GBP": "198.75"}'
    
    Example JSON file content:
        {
            "USD": "155.50",
            "EUR": "170.25",
            "GBP": "198.75"
        }
    """
    
    def __init__(self):
        self._rates: Dict[str, Decimal] = {}
        self._load_exchange_rates()
    
    def _load_exchange_rates(self) -> None:
        """Load exchange rates from environment or config file."""
        self._rates = DEFAULT_EXCHANGE_RATES.copy()
        
        rates_json = os.environ.get('EXCHANGE_RATES')
        if rates_json:
            try:
                custom_rates = json.loads(rates_json)
                for code, rate in custom_rates.items():
                    self._rates[code.upper()] = Decimal(str(rate))
                logger.info(f"Loaded {len(custom_rates)} custom exchange rates from environment")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse EXCHANGE_RATES environment variable: {e}")
        
        rates_file = os.environ.get('EXCHANGE_RATES_FILE')
        if rates_file and os.path.exists(rates_file):
            try:
                with open(rates_file, 'r') as f:
                    file_rates = json.load(f)
                    for code, rate in file_rates.items():
                        self._rates[code.upper()] = Decimal(str(rate))
                    logger.info(f"Loaded {len(file_rates)} exchange rates from file: {rates_file}")
            except (json.JSONDecodeError, ValueError, IOError) as e:
                logger.warning(f"Failed to load exchange rates from file {rates_file}: {e}")
    
    def get_rate(self, currency_code: str) -> Optional[Decimal]:
        """
        Get the exchange rate for a currency to JMD.
        
        Args:
            currency_code: The ISO currency code (e.g., 'USD', 'EUR')
            
        Returns:
            The exchange rate to JMD, or None if not found
        """
        return self._rates.get(currency_code.upper())
    
    def has_rate(self, currency_code: str) -> bool:
        """Check if an exchange rate is configured for the given currency."""
        return currency_code.upper() in self._rates
    
    def get_available_currencies(self) -> list:
        """Get list of all currencies with configured exchange rates."""
        return sorted(self._rates.keys())
    
    def convert_to_jmd(
        self, 
        amount: Decimal, 
        source_currency_code: str,
        raise_on_missing: bool = True
    ) -> Tuple[Decimal, Optional[str]]:
        """
        Convert an amount from a source currency to JMD.
        
        Args:
            amount: The amount to convert
            source_currency_code: The ISO currency code of the source amount
            raise_on_missing: If True, raise exception when rate is missing;
                            if False, return error message instead
        
        Returns:
            Tuple of (converted_amount, error_message)
            - If successful: (jmd_amount, None)
            - If failed: (original_amount, error_message)
        
        Raises:
            CurrencyConversionError: If rate is missing and raise_on_missing is True
        """
        if amount is None:
            return Decimal('0.00'), None
        
        amount = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
        currency_code = source_currency_code.upper().strip()
        
        if currency_code == 'JMD':
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), None
        
        rate = self.get_rate(currency_code)
        
        if rate is None:
            error_msg = (
                f"Conversion rate for [{currency_code}] to JMD is not configured. "
                f"Please contact the administrator to add the exchange rate."
            )
            if raise_on_missing:
                raise CurrencyConversionError(error_msg, currency_code)
            return amount, error_msg
        
        converted = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return converted, None
    
    def convert(
        self,
        amount: Decimal,
        source_currency_code: str,
        target_currency_code: str = 'JMD',
        raise_on_missing: bool = True
    ) -> Tuple[Decimal, Optional[str]]:
        """
        Convert an amount from source currency to target currency.
        
        Currently only supports JMD as target currency.
        
        Args:
            amount: The amount to convert
            source_currency_code: The ISO currency code of the source amount
            target_currency_code: The target currency code (default: JMD)
            raise_on_missing: If True, raise exception when rate is missing
        
        Returns:
            Tuple of (converted_amount, error_message)
        """
        if target_currency_code.upper() != 'JMD':
            error_msg = f"Only conversion to JMD is currently supported, not {target_currency_code}"
            if raise_on_missing:
                raise CurrencyConversionError(error_msg)
            return amount, error_msg
        
        return self.convert_to_jmd(amount, source_currency_code, raise_on_missing)
    
    def update_rate(self, currency_code: str, rate: Decimal) -> None:
        """
        Update or add an exchange rate.
        
        Note: This only updates the in-memory rates. To persist rates,
        update the EXCHANGE_RATES environment variable or rates file.
        
        Args:
            currency_code: The ISO currency code
            rate: The exchange rate to JMD
        """
        self._rates[currency_code.upper()] = Decimal(str(rate))
    
    def reload_rates(self) -> None:
        """Reload exchange rates from configuration."""
        self._load_exchange_rates()


_service_instance: Optional[CurrencyConversionService] = None


def get_currency_conversion_service() -> CurrencyConversionService:
    """
    Get the singleton instance of the currency conversion service.
    
    Returns:
        CurrencyConversionService: The service instance
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = CurrencyConversionService()
    return _service_instance


def convert_to_jmd(amount: Decimal, source_currency_code: str) -> Tuple[Decimal, Optional[str]]:
    """
    Convenience function to convert an amount to JMD.
    
    Args:
        amount: The amount to convert
        source_currency_code: The ISO currency code of the source amount
    
    Returns:
        Tuple of (jmd_amount, error_message)
    """
    service = get_currency_conversion_service()
    return service.convert_to_jmd(amount, source_currency_code, raise_on_missing=False)


def convert_item_cost_to_jmd(
    item_cost: Decimal,
    quantity: Decimal,
    currency_code: str,
    donation_type: str = 'GOODS'
) -> Tuple[Decimal, Optional[str]]:
    """
    Convert a donation item's total cost to JMD.
    
    For FUNDS items, the currency is determined by the UOM/currency_code field.
    For GOODS items, costs are assumed to be in JMD unless otherwise specified.
    
    Args:
        item_cost: The per-unit cost of the item
        quantity: The quantity of items
        currency_code: The currency code (from UOM field for FUNDS, or 'JMD' for GOODS)
        donation_type: 'GOODS' or 'FUNDS'
    
    Returns:
        Tuple of (total_jmd_amount, error_message)
    """
    if item_cost is None or quantity is None:
        return Decimal('0.00'), None
    
    item_cost = Decimal(str(item_cost)) if not isinstance(item_cost, Decimal) else item_cost
    quantity = Decimal(str(quantity)) if not isinstance(quantity, Decimal) else quantity
    
    line_total = item_cost * quantity
    
    if donation_type == 'FUNDS' and currency_code and currency_code.upper() != 'JMD':
        return convert_to_jmd(line_total, currency_code)
    
    return line_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), None


def get_available_currencies() -> list:
    """Get list of all currencies with configured exchange rates."""
    service = get_currency_conversion_service()
    return service.get_available_currencies()


def has_exchange_rate(currency_code: str) -> bool:
    """Check if an exchange rate is configured for the given currency."""
    service = get_currency_conversion_service()
    return service.has_rate(currency_code)
