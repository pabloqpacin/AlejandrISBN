AlejandrISBN — carpeta seed
============================

Pon aquí un JSON exportado del inventario para restaurarlo o cargarlo
la primera vez.

Pasos
-----
1. Copia tu archivo, por ejemplo:  mi-biblioteca.json
2. Cierra AlejandrISBN por completo (la ventanita de control)
3. Vuelve a abrir AlejandrISBN.exe

La app importa los libros al arrancar.
No pisa libros que ya existan con el mismo ISBN.

Formato
-------
Vale el JSON que descarga la propia web (Exportar), con forma:

  { "books": [ { "isbn": "...", "title": "...", ... }, ... ] }

También puedes usar CSV (con columna isbn y/o title).

Notas
-----
- Los datos viven en:  %LOCALAPPDATA%\AlejandrISBN\
- Si cambias el JSON y quieres reimportarlo, renómbralo o edítalo
  (la app recuerda el contenido ya aplicado).
