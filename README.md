# EIRA-reto-3

Prototipo para gestión y seguimiento de pacientes - Reto 3 EIRA

**Reto 3 · Consolidación y visualización del impacto social.** Es una aplicación local en Python + Streamlit para la
coordinación de EIRA Movimiento Rosa. Reúne atenciones y participaciones de distintas fuentes (Excel, CSV, PDF y fotos o
escaneos de formularios), permite revisarlas y corregirlas, y conserva la procedencia y la bitácora de cada cambio en SQLite.
También propone posibles coincidencias entre personas sin vincularlas automáticamente y produce un tablero y un informe
agregado sin nombres ni datos de salud.

> Todos los datos del repositorio son **ficticios**.

## Recorrido

La interfaz, en español, tiene cuatro pasos (pestañas):

1. **Cargar archivos**: Excel (.xlsx), CSV, PDF, PNG o JPG.
   - El botón **«Cargar datos de ejemplo»** carga `Datos/atenciones.xlsx` y `Datos/participaciones.xlsx`. Hay más botones para los ejemplos PDF, PNG, Excel y de formato en blanco.
   - En Excel y CSV se muestra una vista previa y propone qué columna corresponde a cada campo. Por ejemplo, `municipio`/`localidad`, `fecha_atencion`/`dia_evento`, y `nombres`+`apellidos` o `nombre_completo`. La persona confirma el mapeo.
   - En documentos se ve la página junto a los campos extraídos. Si el PDF tiene texto, se lee directo; si es PNG o PDF escaneado, se aplica OCR local en español.
2. **Revisar datos**:
   - Tabla editable con alertas (fecha inválida, sin municipio, edad fuera de rango, sin folio), estado al guardar (nuevo, sin cambios, folio existente con datos diferentes), posible coincidencia, procedencia (archivo y fila o página) y valor original.
   - Conflictos de folio: *Mantener lo guardado* / *Aplicar lo que llegó*.
   - Coincidencias entre personas: *Vincular* / *Personas distintas* / *Dejar pendiente*.
3. **Confirmar**: resumen y guardado en SQLite. Cada corrección queda en la bitácora con campo, valor anterior, valor nuevo, origen y fecha y hora.
4. **Ver tablero**:
   - Atenciones y participaciones por separado; las citas agendadas solo aparecen si la fuente las identifica.
   - Filtros por municipio, programa y periodo, gráfica por municipio y alertas de calidad.
   - Consulta individual (única vista con nombres y datos de salud), bitácora y fuentes.
   - Descarga del informe en **Excel** y **PDF**.

En la barra lateral, **«Reiniciar demo»** borra la base local después de una casilla de confirmación.

### Reglas que aplica

| Regla | Comportamiento |
|---|---|
| Identidad | EIRA no tiene identificador común de paciente. Se sugieren pares por similitud de escritura del nombre normalizado (sin mayúsculas, acentos ni espacios dobles; `token_sort_ratio` ≥ 92) y se muestran ambos nombres originales, edad, municipio, fuente y motivo. **Solo una decisión humana vincula registros.** El folio identifica una actividad, no a una persona. |
| Beneficiarias únicas | Mientras haya sugerencias pendientes se muestra «Total de beneficiarias únicas pendiente de validación». |
| Folios | Recargar el mismo archivo no duplica nada. Si un folio llega con datos diferentes, no se sobrescribe: queda para revisión. |
| Fechas inválidas | Se conserva el valor original (p. ej. `31/09/2026`), cuentan en el total general y se excluyen de los filtros por fecha. |
| Municipio vacío | Se agrupa en «Sin municipio». |
| Padecimiento | Solo se transcribe si la fuente lo registra explícitamente (columna `padecimiento`/`diagnostico`, o «Diagnóstico: …» en el formulario). Si falta: «No registrado». Nunca se deduce del nombre del estudio. |
| Documentos | Un formulario de una página por atención. Si no se encuentra folio ni nombre, el documento queda como «Sin datos suficientes». Si el OCR falla, se explica la causa y se permite la captura manual. Cada campo queda marcado como *Extraído automáticamente*, *Corregido en revisión* o *Captura manual*. |
| Informe | Lleva filtros aplicados, fecha de corte, fuentes, conteos, advertencias y ajustes manuales (los valores de nombre, edad y padecimiento se muestran como «(reservado)»). |

## Instalación

