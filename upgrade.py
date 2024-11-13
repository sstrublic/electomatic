#!/bin/python

# This script runs an upgrade.

import argparse, os, sys, traceback
import subprocess
import zipfile
import pathlib
import shutil, glob

# Execute a command.

def run_command(c):
    retcode = 0

    try:
        cmd = c.split(' ')
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

        output = proc.communicate()

        # Get the return code...
        retcode = proc.poll()

    except OSError:
        print('Command failed!')
        retcode = 1

    return retcode, output


def backup_database():
    # Perform a database backup.
    print("Backing up database... Prompting for user 'elections' password:")

    cmd = 'pg_dump -U elections -d elections -h localhost -W -f backup.sql'
    return run_command(cmd)


# Update the system configuration.
def update_config(installdir, oldconfig, forcelist):

    # Specific to the config, we need to add any new settings that might have
    # been created and remove those that are obsolete.

    # The goal is to transfer over any existing settings and highlight items
    # that have changed so they can be set by the admin.

    # We have read the current config, so we can read the new file and identify
    # anything that's obsolete (and anything that's new).

    # Convert the config to a dict.  The config is a class, so we need to make that
    # something parseable/iterable for use.
    def get_config_as_dict(config):
        configdata = {}
        members = [attr for attr in dir(config) if not callable(getattr(config, attr)) and not attr.startswith("__")]
        for m in members:
            configdata[m] = getattr(config, m)

        return configdata

    try:
        # Reload the module to be able to fetch the new config.
        import importlib
        import electomatic.config as config

        importlib.reload(config)
    except:
        # This is a fresh module load (for testing).
        import config

    # Get the configs as dicts, including converting the one passed in.
    newconfig = get_config_as_dict(config.Config())
    oldconfig = get_config_as_dict(oldconfig)

    # Find the differences between the old and new configs.
    newsettings = set(newconfig) - set(oldconfig)
    oldsettings = set(oldconfig) - set(newconfig)

    # For output to file.
    def get_configvalue_str(value):
        if type(value) is int:
            return "%d" % value
        elif type(value) is str:
            return "'%s'" % value
        else:
            return "%s" % value

    print("\nChecking for configuration changes...")

    if len(newsettings) > 0:
        print("New settings have been installed:")
        for n in newsettings:
            print("  %s: %s" % (n, get_configvalue_str(newconfig[n])))

    if len(oldsettings) > 0:
        print("\nOld settings have been removed:")
        for o in oldsettings:
            print("  %s: %s" % (o, get_configvalue_str(oldconfig[o])))


    # Config items to ignore, because we cannot interpret them properly (they are
    # either things we never would bring forward, or things that get interpreted
    # during config read and would cause problems if rewritten).
    CONFIG_ITEMS_TO_IGNORE = ['VERSION', 'STATIC_UPLOAD_FOLDER', 'COMPRESSOR_DEBUG', 'MAX_CONTENT_LENGTH',
                              'IMPORT_UPLOAD_FOLDER', 'IMAGES_UPLOAD_FOLDER', 'EXPORT_DOWNLOAD_FOLDER',
                              'LOG_DOWNLOAD_FOLDER', 'LOG_BASENAME'
                             ]

    print("\nChecking configuration values...")
    changed = {}

    # Verify the force-update list is valid.
    for f in forcelist:
        if f not in newconfig:
            print("  Force-update item '%s' is not found in the new configuration file." % f)
            return False

    for s in newconfig:
        # We skip the version as we always want to keep the new version.
        if s in CONFIG_ITEMS_TO_IGNORE:
            # print("  Skipping static item '%s'" % s)
            continue

        # If the value already exists and differs from the new configuration, see if it should be
        # restored or forcibly updated to the new value.
        if s in oldconfig and newconfig[s] != oldconfig[s]:
            if s in forcelist:
                print("  Configuration item '%s' will be force-updated as %s" % (s, get_configvalue_str(newconfig[s])))
            else:
                print("  Configuration item '%s' will be restored as %s" % (s, get_configvalue_str(oldconfig[s])))
                changed[s] = oldconfig[s]


    # Open and read the file as lines.
    configfile = 'config.py'
    retval = True

    # If there are changes, apply them to the new config.
    if len(list(changed)) > 0:
        print("\nUpdating configuration...")

        try:
            # Read the current file.
            configlines = []
            with open(os.path.join(os.getcwd(), installdir, configfile), 'r') as f:
                configlines = f.readlines()

            # Walk each line and find any changes abse don the change set we identified earlier.
            classdef = False
            for index, c in enumerate(configlines):
                # We have to find the start of the config class first to prevent false positives.
                if "class Config" in c:
                    classdef = True
                    continue

                if classdef is False:
                    continue

                # Find the item in the line.
                # Since we have to construct a new line, we need to split it into its key/value
                # and find the key in the changed dict, then write a new line with the old value.
                cs = c.strip()
                if len(cs) == 0 or cs.startswith('#'):
                    continue

                configitem = cs.split('=')
                if len(configitem) != 2:
                    print("  Line %d: Malformed line item '%s'" % (index + 1, cs))
                    return False

                # Get the key from the line.
                k, _ = (t.strip() for t in configitem)

                # If the value has changed for this item, write a new line with the old value and substitute
                # it into the config file's lines.
                if k in changed:
                    print("  Setting configuration item '%s' value as %s" % (k, get_configvalue_str(oldconfig[k])))
                    newline = "%s= %s\n" % (c.split('=')[0], get_configvalue_str(oldconfig[k]))
                    configlines[index] = newline

            # Rewrite the config file.
            print("\nWriting configuration file...")
            with open(os.path.join(os.getcwd(), installdir, configfile), 'w') as f:
                for c in configlines:
                    f.write(c)

            print("\nConfiguration file update completed.")

        except Exception:
            print("** Exception while parsing configuration file:")
            print(traceback.format_exc())
            retval = False

    else:
        print("\nConfiguration settings have not changed.")

    return retval


