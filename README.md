# one-line

Finds the longest route you can run through a neighborhood without ever retracing your steps — no street segment or intersection used more than once (a longest-simple-path search on the street graph).

Live route: https://ulyssegagne.github.io/one-line/

## Running it

    pip install -r requirements.txt

1. Set the neighborhood in `config.py`.
2. `python prepare.py` — pulls the streets from OpenStreetMap and opens an editing map in the browser. Connect or cut streets, mark start/end, then Export.
3. `python solve.py` — searches for the longest path and saves routes as GPX under `output/<name>_routes/`. Runs until Ctrl+C, keeping a few good, distinct ones.

Past runs are in `past-runs/`.
