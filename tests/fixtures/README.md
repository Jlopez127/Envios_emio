# Fixtures de tests

Los tests **no dependen de ningún archivo real**. Todos los fixtures de manifiestos
(cobertura parcial, sufijo Dropbox `" (1)"`, dedupe por mtime, hoja CLIENTES ausente,
archivos ignorados, guía con error de digitación) se generan **al vuelo en `tmp_path`**
desde `tests/conftest.py`, con datos SINTÉTICOS. No se commitea ningún `.xlsx`.

## Exports reales (opcional, LOCAL)

Si querés probar el modo `excel` contra un export **real** de tu proveedor, colocá el
archivo acá con el patrón `YYYY-MM-DD-<id>-ASTRID.xlsx` y corré la app con
`DATASOURCE_ASTRID=excel EXCEL_DIRECTORIO_LOCAL=tests/fixtures`.

- `tests/fixtures/*.xlsx` está en **`.gitignore`**: los exports reales traen PII de
  clientes (nombres/direcciones/teléfonos) y **nunca** se commitean. Se quedan LOCAL.
- La suite de tests **no** los usa: usa los sintéticos de `conftest.py`.
