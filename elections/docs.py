#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os, traceback
import zipfile, pathlib

from flask import redirect, render_template, url_for
from flask_login import current_user

from elections import app
from elections import ADMINS

# Retrieve system documentation.
def fetchDocs(user):
    try:
        event = current_user.event
        current_user.logger.info("Displaying: Fetch documents")

        filename = 'ballotomatic_docs_%s.zip' % app.config.get('VERSION')
        filepath = url_for('main_bp.exportfile', filename=filename)

        # Create the Zip file for documents.
        try:
            docs_folder = os.path.join(os.getcwd(), app.config.get('DOCS_FOLDER'))
            export_folder = os.path.join(os.getcwd(), app.config.get('EXPORT_DOWNLOAD_FOLDER'))
            localfile = os.path.join(export_folder, filename)

            if os.path.exists(localfile):
                current_user.logger.debug("Removing existing documentation bundle", indent=1)
                os.remove(localfile)

            # Add all PDFs in the docs directory.
            filelist = list(pathlib.Path(docs_folder).rglob("*.pdf"))

            with zipfile.ZipFile(os.path.join(export_folder, filename), 'w', zipfile.ZIP_DEFLATED) as zip:
                # Add files from the images folder..
                current_user.logger.debug("Fetching documents: Building documents file '%s'" % filename, indent=1)
                for f in filelist:
                    zip.write(f, os.path.basename(f))

        except Exception as ex:
            current_user.logger.error("Failed to remove existing documentation bundle", indent=1)
            current_user.logger.error(ex)

        current_user.logger.info("Fetching documents: Operation completed")

        return render_template('config/fetchdocs.html', user=user, admins=ADMINS[event.clubid],
                            filepath=filepath, filename=filename,
                            configdata=current_user.get_render_data())

    except Exception as e:
        current_user.logger.flashlog("Fetch Documents failure", "Exception: %s" % str(e))
        current_user.logger.error("Unexpected exception:")
        current_user.logger.error(traceback.format_exc())

        # Redirect to the main page to display the exception and prevent recursive loops.
        return redirect(url_for('main_bp.index'))
