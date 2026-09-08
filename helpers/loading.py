"""
Loading and animation utilities for user feedback.
Provides animated loading indicators for terminal and UI.
"""

import time
import sys
import threading
from contextlib import contextmanager
import streamlit as st


def print_animated_dots(message: str, duration: float = 3.0, interval: float = 0.5):
    """
    Print animated dots that update on the same line (Option A).
    Shows progress in terminal with increasing dots.
    
    Args:
        message: Base message to display
        duration: Total duration in seconds
        interval: Time between dot updates in seconds
    
    Example:
        print_animated_dots("Loading data", duration=2.0, interval=0.3)
        # Output: Loading data .
        #         Loading data ..
        #         Loading data ...
        #         Loading data ✓
    """
    start_time = time.time()
    dot_count = 0
    
    while time.time() - start_time < duration:
        # Update same line with carriage return
        sys.stdout.write(f"\r{message} {'.' * (dot_count % 4)}\033[K")
        sys.stdout.flush()
        dot_count += 1
        time.sleep(interval)
    
    # Final message with checkmark
    sys.stdout.write(f"\r{message} ✓\033[K\n")
    sys.stdout.flush()


@contextmanager
def animate_progress(message: str, interval: float = 0.3):
    """
    Context manager that animates dots while code executes.
    Automatically replaces dots with checkmark when done.
    
    Args:
        message: Base message to display
        interval: Time between dot updates in seconds
    
    Example:
        with animate_progress("Space detection in progress"):
            all_spaces = o.get_spaces()  # Dots animate during this
        # Output: Space detection in progress ...
        #         Space detection in progress ✓ (when done)
    """
    # Flag to control animation thread
    stop_animation = threading.Event()
    
    def animate():
        """Animation thread function"""
        dot_count = 0
        while not stop_animation.is_set():
            sys.stdout.write(f"\r{message} {'.' * (dot_count % 4)}\033[K")
            sys.stdout.flush()
            dot_count += 1
            time.sleep(interval)
    
    # Start animation in background thread
    animation_thread = threading.Thread(target=animate, daemon=True)
    animation_thread.start()
    
    try:
        yield
    finally:
        # Stop animation and show checkmark
        stop_animation.set()
        animation_thread.join(timeout=0.5)
        sys.stdout.write(f"\r{message} ✓\033[K\n")
        sys.stdout.flush()


@contextmanager
def spinner_context(message: str):
    """
    Context manager that displays a spinner during operation.
    Spinner stays visible until context exits.
    
    Args:
        message: Message to display with spinner
    
    Example:
        with spinner_context("🔍 Querying openBIS..."):
            df = o.get_samples(permId=perm_id, props="$name").df
        # Spinner displays until context exits
    """
    with st.spinner(message):
        yield


