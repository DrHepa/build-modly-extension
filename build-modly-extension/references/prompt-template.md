# Plantilla maestra para crear una extensión Modly

Sustituye los campos entre corchetes. Elimina los apartados que no correspondan, pero conserva las condiciones de validación.

```text
Usa $build-modly-extension para investigar, implementar, probar y dejar lista una extensión completa de Modly.

OBJETIVO
- Tipo de extensión: [model | process-python | process-js]
- Nombre visible: [NOMBRE]
- ID estable: [extension-id]
- Repositorio de la extensión: [https://github.com/CREADOR/REPO]
- Autor exacto del wrapper/integración: [AUTOR]
- Versión inicial: [1.0.0]
- Descripción breve: [DESCRIPCIÓN]

FUENTES
- Repositorio upstream: [URL]
- Revisión/release upstream que debe quedar fijada: [TAG O COMMIT]
- Repositorio de pesos en Hugging Face, si aplica: [OWNER/REPO]
- Licencia del wrapper: [LICENCIA]
- Licencia del código upstream: [LICENCIA]
- Licencia/restricciones de los pesos: [LICENCIA Y RESTRICCIONES]
- Versión/commit de Modly objetivo: [URL, TAG O COMMIT; si se omite, audita primero el upstream actual]

CONTRATO FUNCIONAL
- Entrada(s): [image | mesh | text | tipos admitidos por el fork verificado]
- Salida principal: [mesh | image | text | tipo admitido por el fork verificado]
- Nodo(s) y finalidad: [LISTA]
- Parámetros UI, tipos, defaults y rangos: [LISTA]
- Artefacto mínimo esperado en la prueba: [EJEMPLO]
- Hardware objetivo: [WINDOWS/LINUX/MAC, X64/ARM64, GPU, VRAM]
- Hardware realmente disponible para validar: [LISTA]

REQUISITOS OBLIGATORIOS
1. Audita primero el instalador, parser de manifest, downloader, registry/runner y workflow types del Modly objetivo. Distingue hechos, inferencias y campos no consumidos.
2. Audita el código upstream, su instalación, inferencia, serialización, dependencias nativas, pesos y licencias. Fija revisiones reproducibles.
3. Crea en la raíz del repo todos los archivos necesarios: manifest.json, setup.py, generator.py para model o processor.py/processor.js para process, README.md en inglés, licencia/avisos y pruebas útiles.
4. setup.py solo prepara el entorno aislado <extension>/venv. Debe aceptar el JSON actual de Modly y los argumentos posicionales heredados, ser reparable/idempotente, verificar imports y fallar con mensajes accionables. No debe descargar pesos.
5. Los pesos se descargan exclusivamente desde la UI de Modly. Declara por nodo hf_repo, download_check y filtros de prefijo válidos. Deben terminar en models/<extension-id>/<node-id>/ y el runtime solo puede cargar desde model_dir, sin descargas implícitas ni cachés globales.
6. El manifest debe incluir autoría real del creador del wrapper, source apuntando al repo de la extensión, nodes[] no vacío, tipos/valores/defaults compatibles con la UI y generator_class o entry correcto. Separa autor del wrapper, upstream, pesos y Modly en los créditos.
7. Para model, implementa correctamente load/generate/unload, progreso, cancelación, coerción de parámetros, salida existente y liberación de memoria. Para process Python, respeta el protocolo NDJSON; para JS, exporta la función CommonJS esperada.
8. El README debe estar en inglés e incluir Install from GitHub, descarga separada de pesos, uso, parámetros, outputs, requisitos, compatibilidad realmente probada, limitaciones, Repair/troubleshooting, upstream fijado, créditos y licencias.
9. No dejes TODO, REPLACE_ME, mocks, funciones no implementadas, rutas personales, ramas mutables, hashes falsos ni afirmaciones de compatibilidad sin prueba.
10. Ejecuta el validador incluido en `$SKILL_DIR/scripts/validate_extension.py` con `--strict`, las pruebas del protocolo si es process, instalación limpia, Repair, renderizado de parámetros, descarga desde UI al path exacto y al menos una ejecución real mínima. Resuelve `SKILL_DIR` desde la carpeta de la skill cargada, no desde el proyecto. Si no puedes ejecutar una fase por hardware o acceso, no la simules: indica el nivel alcanzado y entrega el comando/fixture exacto pendiente.

ENTREGA
- Repositorio completo y limpio.
- Resumen de decisiones de integración.
- Matriz de validación con PASS/FAIL/NOT RUN y evidencia breve.
- Lista explícita de cualquier limitación real restante.
- No declares “fully functional” hasta completar una ejecución real dentro de Modly.
```

## Variante corta

```text
Usa $build-modly-extension para convertir [URL UPSTREAM] en una extensión [model/process-python/process-js] de Modly, creada por [AUTOR] en [REPO EXTENSIÓN]. Audita el Modly objetivo [COMMIT], implementa setup/manifest/runtime/README inglés, mantén los pesos [HF_REPO] gestionados exclusivamente por la UI en models/<extension-id>/<node-id>/, valida Install from GitHub + Repair + parámetros + una ejecución real, y no dejes placeholders ni afirmaciones no probadas.
```
