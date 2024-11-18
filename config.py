#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

"""Flask app configuration."""
from os import environ, path
from dotenv import load_dotenv

basedir = path.abspath(path.dirname(__file__))
load_dotenv(path.join(basedir, '.env'))

class Config:

    ######################################################
    # These are things you do not touch.
    ######################################################

    # Package
    PACKAGE = 'elections'

    # Version
    VERSION = '1.0.1'

    # Multi-tenancy.
    MULTI_TENANCY = True

    # Default event title.
    DEFAULT_EVENT_TITLE = 'The Elect-O-Matic!'
    DEFAULT_APPICON = 'defaulticon.ico'
    DEFAULT_HOMEIMAGE = 'appdefault.png'
    MISSING_IMAGE = 'x-icon.png'

    # Default club and election IDs.
    DEFAULT_CLUBID = 1
    DEFAULT_ELECTID = 1

     # Flask settings
    FLASK_APP = 'wsgi.py'
    SECRET_KEY = 'Shut Up, Beavis'

    # Static Assets
    STATIC_FOLDER = 'static'
    STATIC_UPLOAD_FOLDER = path.join(PACKAGE, STATIC_FOLDER)

    TEMPLATES_FOLDER = 'templates'
    COMPRESSOR_DEBUG = environ.get('COMPRESSOR_DEBUG')

    # Images folder (icon, homeimage, photos, QR codes, others)
    IMAGES_FOLDER = 'images'
    IMAGES_UPLOAD_FOLDER =  path.join(PACKAGE, IMAGES_FOLDER)
    MAX_CONTENT_LENGTH = (16 * 1024 * 1024)

        # Docs folder
    DOCS_FOLDER = 'docs'

    # Export data
    EXPORT_FOLDER = 'exports'
    EXPORT_DOWNLOAD_FOLDER = path.join(PACKAGE, EXPORT_FOLDER)

    # Import data
    IMPORT_FOLDER = 'imports'
    IMPORT_UPLOAD_FOLDER = path.join(PACKAGE, IMPORT_FOLDER)
    IMPORT_SUPPORTED_VERSIONS = [1]

    # Log data
    LOG_FOLDER = 'log'
    LOG_DOWNLOAD_FOLDER = path.join(PACKAGE, LOG_FOLDER)
    LOG_BASENAME = PACKAGE

    # Number of lines of a logfile to process when building the log-offsets file.
    # This must be a power of 2.
    LOGFILE_OFFSETS_CHUNKSIZE = 131072

    # Complexity checker can be disbled for testing by setting as False.
    PASSWORD_COMPLEXITY_CHECK = True

    ######################################################
    # These are things that can be modified to suit the installation.
    ######################################################

    # Password minimal length (chars).
    PASSWORD_MIN_LENGTH = 8

    # Logging
    # Maximum number of backup files and file size at which to backup.
    LOG_BACKUP_FILE_COUNT = 10
    LOG_BACKUP_FILE_SIZE = 5000000 # 5M bytes

    # Login
    # Number of seconds a session can be idle before expiring.
    SESSION_IDLE_TIME = 1800

    # Debug
    DB_DEBUG = False
    DB_DEBUG_OUTPUT = False
    CONSOLE_ECHO = False

    # Logging
    SAVE_LOGS = False
    LOGPAGE_SIZE = 50

    # Database Control
    READ_ONLY = False