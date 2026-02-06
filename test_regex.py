import re

app_id_regex = r"\[([0-9A-Fa-f]{16})\]"
version_regex = r"\[v(\d+)\]"

filename = "The Elder Scrolls V Skyrim [01000A10041EA800][v393216].nsp"

app_id_match = re.search(app_id_regex, filename)
app_id = app_id_match[1] if app_id_match else None

version_match = re.search(version_regex, filename)
version = version_match[1] if version_match else None

print(f"Filename: {filename}")
print(f"App ID: {app_id}")
print(f"Version: {version}")
