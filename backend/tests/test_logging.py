#!/usr/bin/env python3
"""
Test script to verify the logging system is working correctly.
"""

import sys
import os

# Add the src directory to the path so we can import modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from logger import get_logger, log_performance, configure_email_logger


@log_performance
def test_function():
    """A simple test function to demonstrate logging."""
    logger = get_logger("test")
    
    logger.info("Starting test function")
    logger.debug("This is a debug message")
    logger.warning("This is a warning message")
    
    # Simulate some work
    import time
    time.sleep(1)
    
    logger.info("Test function completed successfully")
    return "Test completed"


def main():
    """Main test function."""
    logger = get_logger("main_test")
    
    logger.info("=== TrendMind Logging System Test ===")
    
    # Test basic logging
    logger.info("Testing basic logging functionality")
    logger.debug("Debug level message")
    logger.warning("Warning level message")
    
    # Test performance logging decorator
    logger.info("Testing performance logging decorator")
    result = test_function()
    logger.info(f"Function returned: {result}")
    
    # Test child logger
    child_logger = get_logger("scraper_test")
    child_logger.info("Testing child logger functionality")
    
    logger.info("=== Logging Test Complete ===")
    print("\nCheck the logs directory for generated log files!")


if __name__ == "__main__":
    main()