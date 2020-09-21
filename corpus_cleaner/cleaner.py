from corpus_cleaner.components.a_data_parser.data_parser import DataParser
from corpus_cleaner.components.a_data_parser.data_parser_factory import DataParserFactory
from corpus_cleaner.components.b_encoding_fixer.encoding_fixer import EncodingFixer
from corpus_cleaner.components.c_pre_filterer.pre_filterer import PreFilterer
from corpus_cleaner.components.d_sentence_splitter_component.sentence_splitter_component import \
    SentenceSplitterComponent
from corpus_cleaner.components.e_sentence_filter.sentence_filter import SentenceFilter
from corpus_cleaner.components.f_normalizer.normalizer import Normalizer
from corpus_cleaner.components.g_document_filter.document_filter import DocumentFilter
from corpus_cleaner.components.h_document_organizer.document_organizer import DocumentOrganizer
from corpus_cleaner.components.i_output_formatter.output_formatter import OutputFormatter
from corpus_cleaner.components.i_output_formatter.output_formatter_factory import OutputFormatterFactory
from typing import Iterable, List, Tuple
from corpus_cleaner.components.cleaner_component import CleanerComponent
from corpus_cleaner.document import Document
from collections import OrderedDict
from corpus_cleaner.par_utils import MappingPipeline, PipelineLogger
from corpus_cleaner.components.cleaner_component_reducer import DummyReducer
import argparse
import logging
import os
from . import __version__
from typing import Optional
from corpus_cleaner.components.cleaner_component_mapper import CleanerComponentMapper

MAPPERS = [
    EncodingFixer, PreFilterer,
    SentenceSplitterComponent, SentenceFilter, Normalizer
]
REDUCER = DocumentFilter

POSTMAPPERS = [DocumentOrganizer]


class Cleaner:

    @staticmethod
    def get_components_classes() -> List:
        return [DataParser, EncodingFixer, PreFilterer, SentenceSplitterComponent, SentenceFilter, Normalizer,
                DocumentFilter, DocumentOrganizer, OutputFormatter]

    @staticmethod
    def get_valid_input_output_formats() -> Tuple:
        return DataParserFactory.VALID_INPUT_FORMATS, OutputFormatterFactory.VALID_OUTPUT_FORMATS

    def __init__(self, args: argparse.Namespace, logger: logging):
        self.args = args
        self.args.cleaner_version = __version__
        self.logger = PipelineLogger(logger)
        self.args.logger = self.logger
        self.mappers = MAPPERS
        self.tmp_dir = os.path.join(args.output_path, 'tmp')
        os.makedirs(self.tmp_dir)
        if args.components is not None:
            self.mappers = []
            for comp in MAPPERS:
                if comp.__name__ in args.components:
                    self.mappers.append(comp)
        if not self.args.only_reduce:
            self.mappers = [lambda x: DataParserFactory.get_parser_mapper(x)] + self.mappers +\
                           [lambda x: OutputFormatterFactory.get_output_formatter_mapper(
                            args=None, output_format='onion',
                            output_path=os.path.join(self.tmp_dir, os.uname()[1] + '-' + str(os.getpid()) + '.onion'))]
        else:
            class SentencePacker(CleanerComponentMapper):

                def apply(self, document: Optional[Document]) -> Optional[Document]:
                    document.sentences = [sen for sen in document.content.splitlines() if len(sen.split()) > 0]
                    return document

            self.mappers = [lambda x: DataParserFactory.get_parser_mapper(x)] + [SentencePacker] + \
                           [lambda x: OutputFormatterFactory.get_output_formatter_mapper(
                            args=None, output_format='onion',
                            output_path=os.path.join(self.tmp_dir,  os.uname()[1] + '-' + str(os.getpid()) + '.onion'))]
        self.reducer = REDUCER if not args.debug_errors_mode else DummyReducer
        if args.components is not None:
            self.reducer = None
            for comp in args.components:
                if comp == REDUCER.__name__:
                    self.reducer = REDUCER
                    break
        self.postmappers = POSTMAPPERS
        if args.components is not None:
            self.postmappers = []
            for comp in POSTMAPPERS:
                if comp.__name__ in args.components:
                    self.postmappers.append(comp)
        self.documents = None
        self.stats = OrderedDict()

    @staticmethod
    def add_args(parser: argparse.ArgumentParser):
        parser.add_argument('--components', type=str, help='Elements of the pipeline', nargs='+',
                            default=list(map(lambda x: x.__name__, MAPPERS + [REDUCER] + POSTMAPPERS)))
        parser.add_argument('--parallel', action='store_true', help='Run the cleaner in parallel')
        parser.add_argument('--log-every-iter', type=int, default=-1, help='Log the pipeline every N iterations'
                                                                           '(-1, silent)')
        parser.add_argument('--backend', type=str, default='mp', help='Parallel backend (mp or ray)')
        parser.add_argument('--only-reduce', action='store_true', help='Only document filter')
        parser.add_argument('--only-reduce-output', action='store_true', help='Only document filter for output files')
        parser.add_argument('--debug-errors-mode', action='store_true',
                            help='Activate the debug error mode to compare the original and cleaned sentences')

    @staticmethod
    def check_args(args: argparse.Namespace):
        for comp in args.components:
            if comp not in list(map(lambda x: x.__name__, MAPPERS + [REDUCER] + POSTMAPPERS)):
                raise Exception('Unknown component', comp)
        assert args.log_every_iter == -1 or args.log_every_iter >= 1
        # TODO: add more checks (eg. sentence splitting requirement for other components

    def _get_documents(self) -> List[Iterable[Document]]:
        # self.logger.info('Parsing...')
        parser = DataParserFactory.get_parser(self.args)
        return parser.parse()

    def _get_paths(self) -> List[Tuple[int, str]]:
        # self.logger.info('Parsing...')
        parser = DataParserFactory.get_parser(self.args)
        return parser.get_idx_relative_filepaths()

    def _create_pipeline_mappers(self) -> List[CleanerComponent]:
        return [component(self.args) for component in self.mappers]

    def _create_pipeline_postmappers(self) -> List[CleanerComponent]:
        return [component(self.args) for component in self.postmappers]

    def _output(self, documents: Iterable[Document]):
        # self.logger.info('Outputting...')
        output_formatter = OutputFormatterFactory.get_output_formatter(self.args)
        output_formatter.apply(documents)

    def clean(self):
        if self.reducer is None:
            raise NotImplementedError()
        else:
            if not self.args.only_reduce_output:
                self.reducer = self.reducer(self.args)
                pipeline = MappingPipeline(streams=self._get_paths(),
                                           mappers_factory=self._create_pipeline_mappers,
                                           parallel=self.args.parallel,
                                           logger=self.logger if self.args.log_every_iter != -1 else None,
                                           log_every_iter=self.args.log_every_iter,
                                           backend=self.args.backend)
                pipeline.run()

            else:
                self.reducer = self.reducer(self.args, output_path=os.path.join(self.args.input_path))

            self.reducer.reduce()

            self._output(self.reducer.get_documents()[0])

