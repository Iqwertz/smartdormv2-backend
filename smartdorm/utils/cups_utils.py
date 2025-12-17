"""
CUPS Utilities for SmartDorm Print System

This module provides functions for communication with the CUPS print server.
It uses the CUPS HTTP API via the pycups package.
"""
import logging
from typing import Optional, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import cups
    CUPS_AVAILABLE = True
except ImportError:
    CUPS_AVAILABLE = False
    logger.warning("pycups not installed. CUPS functionality will be limited.")


def get_cups_connection() -> Optional[Any]:
    """
    Creates a CUPS connection to the configured CUPS server.
    
    Returns:
        cups.Connection or None if connection fails
    """
    if not CUPS_AVAILABLE:
        logger.error("pycups not available. Cannot connect to CUPS.")
        return None
    
    try:
        cups_server = getattr(settings, 'CUPS_SERVER', None)
        if not cups_server:
            logger.error("CUPS_SERVER not configured in settings")
            return None
        
        # pycups can use either IP address or hostname
        conn = cups.Connection(cups_server)
        logger.debug(f"Successfully connected to CUPS server at {cups_server}")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to CUPS server: {e}")
        return None


def submit_print_job(printer_name: str, file_data: bytes, filename: str, 
                     title: Optional[str] = None) -> Optional[str]:
    """
    Submits a print job to CUPS.
    
    Args:
        printer_name: Name of the printer in CUPS (e.g. "Samsung_C1860_Series")
        file_data: PDF data as bytes
        filename: Name of the file (for CUPS info)
        title: Optional title for the print job
        
    Returns:
        CUPS Job ID as string, or None if failed
    """
    conn = get_cups_connection()
    if not conn:
        return None
    
    try:
        # Check if printer exists
        printers = conn.getPrinters()
        if printer_name not in printers:
            logger.error(f"Printer '{printer_name}' not found in CUPS. Available printers: {list(printers.keys())}")
            return None
        
        # Submit job
        # cups.printFile requires a file path, so we need to store temporarily
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(file_data)
            tmp_path = tmp_file.name
        
        try:
            job_title = title or filename
            job_id = conn.printFile(
                printer_name,
                tmp_path,
                job_title,
                {}
            )
            logger.info(f"Print job submitted successfully. Job ID: {job_id}, Printer: {printer_name}, File: {filename}")
            return str(job_id)
        finally:
            # Delete temporary file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as e:
        logger.error(f"Failed to submit print job to CUPS: {e}")
        return None


