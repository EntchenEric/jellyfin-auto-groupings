# jellyfin-groupings

> **Note:** This project was largely AI-generated. I'm a CS student who could have written this myself — I just didn't want to. I reviewed the code, understand how it works, and actively maintain it. The AI was basically just a faster keyboard.

A small Flask web app that lets you create **virtual libraries** in [Jellyfin](https://jellyfin.org/) by grouping media into symlinked directories on disk. Instead of duplicating files or messing with Jellyfin's built-in collections, it creates folders of symlinks (e.g. `~/jellyfin-groupings-virtual/action/`) that Jellyfin can scan as independent libraries.

> [!IMPORTANT]
> **Jellyfin libraries are NOT created automatically.** After syncing, you must add each group as a library in Jellyfin manually:
> **Dashboard → Libraries → Add Media Library → Content Type: Mixed Movies and Shows**
> Automatic library creation is a planned future feature.

---

## Features

- **Metadata-based groups** — filter by genre, actor, studio, or tag directly from your Jellyfin library
- **IMDb list support** — paste an IMDb list URL and the app resolves matching items in your library
- **Docker path mapping** — translate Jellyfin container paths to host paths via `jellyfin_root` / `host_root` config
- **Sorting** — optionally prefix filenames with a numeric index based on community rating, year, name, date added, random, or IMDb list order
- **Auto-detect paths** — the app can scan your filesystem to suggest the correct `jellyfin_root` and `host_root` values
- **One-click sync** — rebuilds all symlink directories on demand via the web UI

---

## Stack

- **Backend:** Python 3, Flask, Requests
- **Frontend:** Single-file vanilla HTML/CSS/JS (`index.html`)
- **Config:** `config.json` (created automatically on first run)

---

## Setup

### 1. Install dependencies

```bash
pip install flask requests
```

### 2. Run the app

```bash
python app.py
```

The web UI is available at [http://localhost:5000](http://localhost:5000).

### 3. Configure

Open the UI and fill in:

| Field | Description |
|---|---|
| Jellyfin URL | e.g. `http://localhost:8096` |
| API Key | Generate one in Jellyfin → Dashboard → API Keys |
| Target Path | Where symlink folders will be created on the **host** (e.g. `~/jellyfin-groupings-virtual`) |
| Jellyfin Root | The media root path **as seen by Jellyfin** (only needed if running in Docker) |
| Host Root | The same path **as seen by the host** (only needed if running in Docker) |
| Jellyfin Virtual Root | The target path **as seen by Jellyfin** (so it can find the symlinks) |

Use the **Auto-Detect** button to have the app guess the path mapping for you.

### 4. Add groups and sync

Create groupings in the UI (by genre, actor, studio, tag, or IMDb list), then hit **Sync All Groupings**. The app will create/recreate the symlink directories and print a per-group summary.

### 5. Add the libraries to Jellyfin manually

> [!IMPORTANT]
> **Automatic library creation is not implemented yet** — this is a planned future feature. You have to add each library by hand.

For each group you created, add a new library in Jellyfin:

1. Go to **Dashboard → Libraries → Add Media Library**
2. Set **Content Type** to **`Mixed Movies and Shows`**
3. Set the folder to the matching subdirectory inside your target path
   - e.g. if your target path is `~/jellyfin-groupings-virtual` and your group is `action`, add `~/jellyfin-groupings-virtual/action`
4. Save and let Jellyfin scan

---

## Configuration reference (`config.json`)

```json
{
    "jellyfin_url": "http://localhost:8096",
    "api_key": "your_api_key_here",
    "target_path": "/home/user/jellyfin-groupings-virtual",
    "jellyfin_root": "/media",
    "host_root": "/mnt/media",
    "jellyfin_target_root": "/virtual",
    "groups": [
        {
            "name": "action",
            "source_category": "jellyfin",
            "source_type": "genre",
            "source_value": "Action"
        },
        {
            "name": "mcu",
            "source_category": "external",
            "source_type": "imdb_list",
            "source_value": "https://www.imdb.com/list/ls029032797/",
            "sort_order": "imdb_list_order"
        }
    ]
}
```

**`source_type` values:**

| Value | Description |
|---|---|
| `genre` | Match by Jellyfin genre tag |
| `actor` | Match by actor name |
| `studio` | Match by studio name |
| `tag` | Match by Jellyfin tag |
| `imdb_list` | Pull from a public IMDb list URL |

**`sort_order` values:** `CommunityRating`, `ProductionYear`, `SortName`, `DateCreated`, `Random`, `imdb_list_order` (or leave empty for no sorting/prefix)

---

## Project structure

```
jellyfin-groupings/
├── app.py          # Flask backend + sync logic
├── index.html      # Frontend (single-file, no build step)
├── config.json     # Auto-created on first run
└── tests/          # Test suite
```

---

## Running tests

```bash
python -m pytest tests/
```

---

## License

Do whatever you want with it.
