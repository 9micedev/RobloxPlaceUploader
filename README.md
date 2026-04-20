# RobloxPlaceUploader

Python utility for uploading Roblox place files (`.rbxl` / `.rbxlx`) with a cookie-based authentication flow.

> Note: this repository uses the legacy Roblox upload endpoint as a best-effort workflow. Roblox has deprecated `data.roblox.com/Data/Upload.ashx` for place publishing traffic, so Open Cloud Place Publishing API is the recommended long-term path.

## Quick Start

Set your `.ROBLOSECURITY` cookie through an environment variable:

```bash
export ROBLOSECURITY="YOUR_COOKIE_VALUE"
python 11/main.py --file Place.rbxl
```

On Windows PowerShell:

```powershell
$env:ROBLOSECURITY = "YOUR_COOKIE_VALUE"
python 11/main.py --file Place.rbxl
```

## What The Script Does

1. Requests an `X-CSRF-TOKEN`.
2. Reads the authenticated Roblox user.
3. Finds the user's games and selects the latest root place unless `--place-id` is provided.
4. Uploads the selected `.rbxl` or `.rbxlx` file.
5. Attempts to make the universe public.
6. Prints and optionally opens the Roblox game URL.

## Options

- `--cookie` - `.ROBLOSECURITY` value. If omitted, the script reads `ROBLOSECURITY`.
- `--file` - path to a `.rbxl` or `.rbxlx` file. Defaults to `Place.rbxl`.
- `--place-id` - optional explicit place ID. If omitted, the script selects a place automatically.
- `--no-open` - do not open the result URL in a browser.
- `--timeout` - HTTP timeout in seconds. Defaults to `90`.
- `--retries` - retry count for temporary HTTP failures. Defaults to `2`.

## Security

- Never commit `.ROBLOSECURITY` cookies.
- Prefer environment variables over command-line arguments so secrets are less likely to appear in shell history.
- Rotate your Roblox cookie immediately if it was pasted into logs, screenshots, commits, or chat.
- Use Open Cloud API keys for production workflows when possible.

## Repository Contents

- `11/main.py` - upload script.
- `Place.rbxl` - sample place file.
- `11/` - media/assets used by the sample project.
