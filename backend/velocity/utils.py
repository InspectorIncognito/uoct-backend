from velocity.grid import GridManager


def generate_grid():
    grid_manager = GridManager()
    grid_manager.process()
    return grid_manager
