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
1. **Cargar archivos**: Excel (.xlsx), CSV, PDF, PNG o JPG, o los botones de ejemplo (atenciones y participaciones, formato escaneado en PDF, formato en fotos, Excel de jornada, formato en blanco).
   - Cada archivo muestra un resumen simple, por ejemplo «Reconocimos atenciones.xlsx: 120 atenciones».
   - Las columnas se reconocen solas (`municipio`/`localidad`, `fecha_atencion`/`dia_evento`, `nombres`+`apellidos` o `nombre_completo`). La vista previa y la asignación de columnas están en **«Ajustar columnas (avanzado)»**, que se abre solo si falta algo.
   - Los PDF con texto se leen directo; las fotos o PDF escaneados de los formatos de EIRA llenados a mano se enderezan y se leen campo por campo (ver «Lectura de formatos llenados a mano»); las fotos de páginas sueltas se unen solas. Cualquier otro documento pasa por OCR local en español.
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
| Documentos | Un formato por atención (las dos páginas del formato mamario pueden venir en un PDF o en dos fotos, que se unen solas). Las lecturas dudosas se señalan para revisarlas contra la imagen. Si no se encuentra folio ni nombre, el documento queda como «Sin datos suficientes». Si el OCR falla, se explica la causa y se permite la captura manual. Cada campo queda marcado como *Extraído automáticamente*, *Corregido en revisión* o *Captura manual*. |
| Informe | Lleva filtros aplicados, fecha de corte, fuentes, conteos, advertencias y ajustes manuales (los valores de nombre, edad y padecimiento se muestran como «(reservado)»). |

## Lectura de formatos llenados a mano

Los ejemplos de `Datos/ejemplos/` imitan los formatos reales («Formato de revisión mamaria», 2 páginas, y «Solicitud y reporte de
citología cervical») llenados con letra manuscrita y datos ficticios: fotos de celular (perspectiva, sombra, giro, desenfoque, JPEG)
y escaneos a 110 ppp. `valores_esperados.json` guarda lo que se escribió en cada uno.

Pasos del preproceso, todos locales y con herramientas open source:

1. **Hoja**: se localiza el papel en la foto y se corrige la perspectiva; se igualan sombras e iluminación (OpenCV).
2. **Registro**: se identifica formato y página con las palabras impresas (Tesseract) y, si no se alcanzan a leer, comparando
   el dibujo con el formato en blanco; la imagen se lleva a las coordenadas de la plantilla.
3. **Recorte**: de cada campo se quita lo impreso (rayas, marcos, etiquetas) comparando con el formato en blanco.
4. **Lectura**: cada recorte se lee con RapidOCR (modelos PP-OCR en ONNX); las casillas de un solo dígito, con un clasificador de cifras.
5. **Registro EIRA**: se arma folio, fecha, nombre, edad, municipio y padecimiento (solo si la casilla de resultado está marcada).

Exactitud medida con `scripts/medir_lectura.py` sobre 24 documentos generados aparte (`generar_ejemplos.py --lote 24 --semilla 11`):

| Tipo de campo | Escaneo, exactos | Foto, exactos |
|---|---|---|
| Números (fechas, edad, teléfonos…) | 83% | 76% |
| Códigos de casilla | 82% | 85% |
| Folio | 83% | 75% |
| Texto libre (nombre, domicilio…) | 41% (82% de parecido) | 52% (90% de parecido) |

En el registro: edad 22/24, folio 19/24, municipio 17/24, fecha 14/24 y nombre 7/24 exactos. **La letra corrida no se lee de forma
confiable**: el nombre casi siempre requiere corrección y por eso se marca para revisión salvo lectura muy segura. La lectura es
una propuesta que la persona confirma en «2. Revisar datos», con la imagen al lado. Estas cifras vienen de letra sintética
(tipografías manuscritas); con formatos reales pueden ser distintas y conviene medirlas con un lote real.

La primera vez, RapidOCR descarga sus modelos (unos 30 MB) a la carpeta del paquete; después funciona sin conexión.

## Instalación