# PIP packages to install/verify.
PIP_PACKAGES = {'flask': None,
                'flask-login': None,
                'waitress': None,
                'psycopg2': None,
                'openpyxl': None,
                'python-dotenv': None,
                'qrcode': None,
                'Image': None,
                'Pillow': None
               }

# Update packages that need to be installed.
def update_packages():
    # Walk the package list and verify that the package is installed,
    # or needs installation due to not being present or a specific version
    # being required.
    print("\nChecking package installation...")
    retval = True

    for package in PIP_PACKAGES:
        packagever = PIP_PACKAGES[package]

        # Get package version.
        cmd = 'pip3 show %s' % package
        retcode, output = run_command(cmd)

        stdout = output[0].split('\n')
        installed = True
        installedver = None

        # If the package is not installed, a WARNING will be thrown.
        if stdout[0].startswith('WARNING'):
            if 'not found' in stdout[0]:
                installed = False

        if installed is True:
            for o in stdout:
                k, v = o.split(':')
                if k.strip() == 'Version':
                    installedver = v.strip()
                    break

        if installed is False:
            cmd = 'pip3 install %s' % package
            print("  Installing package '%s'..." % package)
            retcode, output = run_command(cmd)
            if retcode == 0:
                print("  Installed package '%s'." % package)
            else:
                print("  Failed to install package '%s'!" % package)
                print(output)
                retval = False

        else:
            # Right now, packagever is always None.  We'll come back to this someday.
            if packagever is None:
                print("  Package '%s' is installed at version '%s'." % (package, installedver))

    return retval


