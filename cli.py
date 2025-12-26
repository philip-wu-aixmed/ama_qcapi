""" Docstring for CCHQC.v1.qcapi.cli
  command-line interface
"""
from cchqc.api_main import start_qcapi

def main():
    """ command-line launch QCAPI service """
    #initLogger()
    start_qcapi()

if __name__  == '__main__':
    main()
