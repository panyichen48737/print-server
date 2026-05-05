"""测试 PrinterBackend 抽象基类"""

import pytest

from app.printing.backends.base import PrinterBackend


class TestPrinterBackend:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            PrinterBackend()  # 应抛出 TypeError

    def test_concrete_subclass_works(self):
        class ConcreteBackend(PrinterBackend):
            def print_file(self, filepath, job_id, print_params, lock=None):
                return True

            def cancel(self, job_id, info):
                return True

        backend = ConcreteBackend()
        assert backend.print_file('/p.pdf', '1', {}) is True
        assert backend.cancel('1', {}) is True
