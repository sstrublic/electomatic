#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os, shutil, re

from flask_login import current_user
from werkzeug.utils import secure_filename

from elections import app

# Save an image file.
def save_image_file(logprefix, file, default, clubid, eventid):
    try:
        # Build the destination path.
        if eventid != 0:
            basepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), str(clubid), str(eventid))
        else:
            basepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), str(clubid))

        if not os.path.exists(basepath):
            current_user.logger.debug("%s: Creating images directory '%s'" % (logprefix, basepath), indent=1)
            os.makedirs(basepath)

        # When no file specified, use the default and copy from static storage.
        if file is None:
            if default is None:
                current_user.logger.info("%s: Default image file was not specified" % logprefix, indent=1)
                return False

            static_folder = os.path.join(os.getcwd(), app.config.get('STATIC_UPLOAD_FOLDER'))

            current_user.logger.info("%s: Using default image file '%s'" % (logprefix, default), indent=1)
            srcfile = os.path.join(static_folder, default)
            dstfile = os.path.join(basepath, default)

            # If the file exists at the location, remove it before overwriting.
            if os.path.exists(dstfile):
                current_user.logger.warning("%s: Overwriting image '%s'" % (logprefix, dstfile), indent=1)
                os.remove(dstfile)

            shutil.copy2(srcfile, dstfile)

        else:
            # Build a file name that contains limited characters.
            filename = re.sub('[^0-9a-zA-Z-_.]+', '', secure_filename(file.filename))
            filepath = os.path.join(basepath, filename)

            # If the file exists at the location, remove it before overwriting.
            if os.path.exists(filepath):
                current_user.logger.warning("%s: Overwriting image '%s'" % (logprefix, filename))
                os.remove(filepath)

            current_user.logger.debug("%s: Saving file '%s'" % (logprefix, filename), indent=1)
            file.save(filepath)

        # Save completed.
        return True

    # A permissions error most likely means we're trying to overwrite the same file we're uploading from
    # (as in, someone went into the static directory and chose the file).  This isn't fatal; we just won't
    # save the file.
    except PermissionError:
        current_user.logger.debug("%s: Failed to save file (cannot overwrite the same file): this is not fatal" % logprefix)
        pass

    # Save was not completed.
    return False