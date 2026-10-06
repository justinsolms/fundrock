import unittest

import fundrock


class PackageImportTest(unittest.TestCase):
    def test_package_imports(self):
        self.assertIsNotNone(fundrock)


if __name__ == "__main__":
    unittest.main()
