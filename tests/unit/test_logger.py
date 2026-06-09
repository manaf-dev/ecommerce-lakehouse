"""Unit tests for src/utils/logger.py."""

import logging

from utils.logger import DatasetAdapter, get_logger


class TestGetLogger:
    def test_returns_dataset_adapter(self):
        result = get_logger("test_module")
        assert isinstance(result, DatasetAdapter)

    def test_dataset_and_run_id_stored(self):
        logger = get_logger("test_module", dataset="orders", run_id="exec-123")
        assert logger.extra["dataset"] == "orders"
        assert logger.extra["run_id"] == "exec-123"

    def test_empty_extras_are_defaults(self):
        logger = get_logger("test_module")
        assert logger.extra["dataset"] == ""
        assert logger.extra["run_id"] == ""

    def test_underlying_logger_name(self):
        logger = get_logger("my_logger")
        assert logger.logger.name == "my_logger"

    def test_basicconfig_called_when_no_handlers(self):
        logging.root.handlers.clear()
        get_logger("test_no_handlers")
        assert len(logging.root.handlers) > 0


class TestDatasetAdapterProcess:
    def test_prefix_with_both_extras(self):
        base = logging.getLogger("test_process")
        adapter = DatasetAdapter(base, {"dataset": "products", "run_id": "run-99"})
        msg, _ = adapter.process("hello", {})
        assert msg == "[products][run-99] hello"

    def test_prefix_with_dataset_only(self):
        base = logging.getLogger("test_dataset_only")
        adapter = DatasetAdapter(base, {"dataset": "orders", "run_id": ""})
        msg, _ = adapter.process("world", {})
        assert msg == "[orders] world"

    def test_prefix_with_run_id_only(self):
        base = logging.getLogger("test_run_only")
        adapter = DatasetAdapter(base, {"dataset": "", "run_id": "exec-7"})
        msg, _ = adapter.process("msg", {})
        assert msg == "[exec-7] msg"

    def test_no_prefix_when_both_empty(self):
        base = logging.getLogger("test_no_prefix")
        adapter = DatasetAdapter(base, {"dataset": "", "run_id": ""})
        msg, _ = adapter.process("bare", {})
        assert msg == "bare"

    def test_kwargs_passed_through_unchanged(self):
        base = logging.getLogger("test_kwargs")
        adapter = DatasetAdapter(base, {"dataset": "x", "run_id": "y"})
        original_kwargs = {"extra": {"foo": "bar"}}
        _, returned_kwargs = adapter.process("msg", original_kwargs)
        assert returned_kwargs is original_kwargs