Requisitos: Python 3.12 o superior (probado con 3.14.3 en Windows 11) y Tesseract OCR con el idioma español.
**No se necesitan credenciales, claves de API ni servicios en la nube**: todo corre en el equipo.

### Windows

```powershell
winget install --id UB-Mannheim.TesseractOCR -e      # Tesseract (open source, Apache 2.0)
git clone https://github.com/maximolopez09-blip/EIRA-reto-3.git
cd EIRA-reto-3
mkdir tessdata
Invoke-WebRequest https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata -OutFile tessdata\spa.traineddata
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### Linux / macOS

```bash
sudo apt install tesseract-ocr tesseract-ocr-spa     # Debian/Ubuntu
# brew install tesseract tesseract-lang              # macOS
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Después abre http://localhost:8501.

### Configuración opcional

| Variable | Uso |
|---|---|
| `TESSERACT_CMD` | Ruta del ejecutable de Tesseract si no está en el PATH ni en `C:\Program Files\Tesseract-OCR\`. |
| `EIRA_DB` | Ruta de la base SQLite (por omisión `data/eira.db`). |

La app usa `tessdata/spa.traineddata` si existe; si no, el idioma `spa` instalado en el sistema.

### Dependencias de Python (`requirements.txt`)

streamlit, pandas, openpyxl, rapidfuzz (similitud de nombres), pypdfium2 (texto y render de PDF), pytesseract + Pillow (OCR),
fpdf2 (informe PDF y ejemplos), altair (gráficas) y pytest.

## Estructura

```
app.py                      Interfaz Streamlit (4 pasos)
eira/config.py              Campos, sinónimos de columnas, catálogo de municipios, umbrales
eira/tabular.py             Lectura de Excel/CSV, propuesta de mapeo, registros con procedencia
eira/documents.py           PDF con texto, PDF escaneado e imágenes (OCR), extracción de campos del formulario
eira/quality.py             Fechas, edades, municipios y alertas de calidad
eira/matching.py            Normalización y similitud de nombres; vínculos solo confirmados
eira/db.py                  SQLite: actividades, bitácora, conflictos de folio, decisiones de identidad
eira/report.py              Filtros, indicadores e informe Excel/PDF
scripts/generar_ejemplos.py Regenera los ejemplos ficticios de Datos/ejemplos/
Datos/                      Bases sintéticas originales (atenciones.xlsx, participaciones.xlsx)
Datos/ejemplos/             ejemplo_formulario.pdf/.png, ejemplo_escaneado.pdf, formato_en_blanco.pdf, ejemplo_atenciones_nuevas.xlsx
tests/                      Pruebas de aceptación, de documentos y recorrido de la interfaz
```

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

Resultado observado: **22 pruebas aprobadas** (Windows 11, Python 3.14.3, Tesseract 5.4.0). Si Tesseract no está instalado,
las pruebas de OCR se omiten.

### Pruebas de aceptación con las dos bases originales

| Caso | Resultado |
|---|---|
| Sin filtros | 120 atenciones y 80 participaciones ✔ |
| Sayula | 25 atenciones y 19 participaciones ✔ |
| PA-041 | Aparece en «Sin municipio» ✔ |
| PA-042 | Fecha inválida (`31/09/2026` conservada); cuenta en el total y se excluye al filtrar por periodo (79 + 1 excluida) ✔ |
| AT-001 / AT-002 (Ana García López) | Se sugieren como «posibles homónimas» (edad 34 vs 58, Sayula vs Tuxpan) y quedan **separadas** por defecto ✔ |
| AT-003 / PA-003 | Se sugiere revisión por «Escritura similar (98 %)»; ambos eventos se conservan ✔ |
| PA-006 y PA-008 | Se sugieren con AT-006 y AT-008 (mayúsculas y espacio doble) ✔ |
| Recargar las dos bases | 0 nuevos y 0 conflictos; los totales siguen en 120 / 80 ✔ |
| Misma base como CSV (`nombre_completo`) | Mismos conteos que el .xlsx ✔ |
| Decisiones de identidad | Se conservan al recargar; solo «Vincular» une registros ✔ |
| Informes Excel y PDF | Contienen filtros, fecha de corte, fuentes, conteos y advertencias, y ningún nombre ✔ |

Con las dos bases cargadas se generan 64 sugerencias: 53 «Alta» (mismo nombre, edad y municipio), 9 «posibles homónimas» y 2 «escritura similar».

Prueba adicional local (archivo no incluido en el repo): una versión de `atenciones.xlsx` con 129 filas y 9 folios repetidos
se guarda como 120 actividades, envía 8 folios con datos diferentes a revisión e ignora 1 duplicado idéntico.

### Documentos y Excel de ejemplo (folios nuevos)

Cada uno pasó por carga → revisión → confirmación → tablero.

| Archivo | Método | Campos extraídos automáticamente | Requirieron corrección |
|---|---|---|---|
| `ejemplo_formulario.pdf` (AT-201) | Texto del PDF | folio, fecha, nombre, edad, municipio, programa, servicio y padecimiento («BIRADS 2 - Hallazgos benignos») | Ninguno |
| `ejemplo_formulario.png` (AT-202) | OCR español | folio, fecha, nombre (con acentos), edad, municipio, programa y servicio. El padecimiento no viene en el formato, así que queda «No registrado» | Ninguno. En la prueba de interfaz se corrige a propósito el municipio (Tuxpan → Zapotiltic) para comprobar que queda como «Corregido en revisión» y se registra en la bitácora |
| `ejemplo_escaneado.pdf` (AT-202) | OCR de PDF escaneado | Igual que el PNG | Ninguno |
| `formato_en_blanco.pdf` | Texto del PDF | Solo el encabezado impreso (programa y servicio) | «Sin datos suficientes»; no se guarda sin captura manual de folio y nombre |
| Formatos reales de EIRA en blanco (PDF de citología y 2 fotos del formato mamario) | Texto / OCR | — | «Sin datos suficientes» en los tres |
| OCR no disponible (prueba con `TESSERACT_CMD` inválido) | Captura manual | — | Muestra «No se encontró Tesseract…»; los campos capturados quedan como «Captura manual» |
| `ejemplo_atenciones_nuevas.xlsx` (AT-301..306) | Columnas con otros encabezados | Las 9 columnas se mapean solas (`Folio`, `Fecha`, `Municipio de residencia`, `Nombre completo`, `Edad`, `Programa`, `Servicio`, `Padecimiento`, `tipo_registro`) | Ninguno. Además: AT-305 es «Cita agendada» y no suma a atenciones; AT-302 trae el padecimiento «Cervicitis»; AT-304 no tiene municipio; se sugiere AT-303 «Teresa Navaro Flores» con AT-004 |

## Limitaciones del prototipo

- La extracción documental está pensada para el formulario de revisión mamaria con etiquetas impresas (folio, fecha de atención, nombre, edad, residencia, diagnóstico). Solo se procesa la primera página. La letra manuscrita y las fotos con poca luz o inclinadas no están garantizadas; para esos casos queda la corrección o captura manual.
- La similitud de nombres usa un umbral fijo (92) y no ve apodos ni nombres abreviados («Gaby», «Ma.»). Esos casos dependen de la revisión humana.
- El catálogo de municipios incluye solo los 5 de los datos de ejemplo, con el alias «Ciudad Guzmán» → Zapotlán el Grande.
- Sin autenticación ni roles: cualquiera con acceso al equipo puede ver y modificar los datos.
- SQLite local sin cifrar, pensado para una sola persona usuaria a la vez.

## Controles pendientes para un piloto real

Este repositorio es un **prototipo local con datos ficticios**. Antes de usar datos reales de pacientes, EIRA necesita como mínimo:

- **Acceso por roles**: captura, revisión, consulta clínica y dirección (solo agregados), con inicio de sesión individual y registro de quién hizo cada cambio. Hoy la bitácora guarda qué cambió y cuándo, pero no quién.
- **Protección de la base**: cifrado en reposo y en tránsito, servidor o equipo controlado, y nada de datos personales en hojas compartidas ni en el repositorio.
- **Respaldos** automáticos y probados, con política de retención.
- **Privacidad**: aviso de privacidad y consentimiento conforme a la LFPDPPP, minimización de datos sensibles y procedimiento para derechos ARCO.
- **Costos**: hospedaje, mantenimiento, soporte y capacitación. El OCR local (Tesseract) no tiene costo de licencia.
- **Reglas de identificación que EIRA debe validar**: qué atributos bastan para proponer una coincidencia (nombre, edad, municipio, fecha de nacimiento, teléfono), el umbral de similitud, quién puede vincular y cómo deshacer un vínculo, y si conviene adoptar un identificador interno estable (ver Reto 1).
- **Catálogos oficiales** de municipios, programas y servicios, y validación de los formatos reales escaneados.

## Licencia

MIT (ver `LICENSE`).
