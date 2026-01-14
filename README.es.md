# MyFoil

**MyFoil** es un fork mejorado de [Ownfoil](https://github.com/a1ex4/ownfoil) - un gestor de biblioteca de Nintendo Switch que convierte tu colección en una tienda Tinfoil totalmente personalizable y autoalojada.

---

[🇺🇸 English](README.md) | [🇧🇷 Português](README.pt-br.md) | [🇪🇸 Español](README.es.md)

---

---

### ⚠️ Avisos Importantes (Disclaimers)

1.  **Prueba de Concepto**: Este proyecto es una prueba de concepto y está destinado únicamente a fines educativos. **No alienta ni promueve la piratería** ni la infracción de los derechos de autor de ninguna persona o empresa. Los usuarios son responsables de utilizar el software de conformidad con las leyes locales.
2.  **Asistido por IA**: Todas las mejoras y funcionalidades añadidas a este fork fueron implementadas con la ayuda de **Inteligencia Artificial**.

---

## ✨ Funcionalidades Mejoradas (vs Ownfoil)

 - **🔄 Múltiples Fuentes de TitleDB**: Soporte para blawar/titledb, tinfoil.media y fuentes personalizadas.
 - **⚡ Actualizaciones más Rápidas**: Descargas directas de JSON en lugar de extracción de ZIP.
 - **🎯 Fallback Inteligente**: Recuperación automática entre múltiples fuentes.
 - **🏷️ Sistema de Etiquetas**: Crea etiquetas personalizadas para organizar tu biblioteca más allá de los géneros.
 - **📑 Registro de Actividades**: Realiza un seguimiento de cada cambio y escaneo en tu biblioteca.
 - **🌐 Soporte Multi-idioma**: Interfaz totalmente traducible (EN, PT-BR, ES).
 - **⚙️ Fuentes Configurables**: Gestiona las fuentes de TitleDB a través de la interfaz web.
 - **📊 Cache Mejorado**: Caché inteligente con TTL configurable.

## 🎯 Funcionalidades Principales

 - Autenticación multiusuario.
 - Interfaz web para configuración.
 - Interfaz web para navegar por la biblioteca.
 - Identificación de contenido mediante descifrado o nombre de archivo.
 - Personalización de la tienda Tinfoil.
 - Watchdog de biblioteca para actualizaciones automáticas.

> **Nota**: Este proyecto es un fork en desarrollo activo. Basado en Ownfoil por [a1ex4](https://github.com/a1ex4/ownfoil).

# Índice
- [Instalación](#instalación)
- [Funcionalidades Mejoradas](#funcionalidades-mejoradas)
- [Uso](#uso)
- [Fuentes TitleDB](#fuentes-titledb)
- [Migración desde Ownfoil](#migración-desde-ownfoil)

# Instalación

## Usando Python (Recomendado para Desarrollo)

Clona el repositorio usando `git`, instala las dependencias y listo:

```bash
git clone https://github.com/fernandodimas/MyFoil
cd MyFoil
pip install -r requirements.txt
python app/app.py
```

La tienda estará accesible en `http://localhost:8465`

## Usando Docker (Próximamente)

Las imágenes de Docker estarán disponibles pronto. Por ahora, puedes construir la tuya:

```bash
docker build -t myfoil .
docker run -d -p 8465:8465 \
  -v /tu/directorio/de/juegos:/games \
  -v ./config:/app/config \
  --name myfoil myfoil
```

# Uso
Una vez que MyFoil esté en funcionamiento, puedes acceder a la interfaz web de la tienda navegando a `http://<IP de la computadora/servidor>:8465`.

## Administración de Usuarios
MyFoil requiere la creación de un usuario `admin` para habilitar la autenticación en tu tienda. Ve a `Configuración` para crear el primer usuario con derechos de administrador.

## Administración de la Biblioteca
En la página de `Configuración`, bajo la sección `Biblioteca`, puedes añadir directorios que contengan tu contenido. MyFoil escaneará el contenido e intentará identificar cada archivo compatible (`nsp`, `nsz`, `xci`, `xcz`).

---

# Hoja de Ruta (Roadmap) de Futuras Implementaciones
- **Renombre Automático**: Renombrar archivos físicos siguiendo patrones configurables.
- **Filtrar por Wishlist**: Visualizar artículos deseados directamente en la biblioteca.
- **Búsqueda Universal**: Buscar en todo el catálogo de TitleDB incluso para artículos que no posees.
- **Optimización Móvil**: Diseño mejorado para pantallas pequeñas.
- **Limpieza del Proyecto**: Eliminación de códigos y archivos heredados no utilizados.
