#!/usr/bin/env python
"""Run brevo_analytics tests standalone."""
import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2)
    # Run specific tests if provided as args, otherwise run all
    test_labels = sys.argv[1:] if len(sys.argv) > 1 else ['brevo_analytics']
    failures = test_runner.run_tests(test_labels)
    sys.exit(bool(failures))
