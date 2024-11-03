#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os
from pathlib import Path

# QR code generator for public users
import qrcode

from PIL import Image, ImageFont, ImageDraw

from flask_login import current_user
from flask import url_for, request

from elections import app

def clear_all_qr_codes(clubid, eventid):
    current_user.logger.warning("Clearing all QR codes...")

    basepath = os.path.join(os.getcwd(), app.config.get('IMAGES_UPLOAD_FOLDER'), str(clubid), str(eventid), 'entries')

    # Store the QR code in the club's images folder.
    qrfile = '%d_*_qrcode.png' % (eventid)

    if os.path.exists(basepath):
        for p in Path(basepath).glob(qrfile):
            try:
                p.unlink()
            except:
                pass

    current_user.logger.info("Cleared all QR codes.")

# Generate a QR code for the given public key, saving as the given filename.
def generate_public_qr_code(publickey, basepath, qrfile, save=True):
    # Path to store on server.
    qrimgpath = os.path.join(basepath, qrfile)

    if not os.path.exists(basepath):
        current_user.logger.debug("Creating images directory '%s'" % basepath, indent=1)
        os.makedirs(basepath)

    # If the QR image doesn't exist, create it.
    if not os.path.exists(qrimgpath):
        # Path to encode into the QR code.  This should be set by the system config.
        url_root = app.config.get('PUBLIC_ACCESS_QR_CODE_ROOT', None)
        if url_root is None:
            url_root = request.url_root.strip('/')

        url = '%s%s?publickey=%s' % (url_root, url_for('main_bp.publiclogin'), publickey)

        current_user.logger.debug("Generating QR code '%s'" % url, indent=1)
        qrdata = qrcode.make(url)

        current_user.logger.debug("Storing QR code image file '%s'" % qrfile, indent=1)
        qrdata.save(qrimgpath)

    else:
        current_user.logger.debug("QR code image file '%s' exists" % qrfile, indent=1)
