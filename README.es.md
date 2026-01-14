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
 - **🎯 Fallback Inteligente**: Recuperación automática entre múltiples fuentes de metadados.
 - **🏷️ Sistema de Etiquetas**: Crea etiquetas personalizadas, colores e iconos para organizar tus juegos.
 - **📑 Registro de Actividades**: Historial completo de escaneos, cambios de archivos y eventos del sistema.
 - **🌐 Soporte Multi-idioma**: Interfaz disponible en inglés, portugués (BR) y español.
 - **📈 Estadísticas Detalladas**: Contadores en tiempo real de juegos, archivos y espacio en disco (global y por carpeta).
 - **📂 Historial Amigable**: Vista de acordeón en el modal de detalles que prioriza la actualización más reciente.
 - **⚖️ Cálculo Real de Tamaño**: La vista de lista muestra la suma real de todos los archivos en propiedad (Base + Updates + DLCs).
 - **🔍 Filtrado Avanzado**: Combina género, etiquetas personalizadas y estado del contenido (Falta Update/DLC).
 - **🛡️ Seguridad de API**: Limitación de tasa integrada y verificaciones de autenticación mejoradas.
 - **💾 Gestión de Backups**: Sistema nativo para copia de seguridad de la base de datos y configuraciones.
 - **⚙️ Fuentes Configurables**: Interfaz web completa para gestionar, priorizar y monitorear fuentes de TitleDB.
 - **📊 Caché Mejorado**: Caché de biblioteca inteligente con TTL configurable.

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

# Fuentes TitleDB

## ¿Qué son las fuentes TitleDB?
Las fuentes TitleDB proporcionan los metadatos sobre juegos, actualizaciones y DLCs de Switch. MyFoil utiliza estos datos para:
- Identificar sus archivos de juegos
- Verificar si tiene las últimas actualizaciones
- Detectar DLCs faltantes
- Mostrar nombres y arte de los juegos

## Fuentes Predeterminadas
MyFoil viene con cuatro fuentes preconfiguradas (por orden de prioridad):

1. **tinfoil.media** - Prioridad 1 (Activado)
   - API oficial de Tinfoil
   - Confiable y rápido
   - Acceso directo vía JSON

2. **MyFoil (Legacy)** - Prioridad 2 (Activado)
   - Fuente original basada en ZIP (heredada de Ownfoil)
   - Mantenida para máxima compatibilidad
   - Actualizada mediante workflows de enlaces nightly

3. **blawar/titledb (GitHub)** - Prioridad 3 (Activado)
   - La fuente original y más completa de la comunidad
   - Actualizada frecuentemente por la comunidad
   - Directo del contenido bruto de GitHub

4. **julesontheroad/titledb (GitHub)** - Prioridad 4 (Activado)
   - Espejo confiable de metadatos TitleDB
   - Excelente opción de fallback
   - Alojado en GitHub

## Cómo Funciona

Cuando MyFoil necesita actualizar el TitleDB:

1. Intenta primero con la **fuente habilitada de mayor prioridad**.
2. Si la descarga falla, intenta automáticamente con la siguiente fuente en la lista.
3. Si todas las fuentes fallan, mantiene los datos existentes y registra el error.
4. El proceso está optimizado para descargar solo los JSON necesarios, ahorrando ancho de banda y tiempo.

# Referencia de la API (Fuentes TitleDB)

Puedes gestionar las fuentes a través de la interfaz web o la API:

### Listar Fuentes
```bash
curl http://localhost:8465/api/settings/titledb/sources
```

### Añadir una Fuente
```bash
curl -X POST http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "Mi Mirror",
    "base_url": "https://mi-servidor.com/titledb",
    "priority": 5,
    "enabled": true
  }'
```

### Actualizar una Fuente
```bash
curl -X PUT http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "blawar/titledb (GitHub)",
    "enabled": false
  }'
```

### Eliminar una Fuente
```bash
curl -X DELETE http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "Mi Mirror"
  }'
```

### Forzar Actualización
```bash
curl -X POST http://localhost:8465/api/settings/titledb/update \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ="
```

## Creación de Su Propia Fuente

Para alojar su propio mirror de TitleDB:

1. Clone blawar/titledb: `git clone https://github.com/blawar/titledb`
2. Sirva los archivos a través de HTTP/HTTPS
3. Añada su fuente a MyFoil con la URL base
4. Archivos requeridos:
   - `cnmts.json` - Metadatos de contenido
   - `versions.json` - Información de versión
   - `versions.txt` - Lista de versiones
   - `languages.json` - Mapeo de idiomas
   - `titles.{REGION}.{LANG}.json` - Nombres de juegos (ej: `titles.US.en.json`)

## Resolución de Problemas

**¿Las actualizaciones fallan?**
- Compruebe el estado de la fuente en la respuesta de la API
- Revise el campo `last_error` para cada fuente
- Intente forzar una actualización
- Verifique su conexión a Internet

**¿Quiere actualizaciones más rápidas?**
- Deshabilite las fuentes más lentas
- Ajuste las prioridades (número menor = mayor prioridad)
- Aloje su propio mirror más cerca de su servidor

---

# Hoja de Ruta y Mejoras
Para más detalles sobre el desarrollo futuro y las funcionalidades planeadas, vea el archivo [ROADMAP_MELHORIAS.md](ROADMAP_MELHORIAS.md).
