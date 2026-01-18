#!/usr/bin/env python3
"""
Nado Trading Setup Analyzer - Quick Start Script

Run this script to start the application:
    python run.py

Or make it executable and run directly:
    chmod +x run.py
    ./run.py
"""
import uvicorn
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import get_settings


def main():
    """Start the Nado Trading Setup Analyzer server"""
    settings = get_settings()
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🚀 Nado Trading Setup Analyzer                          ║
    ║                                                           ║
    ║   Starting server...                                      ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    print(f"   📊 Dashboard:  http://localhost:{settings.port}")
    print(f"   📖 API Docs:   http://localhost:{settings.port}/docs")
    print(f"   🔄 Refresh:    Every {settings.data_refresh_interval} seconds")
    print()
    print("   Press Ctrl+C to stop the server")
    print()
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )


if __name__ == "__main__":
    main()

