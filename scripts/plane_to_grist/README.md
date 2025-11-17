# Copy a Plane project to a Grist document

If run multiple times, the tool will clear the document and recreate it entirely.

## Dependencies

The dependencies are managed with [uv](https://github.com/astral-sh/uv).

## Running

The plane project's URL and the Grist document URL are currently hardcoded.

```sh
uv run ./plane_to_grist.py --plane-token <plane token> --grist-token <grist token>
```

The dependencies are automatically installed by uv.

# TODO

* Don't convert the date, so we can actually compare the plane and grist content, and avoid erasing everything
* Add an option for the plane project URL
* Add an option for the grist document URL
