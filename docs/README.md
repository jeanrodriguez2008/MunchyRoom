# Manual de MunchyRoom

Este directorio contiene el **Manual de usuario y administrador** de MunchyRoom y los archivos necesarios para regenerarlo.

| Archivo | Uso |
|---|---|
| `Manual_MunchyRoom_Usuario_Administrador.pdf` | Documento final listo para imprimir o compartir. |
| `manual_munchyroom.html` | Fuente del manual con estilos de impresión y contenido. |
| `generate_manual_pdf.py` | Añade índice con números de página, pie de página, metadatos y marcadores al PDF. |

## Regenerar el PDF

1. Edita el contenido en `manual_munchyroom.html`.
2. Genera el PDF base con Chrome en modo headless (ajusta la ruta si el proyecto cambia de ubicación):

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --headless=new --disable-gpu --no-pdf-header-footer `
  --print-to-pdf="docs\_manual_raw.pdf" `
  --virtual-time-budget=12000 `
  --run-all-compositor-stages-before-draw `
  "file:///C:/Users/jcrodriguez/Documents/Programacion%20en%20Python/MunchyRoom/docs/manual_munchyroom.html"
```

3. Procesa el PDF base:

```powershell
python docs/generate_manual_pdf.py
```

4. Elimina el archivo temporal:

```powershell
Remove-Item docs\_manual_raw.pdf
```

El resultado es `docs/Manual_MunchyRoom_Usuario_Administrador.pdf`, con:

- Portada corporativa y contraportada visual.
- Índice con números de página.
- Pie de página y numeración en todas las páginas de contenido.
- Marcadores navegables en el visor de PDF.
- Metadatos de título, autor y asunto.
