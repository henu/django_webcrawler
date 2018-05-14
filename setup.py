#!/usr/bin/env python
from setuptools import setup

setup(
    name='django_webcrawler',
    version='0.1',
    packages=['django_webcrawler'],
    license='MIT License',
    description='Django app for crawling web.',
    author='Henrik Heino',
    author_email='henrik.heino@gmail.com',
    url='https://github.com/henu/django_webcrawler',
    install_requires=[
        'requests',
        'beautifulsoup4',
    ],
)
