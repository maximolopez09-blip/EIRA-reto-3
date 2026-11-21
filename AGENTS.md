# Notas para agentes

- Entorno: Windows + PowerShell. Usa `.\.venv\Scripts\python.exe` (Python 3.14). Git está en `C:\Program Files\Git\cmd\git.exe` y Tesseract en `C:\Program Files\Tesseract-OCR\`; el idioma `spa` está en `tessdata/` (ignorada por git).
- Pruebas: `.\.venv\Scripts\python.exe -m pytest -q tests` (las de OCR se omiten si no hay Tesseract).
- App: `.\.venv\Scripts\python.exe -m streamlit run app.py` → http://localhost:8501. Base de datos en `data/eira.db`; se puede cambiar con `EIRA_DB`.
- Ejemplos ficticios: `.\.venv\Scripts\python.exe scripts\generar_ejemplos.py` regenera `Datos/ejemplos/`.
- `Datos/` lleva D mayúscula y no se renombra. La licencia es MIT. `Original Data/` y `control_pruebas.xlsx` (fuera del repo) nunca se cargan en la app.