Requisitos: Python 3.12 o superior (probado con 3.14.3 en Windows 11) y Tesseract OCR con el idioma español
(sin Tesseract los formatos llenados a mano se siguen leyendo; solo se pierde el OCR de otros documentos).
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

streamlit, pandas, openpyxl, rapidfuzz (similitud de nombres), pypdfium2 (texto y render de PDF), pytesseract + Pillow (OCR de texto impreso),
OpenCV + NumPy (enderezado y recorte de campos), RapidOCR + ONNX Runtime (lectura de letra manuscrita),
fpdf2 (informe PDF y ejemplos), altair (gráficas) y pytest.

## Estructura

```
app.py                      Interfaz Streamlit (4 pasos)
eira/config.py              Campos, sinónimos de columnas, catálogo de municipios, umbrales
eira/tabular.py             Lectura de Excel/CSV, propuesta de mapeo, registros con procedencia
eira/documents.py           PDF con texto, PDF escaneado e imágenes (OCR), extracción de campos del formulario
eira/lectura.py             Preproceso: hoja, perspectiva, sombras, registro contra la plantilla y recorte de cada campo
eira/manuscrito.py          Lectura de cada recorte (RapidOCR, clasificador de cifras) y armado del registro
eira/formatos/*.json        Coordenadas y tipo de cada campo de los formatos (mamario: 2 páginas; citología: 1)
eira/modelos/mnist-12.onnx  Clasificador de cifras para las casillas de código (ONNX Model Zoo, MIT)
scripts/plantillas.py       Regenera Datos/formatos/ y eira/formatos/
scripts/medir_lectura.py    Mide la lectura contra los valores con que se generaron los ejemplos
scripts/fuentes/            Tipografías manuscritas (licencia OFL) para los ejemplos
eira/quality.py             Fechas, edades, municipios y alertas de calidad
eira/matching.py            Normalización y similitud de nombres; vínculos solo confirmados
eira/db.py                  SQLite: actividades, bitácora, conflictos de folio, decisiones de identidad
eira/report.py              Filtros, indicadores e informe Excel/PDF
scripts/generar_ejemplos.py Regenera los ejemplos ficticios de Datos/ejemplos/
Datos/                      Bases sintéticas originales (atenciones.xlsx, participaciones.xlsx)
Datos/formatos/             Formatos en blanco: revision_mamaria.pdf (redibujado) y citologia_cervical.pdf
Datos/ejemplos/             Formatos llenados a mano: *_foto.png, *_escaneo.pdf, valores_esperados.json; formato en blanco; Excel
tests/                      Pruebas de aceptación, de documentos y recorrido de la interfaz
.streamlit/config.toml      Tema visual (claro, rosa institucional, letra grande)
```

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

Incluye recorridos completos de la interfaz con `streamlit.testing`. Las pruebas de OCR se omiten si Tesseract no está instalado, y las de formatos llenados a mano si falta RapidOCR.

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
| `mamaria_foto.png` + `mamaria_foto_pagina2.png` (AT-201) | Formato llenado a mano (foto) | folio, fecha, nombre, edad, municipio y padecimiento («BIRADS 2 - Hallazgos benignos», de la casilla de la página 2) | Ninguno; la fecha sale marcada como dudosa |
| `mamaria_escaneo.pdf` (AT-202) | Formato llenado a mano (PDF escaneado, 110 ppp) | folio, fecha, edad, municipio, padecimiento | Nombre (una letra) |
| `citologia_foto.png` (AT-203) | Formato llenado a mano (foto) | folio, fecha | Nombre, edad y diagnóstico: es la foto más difícil; los tres salen marcados como dudosos |
| `citologia_escaneo.pdf` (AT-204) | Formato llenado a mano (PDF escaneado) | folio, fecha, edad, padecimiento | Nombre y municipio (marcados como dudosos) |
| `formato_en_blanco_escaneo.pdf` | Formato reconocido, sin nada escrito | — | «Sin datos suficientes»; no se guarda sin captura manual de folio y nombre |
| Documento que no es un formato, sin Tesseract (`TESSERACT_CMD` inválido) | Captura manual | — | Muestra «No se encontró Tesseract…»; los campos capturados quedan como «Captura manual» |
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
