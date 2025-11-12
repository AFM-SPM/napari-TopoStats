class Worker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(Exception)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.failed.emit(e)

def run_in_thread(func, loading_message, *args, **kwargs):
    spinner.start("Processing...")

    worker = Worker(func, *args, **kwargs)
    thread = QThread()

    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(lambda result: (spinner.stop(), thread.quit(), thread.wait()))
    worker.failed.connect(lambda e: (spinner.stop(), thread.quit(), thread.wait(), print("Error:", e)))

    thread.start()