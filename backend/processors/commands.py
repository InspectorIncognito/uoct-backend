import logging
import os
import typer
import datetime
from pathlib import Path
from config.paths import LOGS_PATH
from processors.grid import generate_grid

app = typer.Typer()
logger = logging.getLogger(__name__)


@app.command()
def calculate_speed(
        start_date: str = typer.Option(
            (datetime.datetime.now() - datetime.timedelta(minutes=60)).strftime('%Y-%m-%d %H:%M'),
            help='Lower time bound to analyze (in UTC format). For example: 2020-01-01 04:00".'
                 'If it\'s not provided, one hour to past will be used.'),
        end_date: str = typer.Option(
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            help='Lower time bound to analyze (in UTC format). For example: 2020-01-01 04:00".'
                 'If it\'s not provided, one hour to past will be used.'),
):
    print(start_date)
    print(end_date)
    grid_obj = generate_grid()



    vm = VehicleManager(grid_obj)


if __name__ == '__main__':
    log_file_path = Path(
        os.path.join(LOGS_PATH, 'output.log.{}'.format(datetime.datetime.now().strftime('%y_%m_%d_%H_%M_%S'))))
    if log_file_path.exists():
        os.remove(log_file_path)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler()
        ]
    )
    app()
