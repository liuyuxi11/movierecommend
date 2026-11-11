$env:PYTHONPATH = '\backend;' + $env:PYTHONPATH
Push-Location 
try {
    & '.venv_new\Scripts\python.exe' 'app/main.py'
} finally {
    Pop-Location
}

