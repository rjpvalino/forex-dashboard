@echo off
echo Starting Forex Live Dashboard...
echo Open your browser and go to: http://localhost:5000
echo Press Ctrl+C to stop the server.
echo.
cd /d "%~dp0"
python app.py
pause
