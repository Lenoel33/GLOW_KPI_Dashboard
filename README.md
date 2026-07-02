# GLOW Programme KPI & Trends Dashboard

A Streamlit dashboard for analysing GLOW activity attendance data from Excel or CSV files.

## What is improved

- Fixed `classify_programme_type` import issue.
- Reads Excel files across all sheets automatically.
- Lets users map columns manually if headers differ.
- Separates one-time and recurring programmes.
- Shows KPI cards for attendance, unique seniors, activities, and male participation.
- Shows **Male Attendances by Activity** and **Unique Male Attendances by Activity**.
- Every table has controls for:
  - Sort by any column
  - Ascending / Descending order
  - Search
  - Number of rows shown
  - CSV download of the currently sorted table
- Charts follow the same sorted table order.
- Cleaner colours, cards, visual layout, and easier-to-read charts.

## Run locally without admin access

Open PowerShell in this project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If you already activated your virtual environment, you can also run:

```powershell
python -m streamlit run app.py
```

## Run on a different localhost port

```powershell
python -m streamlit run app.py --server.port 8502
```

Open:

```text
http://localhost:8502
```

## Allow colleagues on the same Wi-Fi to access

```powershell
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8502
```

They should open:

```text
http://YOUR-COMPUTER-IP:8502
```

Your computer must stay on and connected to the same network.