def get_job_status(printer_name: str, job_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the status of a CUPS print job.
    
    Args:
        printer_name: Name of the printer
        job_id: CUPS Job ID
        
    Returns:
        Dictionary with job information or None
        {
            'job_state': int (3=completed, 4=stopped, 5=cancelled, etc.),
            'job_state_reasons': list,
            'time_at_completion': int (Unix timestamp),
            'pages': int (number of printed pages)
        }
    """
    conn = get_cups_connection()
    if not conn:
        return None
    
    try:
        job_id_int = int(job_id)
        
        # pycups getJobs() returns Dict: {job_id: {attributes}}
        # Try different methods to find the job
        
        # Method 1: Retrieve all jobs and search (without which_jobs, then you get all)
        try:
            all_jobs = conn.getJobs(requested_attributes=[
                'job-id', 'job-state', 'job-state-reasons', 'time-at-completion', 
                'job-printer-uri', 'job-name', 'job-media-sheets-completed',
                'job-impressions-completed', 'job-k-octets-processed'
            ])
            
            # Iterate over all jobs
            for job_dict_key, job_dict_value in all_jobs.items():
                # job_dict_key might be the job ID
                if isinstance(job_dict_key, int) and job_dict_key == job_id_int:
                    # Job data is directly available
                    if isinstance(job_dict_value, dict):
                        # Page count: job-media-sheets-completed (number of pages) or job-impressions-completed (number of pages)
                        pages = job_dict_value.get('job-media-sheets-completed') or job_dict_value.get('job-impressions-completed') or None
                        if pages:
                            try:
                                pages = int(pages)
                            except (ValueError, TypeError):
                                pages = None
                        return {
                            'job_state': job_dict_value.get('job-state', 0),
                            'job_state_reasons': job_dict_value.get('job-state-reasons', []),
                            'time_at_completion': job_dict_value.get('time-at-completion', 0),
                            'printer_uri': job_dict_value.get('job-printer-uri', ''),
                            'pages': pages,
                        }
                
                # Or job-id is in the job data
                if isinstance(job_dict_value, dict):
                    job_id_in_data = job_dict_value.get('job-id')
                    if job_id_in_data == job_id_int:
                        pages = job_dict_value.get('job-media-sheets-completed') or job_dict_value.get('job-impressions-completed') or None
                        if pages:
                            try:
                                pages = int(pages)
                            except (ValueError, TypeError):
                                pages = None
                        return {
                            'job_state': job_dict_value.get('job-state', 0),
                            'job_state_reasons': job_dict_value.get('job-state-reasons', []),
                            'time_at_completion': job_dict_value.get('time-at-completion', 0),
                            'printer_uri': job_dict_value.get('job-printer-uri', ''),
                            'pages': pages,
                        }
        except Exception as e:
            logger.debug(f"Error getting all jobs: {e}")
        
        # Method 2: Fallback without requested_attributes - retrieve all jobs directly
        try:
            all_jobs_simple = conn.getJobs()
            logger.debug(f"Found {len(all_jobs_simple)} jobs in CUPS (all)")
            
            for job_key, job_value in all_jobs_simple.items():
                # Check if job_key is the ID
                if isinstance(job_key, int) and job_key == job_id_int:
                    if isinstance(job_value, dict):
                        logger.debug(f"Found job {job_id_int} by key match")
                        pages = job_value.get('job-media-sheets-completed') or job_value.get('job-impressions-completed') or None
                        if pages:
                            try:
                                pages = int(pages)
                            except (ValueError, TypeError):
                                pages = None
                        return {
                            'job_state': job_value.get('job-state', 0),
                            'job_state_reasons': job_value.get('job-state-reasons', []),
                            'time_at_completion': job_value.get('time-at-completion', 0),
                            'printer_uri': job_value.get('job-printer-uri', ''),
                            'pages': pages,
                        }
                # Or check job-id in job data
                if isinstance(job_value, dict):
                    job_id_in_value = job_value.get('job-id')
                    if job_id_in_value == job_id_int:
                        logger.debug(f"Found job {job_id_int} by job-id in data")
                        pages = job_value.get('job-media-sheets-completed') or job_value.get('job-impressions-completed') or None
                        if pages:
                            try:
                                pages = int(pages)
                            except (ValueError, TypeError):
                                pages = None
                        return {
                            'job_state': job_value.get('job-state', 0),
                            'job_state_reasons': job_value.get('job-state-reasons', []),
                            'time_at_completion': job_value.get('time-at-completion', 0),
                            'printer_uri': job_value.get('job-printer-uri', ''),
                            'pages': pages,
                        }
        except Exception as e:
            logger.debug(f"Error getting jobs (simple): {e}")
        
        # Method 3: Also check completed jobs explicitly
        try:
            completed_jobs = conn.getJobs(which_jobs='completed')
            logger.debug(f"Found {len(completed_jobs)} completed jobs in CUPS")
            for job_key, job_value in completed_jobs.items():
                if isinstance(job_key, int) and job_key == job_id_int:
                    if isinstance(job_value, dict):
                        logger.debug(f"Found completed job {job_id_int}")
                        pages = job_value.get('job-media-sheets-completed') or job_value.get('job-impressions-completed') or None
                        if pages:
                            try:
                                pages = int(pages)
                            except (ValueError, TypeError):
                                pages = None
                        return {
                            'job_state': 3,  # IPP_JSTATE_COMPLETED
                            'job_state_reasons': job_value.get('job-state-reasons', []),
                            'time_at_completion': job_value.get('time-at-completion', 0),
                            'printer_uri': job_value.get('job-printer-uri', ''),
                            'pages': pages,
                        }
                if isinstance(job_value, dict) and job_value.get('job-id') == job_id_int:
                    logger.debug(f"Found completed job {job_id_int} by job-id")
                    pages = job_value.get('job-media-sheets-completed') or job_value.get('job-impressions-completed') or None
                    if pages:
                        try:
                            pages = int(pages)
                        except (ValueError, TypeError):
                            pages = None
                    return {
                        'job_state': 3,  # IPP_JSTATE_COMPLETED
                        'job_state_reasons': job_value.get('job-state-reasons', []),
                        'time_at_completion': job_value.get('time-at-completion', 0),
                        'printer_uri': job_value.get('job-printer-uri', ''),
                        'pages': pages,
                    }
        except Exception as e:
            logger.debug(f"Error getting completed jobs: {e}")
        
        logger.warning(f"Job {job_id} not found in CUPS (checked all methods)")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get job status from CUPS: {e}")
        return None


def is_job_completed(job_state: int) -> bool:
    """
    Checks if a job status means "completed".
    
    CUPS Job States:
    3 = IPP_JSTATE_COMPLETED
    4 = IPP_JSTATE_STOPPED
    5 = IPP_JSTATE_CANCELLED
    
    Args:
        job_state: CUPS job-state integer
        
    Returns:
        True if completed, False otherwise
    """
    # IPP_JSTATE_COMPLETED = 3
    return job_state == 3


def is_job_failed(job_state: int, job_state_reasons) -> bool:
    """
    Checks if a job has failed.
    
    Args:
        job_state: CUPS job-state integer
        job_state_reasons: List of state reasons or string
        
    Returns:
        True if failed, False otherwise
    """
    # Normalize job_state_reasons to a list
    if isinstance(job_state_reasons, str):
        reasons_list = [job_state_reasons]
    elif isinstance(job_state_reasons, list):
        reasons_list = job_state_reasons
    else:
        reasons_list = []
    
    # Normalized reasons as string for easier checking
    reasons_str = ' '.join(str(r).lower() for r in reasons_list)
    
    # IMPORTANT: "job-printing" ALWAYS means the job is still running (NOT an error!)
    # Regardless of the state code
    if 'job-printing' in reasons_str or 'job-processing' in reasons_str:
        return False
    
    # IPP_JSTATE_CANCELLED = 5 (usually error)
    # BUT: Only if no "job-printing" reason is present (see above)
    if job_state == 5:
        # State 5 without "job-printing" = really cancelled
        return True
    
    # IPP_JSTATE_STOPPED = 4 can mean "processing" OR "stopped"
    # Check the reasons to distinguish
    if job_state == 4:
        # State 4 + "stopped" or "error" = error
        if 'stopped' in reasons_str or 'error' in reasons_str or 'aborted' in reasons_str:
            return True
        # Otherwise: State 4 without clear reason = treat carefully as "not yet failed"
        return False
    
    # Check for error reasons in other states
    failed_keywords = ['error', 'aborted', 'cancelled', 'processing-stopped']
    ignored_keywords = ['job-queued']
    
    # Only mark as error if no normal printing states are present
    has_normal_state = any(ignored in reasons_str for ignored in ignored_keywords)
    if has_normal_state:
        return False
    
    # Check for real errors
    if any(keyword in reasons_str for keyword in failed_keywords):
        return True
    
    return False


def get_printer_info(printer_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves information about a printer.
    
    Args:
        printer_name: Name of the printer in CUPS
        
    Returns:
        Dictionary with printer information or None
    """
    conn = get_cups_connection()
    if not conn:
        return None
    
    try:
        printers = conn.getPrinters()
        if printer_name not in printers:
            return None
        
        printer_attrs = conn.getPrinterAttributes(printer_name)
        
        return {
            'name': printer_name,
            'state': printers[printer_name].get('printer-state', 0),
            'state_message': printers[printer_name].get('printer-state-message', ''),
            'is_accepting_jobs': printers[printer_name].get('printer-is-accepting-jobs', False),
            'info': printers[printer_name].get('printer-info', ''),
        }
    except Exception as e:
        logger.error(f"Failed to get printer info: {e}")
        return None


def cancel_job(printer_name: str, job_id: str) -> bool:
    """
    Cancels a print job.
    
    Args:
        printer_name: Name of the printer
        job_id: CUPS Job ID
        
    Returns:
        True if successful, False otherwise
    """
    conn = get_cups_connection()
    if not conn:
        return False
    
    try:
        job_id_int = int(job_id)
        conn.cancelJob(job_id_int)
        logger.info(f"Job {job_id} cancelled successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        return False

