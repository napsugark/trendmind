import os
import logging
import logging.handlers
from datetime import datetime
from typing import Optional


def configure_logger(name: str = "TrendMindLogger", 
                    logs_dir: str = "data/logs", 
                    enable_email: bool = False,
                    email_config: Optional[dict] = None) -> logging.Logger:
    """
    Configure a custom logger for the TrendMind system.
    
    Args:
        name: Logger name
        logs_dir: Directory to store log files (relative to project root)
        enable_email: Whether to enable email notifications for critical errors
        email_config: Dictionary containing email configuration if enable_email is True
                     Expected keys: sender_email, sender_password, recipient_emails, smtp_host, smtp_port
    
    Returns:
        Configured logger instance
    """
    # Create logs directory path relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_directory_path = os.path.join(project_root, logs_dir)

    if not os.path.exists(logs_directory_path):
        os.makedirs(logs_directory_path)

    current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = os.path.join(logs_directory_path, f'trendmind_{current_date}.log')

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Check if handlers are already added to avoid duplicate handlers
    if not logger.hasHandlers():
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create rotating file handler (rotate logs if they exceed 10MB)
        file_handler = logging.handlers.RotatingFileHandler(
            log_filename, maxBytes=10**7, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Define the formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # Add handlers to the logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
        # Optional email handler for critical errors
        if enable_email and email_config:
            try:
                smtp_handler = logging.handlers.SMTPHandler(
                    mailhost=(email_config.get("smtp_host", "smtp.gmail.com"), 
                             email_config.get("smtp_port", 587)),
                    fromaddr=email_config["sender_email"],
                    toaddrs=email_config["recipient_emails"].split(',') if isinstance(email_config["recipient_emails"], str) else email_config["recipient_emails"],
                    subject="TrendMind System - Critical Error!",
                    credentials=(email_config["sender_email"], email_config["sender_password"]),
                    secure=()
                )
                smtp_handler.setLevel(logging.ERROR)
                smtp_handler.setFormatter(formatter)
                logger.addHandler(smtp_handler)
                logger.info("Email notifications enabled for critical errors")
            except Exception as e:
                logger.warning(f"Failed to configure email handler: {e}")

    return logger


# Create default logger instance
logger = configure_logger()


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance. If name is provided, creates a child logger.
    
    Args:
        name: Optional name for child logger
        
    Returns:
        Logger instance
    """
    if name:
        return logger.getChild(name)
    return logger


def configure_email_logger(sender_email: str, sender_password: str, 
                          recipient_emails: str, smtp_host: str = "smtp.gmail.com", 
                          smtp_port: int = 587) -> logging.Logger:
    """
    Configure logger with email notifications enabled.
    
    Args:
        sender_email: Email address to send from
        sender_password: Password or app-specific password for sender email
        recipient_emails: Comma-separated list of recipient emails
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port
        
    Returns:
        Configured logger with email notifications
    """
    email_config = {
        "sender_email": sender_email,
        "sender_password": sender_password,
        "recipient_emails": recipient_emails,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port
    }
    
    return configure_logger(
        name="TrendMindLogger_Email",
        enable_email=True,
        email_config=email_config
    )


def log_performance(func):
    """
    Decorator to log function performance metrics.
    
    Args:
        func: Function to be decorated
        
    Returns:
        Wrapped function with performance logging
    """
    import functools
    import time
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()
        
        logger.debug(f"Starting {func.__name__} with args: {args[:2]}{'...' if len(args) > 2 else ''}")
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.info(f"{func.__name__} completed successfully in {execution_time:.2f}s")
            
            # Log result summary if it's a list or dict
            if isinstance(result, list):
                logger.debug(f"{func.__name__} returned {len(result)} items")
            elif isinstance(result, dict) and 'results' in result:
                logger.debug(f"{func.__name__} returned {len(result['results'])} results")
                
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.2f}s: {str(e)}")
            raise
            
    return wrapper


def log_scraping_metrics(source: str, results: list, errors: list = None):
    """
    Log detailed metrics for scraping operations.
    
    Args:
        source: Source URL or handle being scraped
        results: List of scraped results
        errors: Optional list of errors encountered
    """
    scraper_logger = get_logger("scraper")
    
    scraper_logger.info(f"Scraping completed for {source}")
    scraper_logger.info(f"Results: {len(results)} items scraped")
    
    if errors:
        scraper_logger.warning(f"Encountered {len(errors)} errors during scraping")
        for error in errors[:5]:  # Log first 5 errors
            scraper_logger.error(f"Scraping error: {error}")
    
    # Log content quality metrics
    if results:
        content_lengths = [len(r.get('content', '')) for r in results if r.get('content')]
        if content_lengths:
            avg_length = sum(content_lengths) / len(content_lengths)
            scraper_logger.debug(f"Average content length: {avg_length:.0f} characters")


def log_database_metrics(operation: str, records_processed: int, 
                        records_successful: int, execution_time: float):
    """
    Log detailed metrics for database operations.
    
    Args:
        operation: Type of database operation (insert, update, etc.)
        records_processed: Total number of records processed
        records_successful: Number of records successfully processed
        execution_time: Time taken for the operation
    """
    db_logger = get_logger("database")
    
    success_rate = (records_successful / records_processed * 100) if records_processed > 0 else 0
    
    db_logger.info(f"Database {operation} completed")
    db_logger.info(f"Records processed: {records_processed}")
    db_logger.info(f"Records successful: {records_successful}")
    db_logger.info(f"Success rate: {success_rate:.1f}%")
    db_logger.info(f"Execution time: {execution_time:.2f}s")
    
    if success_rate < 90:
        db_logger.warning(f"Low success rate ({success_rate:.1f}%) for {operation}")


def log_summary_metrics(input_posts: int, summary_length: int, 
                       tokens_used: int = None, cost_estimate: float = None):
    """
    Log metrics for AI summarization operations.
    
    Args:
        input_posts: Number of input posts summarized
        summary_length: Length of generated summary
        tokens_used: Optional token count used
        cost_estimate: Optional estimated cost in USD
    """
    summary_logger = get_logger("summarizer")
    
    summary_logger.info(f"Summary generated from {input_posts} posts")
    summary_logger.info(f"Summary length: {summary_length} characters")
    
    if tokens_used:
        summary_logger.info(f"Tokens used: {tokens_used:,}")
        
    if cost_estimate:
        summary_logger.info(f"Estimated cost: ${cost_estimate:.4f}")
        
    # Log efficiency metrics
    if input_posts > 0:
        compression_ratio = summary_length / input_posts
        summary_logger.debug(f"Compression ratio: {compression_ratio:.1f} chars per post")