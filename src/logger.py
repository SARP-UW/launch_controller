from datetime import datetime

class Logger:
    """
    Class for logging data to a file with timestamps.
    """
    
    def __init__(self, path: str) -> None:
        """
        Initializes a Logger object with the given parameters.
        
        Args:
            path: The path of the file where data will be logged.
        """
        self._path = path
        self._file = open(path, 'a')
       
    def __del__(self) -> None:
        self._file.close()
        
    @property
    def path(self) -> str:
        """
        Path of file where data is logged.
        """
        return self._path
        
    def log_data(self, data: str) -> None:
        """
        Logs the provided data to the Logger's file with an added timestamp using 
        the format: "YYYY-MM-DDTHH:MM:SS.ssssss, data".
        
        Args:
            data: The data to be logged.
        """
        timestamp = datetime.now().isoformat()
        self._file.write(f"{timestamp}, {data}\n")
        self._file.flush()