import os
from pathlib import Path

ROOT_PATH = Path(__file__).parent.parent
LOGS_PATH = Path(os.path.join(ROOT_PATH, "logs"))
FIXTURE_PATH = Path(os.path.join(ROOT_PATH, 'fixtures', 'shapes_fixture.geojson'))
