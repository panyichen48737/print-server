"""测试 PrinterBackend 抽象基类"""

from app.printing.backends.base import PrinterBackend


class TestPrinterBackend:
    def test_cannot_instantiate_abstract(self):

        try:
            PrinterBackend()  # 应抛出 TypeError
            assert False, '应禁止直接实例化抽象类'
        except TypeError:
            pass

    def test_concrete_subclass_works(self):
        class ConcreteBackend(PrinterBackend):
            def print_file(self, filepath, job_id, print_params, lock=None):
                return True

            def cancel(self, job_id, info):
                return True

        backend = ConcreteBackend()
        assert backend.print_file('/p.pdf', '1', {}) is True
        assert backend.cancel('1', {}) is True
