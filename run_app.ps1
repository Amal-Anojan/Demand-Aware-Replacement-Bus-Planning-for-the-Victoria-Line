Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -c "from bus_allocation import fleet_needed; from streamlit_folium import st_folium; print('Application imports verified.')"
if ($LASTEXITCODE -ne 0) {
    throw "Import check failed. Install requirements into .venv before launching."
}
& "$PSScriptRoot\.venv\Scripts\python.exe" -m streamlit run app.py
