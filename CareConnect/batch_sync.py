from apscheduler.schedulers.background import BackgroundScheduler

class BatchSyncManager:
    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def sync_patients(self):
        # Logic to sync patients data
        print("Syncing patients data...")

    def sync_appointments(self):
        # Logic to sync appointments data
        print("Syncing appointments data...")

    def sync_prescriptions(self):
        # Logic to sync prescriptions data
        print("Syncing prescriptions data...")

    def sync_lab_orders(self):
        # Logic to sync lab orders data
        print("Syncing lab orders data...")

    def complete_sync(self):
        self.sync_patients()
        self.sync_appointments()
        self.sync_prescriptions()
        self.sync_lab_orders()

    def start_scheduler(self):
        # Schedule the complete sync every hour
        self.scheduler.add_job(self.complete_sync, 'interval', hours=1)
        self.scheduler.start()

# Example usage:
if __name__ == '__main__':
    manager = BatchSyncManager()
    manager.start_scheduler()  # Start the scheduler to auto sync every hour