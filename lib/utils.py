import logging
import os
import json
import time
from rdkit import Chem

def create_logger(name: str, task_id: int) -> logging.Logger:
    """
    Creates a logger with a stream handler and two file handlers.

    The stream handler prints to the screen depending on the value of `quiet`.
    One file handler (verbose.log) saves all logs, the other (quiet.log) only saves important info.

    :param save_dir: The directory in which to save the logs.
    :return: The logger.
    """
    logging.basicConfig(
            filemode='w+',
            level=logging.INFO)
    logger = logging.getLogger(name)
    logger.propagate = False
    file_name = f'{name}_{task_id}.log'
    try:
        os.remove(file_name)
    except:
        pass
    fh = logging.FileHandler(filename=file_name)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    return logger

class DoneJobsRecord(object):
    """
    class to record completed jobs
    """
    def __init__(self, start_time, logger):
        self.start_time = start_time
        self.logger = logger
        self.all_spc_ids = []
        self.task_id = None
        self.num_tasks = None
        self.FF_conf = []
        self.semiempirical_opt = []
        self.DFT_opt_freq = []
        self.COSMO = {}
        self.WFT_sp = []
        self.QM_desp = []
        self.test_semiempirical_opt = {}
        self.test_DFT_sp = {}
    
    def save(self, project_dir, task_id):
        with open(os.path.join(project_dir, f"done_jobs_record_{task_id}.json"), "w+") as fh:
            json.dump(vars(self), fh)
        self.logger.info(f'Elasped time: {time.time()-self.start_time}')

    def load(self, project_dir, task_id):
        with open(os.path.join(project_dir,f"done_jobs_record_{task_id}.json"), "r") as fh:
            content = json.load(fh)
        for job, molids in content.items():
            setattr(self, job, molids)

    def initialize(self, all_spc_ids, task_id, num_tasks):
        self.all_spc_ids = all_spc_ids
        self.task_id = task_id
        self.num_tasks = num_tasks