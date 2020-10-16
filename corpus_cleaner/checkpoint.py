import os
import json
import argparse
import logging
import sys
from typing import Optional
import shelve


class Checkpoint:
    def __init__(self, output_path: str, args: Optional[argparse.Namespace] = None):
        self.output_path = output_path
        self.checkpoint_path = os.path.join(output_path, 'checkpoint')
        if os.path.exists(self.checkpoint_path + '.db'):
            assert args is None
            with open(os.path.join(output_path, 'args.json'), 'r') as f:
                self.args = argparse.Namespace(**json.loads(f.read()))
            self.resume = True
            if not self.args.only_reduce:
                self.logger = self.init_logger(os.path.join(self.output_path, 'clean.log'))
            else:
                raise RuntimeError("Can't resume with --only-reduce")
                # self.logger = self.init_logger(os.path.join(self.output_path, 'clean_reduce.log'))
                # with open(os.path.join(self.output_path, 'args_reduce.json'), 'w') as f:
                #    json.dump(self.args.__dict__, f, indent=2)
            if self.args.done:
                self.logger.info('Already cleaned!')
        else:
            assert args is not None
            with shelve.open(self.checkpoint_path) as c:
                c['done_paths'] = []
            self.args = args
            self.resume = False
            self.args.done = False
            if not self.args.only_reduce:
                self.logger = self.init_logger(os.path.join(self.output_path, 'clean.log'))
                with open(os.path.join(self.output_path, 'args.json'), 'w') as f:
                    json.dump(self.args.__dict__, f, indent=2)
            else:
                self.logger = self.init_logger(os.path.join(self.output_path, 'clean_reduce.log'))
                with open(os.path.join(self.output_path, 'args_reduce.json'), 'w') as f:
                    json.dump(self.args.__dict__, f, indent=2)

    @staticmethod
    def init_logger(filename_path: str) -> logging.Logger:
        logging.basicConfig(filename=filename_path, level=logging.INFO)
        logger = logging.getLogger(__name__)
        h = logging.StreamHandler(sys.stderr)
        h.flush = sys.stderr.flush
        logger.addHandler(h)
        return logger

    def declare_as_cleaned(self):
        self.args.done = True
        self.args.logger = None
        if not self.args.only_reduce:
            with open(os.path.join(self.output_path, 'args.json'), 'w') as f:
                json.dump(self.args.__dict__, f, indent=2)
        else:
            with open(os.path.join(self.output_path, 'args_reduce.json'), 'w') as f:
                json.dump(self.args.__dict__, f, indent=2)

    def get_done_paths(self):
        with shelve.open(self.checkpoint_path) as c:
            done_paths = c['done_paths']
        return done_paths
