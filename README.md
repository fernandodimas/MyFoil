# MyFoil

# MyFoil

**MyFoil** is an enhanced fork of [Ownfoil](https://github.com/a1ex4/ownfoil) - a Nintendo Switch library manager that turns your library into a fully customizable and self-hosted Tinfoil Shop. 

## ✨ Enhanced Features (vs Ownfoil)

 - **🔄 Multiple TitleDB Sources**: Support for blawar/titledb, tinfoil.media, and custom sources
 - **⚡ Faster Updates**: Direct JSON downloads instead of ZIP extraction
 - **🎯 Smart Fallback**: Automatic failover between multiple sources
 - **⚙️ Configurable Sources**: Manage TitleDB sources via web interface
 - **📊 Better Caching**: Intelligent cache with configurable TTL

## 🎯 Core Features

 - Multi-user authentication
 - Web interface for configuration
 - Web interface for browsing the library
 - Content identification using decryption or filename
 - Tinfoil shop customization
 - Library watchdog for automatic updates

> **Note**: This project is a fork under active development. Based on Ownfoil by [a1ex4](https://github.com/a1ex4/ownfoil).

# Table of Contents
- [Installation](#installation)
- [Enhanced Features](#enhanced-features)
- [Usage](#usage)
- [TitleDB Sources](#titledb-sources)
- [Migration from Ownfoil](#migration-from-ownfoil)
- [Roadmap](#roadmap)

# Installation

## Using Python (Recommended for Development)

Clone the repository using `git`, install the dependencies and you're good to go:

```bash
git clone https://github.com/fernandodimas/MyFoil
cd MyFoil
pip install -r requirements.txt
python app/app.py
```

The shop will be accessible at `http://localhost:8465`

## Using Docker (Coming Soon)

Docker images will be available soon. For now, you can build your own:

```bash
git clone https://github.com/fernandodimas/MyFoil
cd MyFoil
docker build -t myfoil .
docker run -d -p 8465:8465 \
  -v /your/game/directory:/games \
  -v ./config:/app/config \
  --name myfoil myfoil
```

## 🔄 Automatic Updates

To keep **MyFoil** always up to date with the latest features from GitHub, we recommend using **Watchtower**. 

Add this to your `docker-compose.yml`:

```yaml
services:
  myfoil:
    image: ghcr.io/fernandodimas/myfoil:latest
    container_name: myfoil
    # ... your config ...

  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_POLL_INTERVAL=3600
```

## Migration from Ownfoil

MyFoil is 100% compatible with Ownfoil. Simply:

1. Stop your Ownfoil instance
2. Replace the code/image with MyFoil
3. Start MyFoil - it will use your existing config and database

All your settings, users, and library data will be preserved!

## Tinfoil setup
In Tinfoil, add a shop with the following settings:
 - Protocol: `http` (or `https` if using a SSL enabled reverse proxy)
 - Host: server/computer IP, i.e. `192.168.1.100`
 - Port: host port of the container, i.e. `8000`
 - Username: username as created in MyFoil settings (if the shop is set to Private)
 - Password: password as created in MyFoil settings (if the shop is set to Private)

# Usage
Once MyFoil is running you can access the Shop Web UI by navigating to the `http://<computer/server IP>:8465`.

## User administration
MyFoil requires an `admin` user to be created to enable Authentication for your Shop. Go to the `Settings` to create a first user that will have admin rights. Then you can add more users to your shop the same way.

## Library administration
In the `Settings` page under the `Library` section, you can add directories containing your content. You can then manually trigger the library scan: MyFoil will scan the content of the directories and try to identify every supported file (currently `nsp`, `nsz`, `xci`, `xcz`).
There is watchdog in place for all your added directories: files moved, renamed, added or removed will be reflected directly in your library.

## Titles configuration
In the `Settings` page under the `Titles` section is where you specify the language of your Shop (currently the same for all users).

This is where you can also upload your `console keys` file to enable content identification using decryption, instead of only using filenames. If you do not provide keys, MyFoil expects the files to be named `[APP_ID][vVERSION]`.

## Shop customization
In the `Settings` page under the `Shop` section is where you customize your Shop, like the message displayed when successfully accessing the shop from Tinfoil or if the shop is private or public.

# TitleDB Sources

## What are TitleDB Sources?

TitleDB sources provide the metadata about Switch games, updates, and DLCs. MyFoil uses this data to:
- Identify your game files
- Check if you have the latest updates
- Detect missing DLCs
- Display game names and artwork

## Default Sources

MyFoil comes with three pre-configured sources (in priority order):

1. **blawar/titledb (GitHub)** - Priority 1 (Enabled)
   - The original and most comprehensive source
   - Updated frequently by the community
   - Direct from GitHub's raw content

2. **tinfoil.media** - Priority 2 (Enabled)
   - Official Tinfoil API
   - Reliable and fast
   - Good fallback option

3. **ownfoil/workflow (Legacy)** - Priority 99 (Disabled)
   - Original MyFoil ZIP-based source (inherited from Ownfoil)
   - Kept for compatibility
   - Slower than direct sources

## How It Works

When MyFoil needs to update TitleDB:

1. It tries the **highest priority enabled source** first
2. If that fails (timeout, rate limit, etc.), it tries the **next source**
3. This continues until a source succeeds or all fail
4. Files are cached for 24 hours to reduce bandwidth

## Managing Sources via API

### Get All Sources
```bash
curl http://localhost:8465/api/settings/titledb/sources \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ="
```

### Add a Custom Source
```bash
curl -X POST http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "My Mirror",
    "base_url": "https://my-server.com/titledb",
    "priority": 5,
    "enabled": true
  }'
```

### Update a Source
```bash
curl -X PUT http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "blawar/titledb (GitHub)",
    "enabled": false
  }'
```

### Remove a Source
```bash
curl -X DELETE http://localhost:8465/api/settings/titledb/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ=" \
  -d '{
    "name": "My Mirror"
  }'
```

### Force Update
```bash
curl -X POST http://localhost:8465/api/settings/titledb/update \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ="
```

## Creating Your Own Source

To host your own TitleDB mirror:

1. Clone blawar/titledb: `git clone https://github.com/blawar/titledb`
2. Serve the files via HTTP/HTTPS
3. Add your source to MyFoil with the base URL
4. Required files:
   - `cnmts.json` - Content metadata
   - `versions.json` - Version information
   - `versions.txt` - Version list
   - `languages.json` - Language mappings
   - `titles.{REGION}.{LANG}.json` - Game titles (e.g., `titles.US.en.json`)

## Troubleshooting

**Updates failing?**
- Check source status in the API response
- Look at `last_error` field for each source
- Try forcing an update
- Verify your internet connection

**Want faster updates?**
- Disable slower sources
- Adjust priorities (lower number = higher priority)
- Host your own mirror closer to your server

# Roadmap
Planned feature, in no particular order.
 - Library browser:
    - [ ] Add "details" view for every content, to display versions etc
 - Library management:
    - [ ] Rename and organize library after content identification
    - [ ] Delete older updates
    - [ ] Automatic nsp/xci -> nsz conversion
 - Shop customization:
    - [ ] Encrypt shop
 - Support emulator Roms
    - [ ] Scrape box arts
    - [ ] Automatically create NSP forwarders
 - Saves manager:
    - [ ] Automatically discover Swicth device based on Tinfoil connection
    - [ ] Only backup and serve saves based on the user/Switch
 - External services:
    - [ ] Integrate torrent indexer Jackett to download updates automatically

# Similar Projects
If you want to create your personal NSP Shop then check out these other similar projects:
- [eXhumer/pyTinGen](https://github.com/eXhumer/pyTinGen)
- [JackInTheShop/FT-SCEP](https://github.com/JackInTheShop/FT-SCEP)
- [gianemi2/tinson-node](https://github.com/gianemi2/tinson-node)
- [BigBrainAFK/tinfoil_gdrive_generator](https://github.com/BigBrainAFK/tinfoil_gdrive_generator)
- [ibnux/php-tinfoil-server](https://github.com/ibnux/php-tinfoil-server)
- [ramdock/nut-server](https://github.com/ramdock/nut-server)
- [Myster-Tee/TinfoilWebServer](https://github.com/Myster-Tee/TinfoilWebServer)
- [DevYukine/rustfoil](https://github.com/DevYukine/rustfoil)
- [Orygin/gofoil](https://github.com/Orygin/gofoil)
