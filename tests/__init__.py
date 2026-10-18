# -*- coding: utf-8 -*-
"""Make ``tests`` a regular package and expose the coach package.

The coach package lives under ``<skill root>/scripts`` since v1.9. Importing
``tests`` from anywhere (``python -m unittest discover -s tests -t .``) puts
that directory on ``sys.path`` so ``from coach import ...`` keeps working
without per-file boilerplate.
"""
import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
