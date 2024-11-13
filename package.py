#!/bin/python3

# This script creates the installation file set for Ballot-O-Matic.

import os, sys, traceback
import pathlib
import zipfile
import config

try:
    # Get the config.
    configdata = config.Config()

    manifest = 'Manifest.in'
    filename = 'electomatic'

    # Read the version and package from the config.
    version = configdata.VERSION
    packagedir = configdata.PACKAGE

    # Manifest file must exist and be in the current directory.
    if not os.path.exists(manifest):
        print("Unable to locate manifest file (expected '%s')." % manifest)
        sys.exit(1)

    # Read the manifest file and build a list of files to include in the ZIP.
    files = []
    print("Building file list...")

    # Get the package files.
    print("Including python files in package '%s'..." % packagedir)
    limiter = '*.py'
    filelist = list(pathlib.Path(packagedir).rglob(limiter))
    if len(filelist) == 0:
        print("*** No files found for directory '%s', filter '%s'" % (packagedir, limiter))
    else:
        for f in filelist:
            print("  %s" % f)
            files.append(f)

    # Get files from the manifest.
    print("\nIncluding files in manifest...")
    with open(manifest, 'r') as m:
        for index, line in enumerate(m.readlines()):

            try:
                line = line.strip()
                if len(line) > 0 and not line.startswith("#"):
                    elems = line.split(' ')
                    cmd = elems[0]
                    item = elems[1]

                    limiter = None
                    if len(elems) > 2:
                        limiter = elems[2]

                    # Include the file.
                    if cmd == 'include':
                        print("  %s" % item)
                        files.append(item)

                    # Include the directory or subset thereof.
                    elif cmd == 'recursive-include':
                        if limiter is None:
                            print("\n*** Badly formatted manifest at line %s: '%s'" % (index, line))
                            sys.exit(1)

                        filelist = list(pathlib.Path(item).rglob(limiter))
                        if len(filelist) == 0:
                            print("*** No files found for directory '%s', filter '%s'" % (item, limiter))
                        else:
                            for f in filelist:
                                print("  %s" % f)
                                files.append(f)

            except:
                print("Error searching for file:")
                print(traceback.format_exc())
                sys.exit(1)

        # Build the ZIP file, using the version we read from the config.
        # The content will be in the 'electomatic' directory.
        distdir = 'dist'

        outdir = filename
        outfile = '%s-%s.zip' % (filename, version)
        outpath = os.path.join(distdir, outfile)

        if not os.path.exists(distdir):
            print("\nCreating output directory '%s'" % distdir)
            os.makedirs(distdir)

        if os.path.exists(outpath):
            print("\nRemoving previous output file '%s'..." % outfile)
            os.remove(outpath)

        print("\nBuilding ZIP file '%s'..." % outfile)
        with zipfile.ZipFile(outpath, 'w') as f_out:
            for f in files:
                f_out.write(os.path.join(os.getcwd(), f), os.path.join(outdir, f))

except:
    print(traceback.format_exc())
    sys.exit(1)

sys.exit(0)
