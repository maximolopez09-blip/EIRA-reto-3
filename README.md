# EIRA-reto-3

Prototipo para gestión y seguimiento de pacientes - Reto 3 EIRA

**Reto 3 · Consolidación y visualización del impacto social.** Es una aplicación local en Python + Streamlit para la
coordinación de EIRA Movimiento Rosa. Reúne atenciones y participaciones de distintas fuentes (Excel, CSV, PDF y fotos o
escaneos de formularios), permite revisarlas y corregirlas, y conserva la procedencia y la bitácora de cada cambio en SQLite.
También propone posibles coincidencias entre personas sin vincularlas automáticamente y produce un tablero y un informe
agregado sin nombres ni datos de salud.

> Todos los datos del repositorio son **ficticios**.

## Recorrido

La interfaz está en español, con tema claro en rosa institucional y letra grande. Es un asistente de cuatro pasos con barra de avance y botones «Siguiente» y «Atrás». Se abre en el tablero.

- **Tablero (pantalla de inicio)**:
  - Cifras grandes de atenciones, participaciones y beneficiarias únicas por separado. Las citas agendadas aparecen solo si la fuente las identifica.
  - Filtros por municipio, programa y periodo, y gráfica por municipio.
  - Botones principales: **«Agregar datos»**, **«Descargar informe»** (Excel o PDF) y **«Buscar beneficiaria»**.
  - Si hay pendientes, un aviso con el botón **«Revisar ahora»**. Los avisos de calidad, las fuentes y la bitácora están en secciones desplegables.
1. **Cargar archivos**: Excel (.xlsx), CSV, PDF, PNG o JPG, o los botones de ejemplo (atenciones y participaciones, formulario PDF, formulario en foto, Excel de jornada, formato en blanco).
   - Cada archivo muestra un resumen simple, por ejemplo «Reconocimos atenciones.xlsx: 120 atenciones».
   - Las columnas se reconocen solas (`municipio`/`localidad`, `fecha_atencion`/`dia_evento`, `nombres`+`apellidos` o `nombre_completo`). La vista previa y la asignación de columnas están en **«Ajustar columnas (avanzado)»**, que se abre solo si falta algo.
   - Los PDF con texto se leen directo; los PNG o PDF escaneados pasan por OCR local en español.
2. **Revisar datos**: solo se muestran tarjetas de lo que necesita atención («De 200 registros, 198 están listos y 2 necesitan tu atención»).
   - Cada tarjeta explica el problema en lenguaje simple y trae el campo para corregirlo; lo demás pasa solo.
   - Los documentos se muestran junto a sus campos, cada uno marcado como *Extraído automáticamente*, *Corregido en revisión* o *Captura manual*.
   - «Buscar y corregir cualquier registro (avanzado)» permite editar cualquier otro registro.
3. **Confirmar**: resumen (nuevas, ya guardadas, folios con datos distintos, correcciones) y botón **«Guardar»**. Cada corrección queda en la bitácora con campo, valor anterior, valor nuevo, origen y fecha y hora.
4. **Ver tablero**: se regresa al inicio con las cifras actualizadas.

**Revisión de pendientes** (desde «Revisar ahora»):
- Las posibles coincidencias se muestran **una por una**: dos fichas lado a lado (nombre original, edad, municipio, actividad, de dónde viene), el motivo de la sugerencia y los botones **«Es la misma persona»**, **«Son personas distintas»** y **«Decidir después»**, con contador «Coincidencia 1 de 64».
- Los casos claros (mismo nombre, edad y municipio) se pueden revisar en bloque, después de ver la lista y marcar una casilla.
- Los folios repetidos con datos distintos se resuelven con «Conservar lo guardado» o «Usar lo que llegó».

**Buscar beneficiaria**: es la única vista con nombres y datos de salud. Muestra edad y municipio con su fuente, las actividades unidas por revisión humana, las fechas de atención y las citas, solo si la fuente las identifica.

En la barra lateral (oculta por defecto), **«Reiniciar demo»** borra la base local después de una casilla de confirmación.

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

### Publicar en Streamlit Community Cloud

1. Entra a https://share.streamlit.io con la cuenta de GitHub dueña del repositorio y pulsa **Create app** → **Deploy a public app from GitHub**.
2. Repositorio `maximolopez09-blip/EIRA-reto-3`, rama `main`, archivo principal `app.py`.
3. En **Advanced settings** elige Python 3.13. No se necesitan *secrets*.
4. Pulsa **Deploy**. Streamlit instala `requirements.txt` y, desde `packages.txt`, Tesseract con el idioma español.

En la nube, la base SQLite es **compartida por todos los visitantes** y **temporal**: Streamlit la borra cuando reinicia o
actualiza la app. Úsala solo con los datos ficticios de la demo.

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
.streamlit/config.toml      Tema visual (claro, rosa institucional, letra grande)
```

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

Resultado observado: **24 pruebas aprobadas**, incluidos recorridos completos de la interfaz con `streamlit.testing` (Windows 11, Python 3.14.3, Tesseract 5.4.0). Si Tesseract no está instalado,
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
