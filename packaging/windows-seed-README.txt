AlejandrISBN — carpeta seed
============================

Opción A (recomendada, con la app abierta)
------------------------------------------
En la web: Importar → JSON o CSV (mismo formato que Exportar).
No hace falta reiniciar.

Opción B (al arrancar)
----------------------
1. Copia tu archivo aquí, por ejemplo:  mi-biblioteca.json
2. Cierra AlejandrISBN por completo (la ventanita de control)
3. Vuelve a abrir AlejandrISBN.exe

La app importa los libros al arrancar.
No pisa libros que ya existan con el mismo ISBN.

Formato
-------
Vale el JSON que descarga la propia web (Exportar → JSON):

  { "books": [ { "isbn": "...", "title": "...", ... }, ... ] }

Notas
-----
- Los datos viven en:  %LOCALAPPDATA%\AlejandrISBN\
- Si usas la opción B y cambias el JSON para reimportarlo, renómbralo o edítalo
  (la app recuerda el contenido ya aplicado por checksum).
