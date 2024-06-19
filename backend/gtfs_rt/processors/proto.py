from gtfs_rt.processors.manager import GTFSRTManager


def download_proto_data():
    gtfs_rt_manager = GTFSRTManager()
    gtfs_rt_manager.run_process_cron()
