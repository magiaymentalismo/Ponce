# Atrapalo_clean

Proyecto mínimo y funcional para generar un dashboard estático sin dependencias externas.

## Cómo usar

```bash
cd Atrapalo_clean
python3 generate_static_dashboard.py
open dashboard_static.html   # en macOS
# o: start dashboard_static.html  # en Windows
# o: xdg-open dashboard_static.html  # en Linux
```

## Datos

- El script busca `dist/last_payload.json`. Si no existe, usa `data/sample_payload.json`.
- Puedes reemplazar `dist/last_payload.json` con tu payload real (mismo formato).

## Personalización

- Edita `templates/dashboard_template.html` para cambiar estilos/estructura.
- El gráfico es un SVG inline sin librerías; puedes modificarlo libremente.