# Main
if __name__ == "__main__":

    # Defined this class to support verbose help on argument error.
    class MyParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)

    def exit_prog(msg):
        print(msg)
        sys.exit(1)

    try:
        # Specify arguments.
        parser = MyParser(description=__doc__)

        parser.add_argument('-p', '--package', help='Input package file.')
        parser.add_argument('-sd', '--skip-database-update', help='Skip updating the database.', action='store_true')
        parser.add_argument('-sp', '--skip-package-check', help='Skip updating packages.', action='store_true')
        parser.add_argument('-f', '--force', help='Force the comma delimited list of config values to be updated from the provided config.')
        parser.add_argument('-c', '--configtest', help='Test config upgrader with the given file.')
        parser.add_argument('-u', '--updatetest', action='store_true', help='Test package upgrader.')

        options = parser.parse_args()
        package = None

        # If a list of items to forcibly update is provided, convert it to a list.
        if options.force is not None:
            try:
                forcelist = options.force.split(',')
                options.force = forcelist
            except:
                exit_prog("Invalid formatted list of 'forced' configuration items '%s'." % options.force)
        else:
            options.force = []

        if options.configtest is not None:
            print("Testing config upgrader - test mode only")

            # Imports the module from the given path.
            from importlib.machinery import SourceFileLoader

            configpath = options.configtest.split(os.sep)
            configpath = os.path.join(*configpath)

            # Load the config from the given path.
            foo = SourceFileLoader("testconfig", configpath).load_module()
            configdata = foo.Config()

            # Run the updater.
            retval = update_config('.', configdata, options.force)

            print("\nResult: %s" % retval)
            if retval is True:
                sys.exit(0)
            else:
                sys.exit(1)

        if options.updatetest is True:
            print("Testing package upgrader - test mode only")
            retval = update_packages()

            print("  Result: %s" % retval)
            if retval is True:
                sys.exit(0)
            else:
                sys.exit(1)

        # Verify we have an input zip file.
        if options.package is None or not os.path.exists(options.package):
            if options.package is None:
                exit_prog("Must specify a package for update.")

            exit_prog("Missing package '%s'." % options.package)

        # Default directory is the 'electomatic' directory.
        installdir = 'electomatic'

        # Perform the package check first.
        if options.skip_package_check is False:
            retval = update_packages()
            if retval is False:
                exit_prog("Failed package check.")

        fresh = False
        if not os.path.exists(installdir):
            print("Cannot locate installation dir '%s' - proceeding with fresh install...")
            fresh = True

        if fresh is False:
            print("Backing up current installation...")

            # Read the config from that directory so we can get the package name.
            import electomatic.config as config
            configdata = config.Config()
            package = configdata.PACKAGE
            version = configdata.VERSION

            # Go to that directory and run a database backup.
            cwd = os.getcwd()

            os.chdir(installdir)
            retcode, output = backup_database()
            if retcode != 0:
                os.chdir(cwd)
                print(output)
                exit_prog("Failed to back up database.")

            os.chdir(cwd)

            # Zip the directory as is.
            outfile = '%s-backup-%s.zip' % (installdir, version)
            outdir = 'backup'
            outpath = os.path.join(outdir, outfile)

            if not os.path.exists(outdir):
                os.makedirs(outdir)

            print("\nBuilding ZIP file '%s'..." % outfile)
            with zipfile.ZipFile(outpath, 'w') as f_out:
                filelist = list(pathlib.Path(installdir).rglob("*"))

                f_out.write(os.path.join(os.getcwd(), installdir), installdir)
                for f in filelist:
                    f_out.write(os.path.join(os.getcwd(), f), f)

            # Rename the directory to include the version.
            backupdir = '%s-%s' % (installdir, version)
            print("Renaming installation dir as %s..." % backupdir)

            # Safety check...
            if os.path.exists(backupdir):
                exit_prog("Backup directory already exists.")

            os.rename(installdir, backupdir)

        # Unzip the input file.
        print("Extracting ZIP file '%s'..." % options.package)
        with zipfile.ZipFile(options.package, 'r') as f_in:
            f_in.extractall()

        # Copy artifacts from the backed-up copy to the newly installed one.
        if fresh is False:
            print("Restoring artifacts...")
            # Restore folder contents from prior install.
            artifacts = ['images', ['exports', '*_entry_qr_codes.zip'], 'log']
            for a in artifacts:
                if type(a) is list:
                    sourcedir = os.path.join(backupdir, package, a[0])
                    destdir = os.path.join(installdir, package, a[0])

                    if os.path.exists(sourcedir):
                        print("  Restoring '%s'..." % os.path.join(package, '/'.join(a)) )
                        if not os.path.exists(destdir):
                            os.makedirs(destdir)

                        for f in glob.glob(os.path.join(sourcedir, a[1]), recursive=True):
                            if os.path.isfile(f):
                                print("    Restoring '%s'..." % f)
                                shutil.copy(f, destdir)

                else:
                    sourcedir = os.path.join(backupdir, package, a)
                    destdir = os.path.join(installdir, package, a)

                    if os.path.exists(sourcedir):
                        print("  Restoring folder '%s'..." % os.path.join(package, a))
                        shutil.copytree(sourcedir, destdir, dirs_exist_ok=True)

            # Restore config settings from prior install.
            update_config(installdir, configdata, options.force)

            # Execute any database update if there is an upgrade script in the new package.
            # Update the database unless instructed to skip.
            if options.skip_database_update is False:
                try:
                    import electomatic.upgradedb as upgradedb
                    result = upgradedb.upgrade_database(installdir)

                except:
                    print("NOTE: Database update not available.")
            else:
                    print("NOTE: Database update skipped.")

        # Set permissions on files.
        if result == 0:
            print("Setting permissions...")
            for f  in ['serve.py']:
                os.chmod(os.path.join(installdir, f), 0o777)

            print("Update complete.")

        else:
            print("*** Update failed!")
            sys.exit(1)


    except Exception as ex:
        parser.print_help()
        print (traceback.format_exc())
        sys.exit(1)

sys.exit(0)
