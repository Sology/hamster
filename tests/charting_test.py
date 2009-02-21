import sys, os.path
# a convoluted line to add hamster module to absolute path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from hamster import charting

class TestIteratorFunctions(unittest.TestCase):
    def testOneStep(self):
        integrator = charting.Integrator(0)
        integrator.target(10)
        
        integrator.update()
        assert integrator.value == 9

if __name__ == '__main__':
    unittest.main()
