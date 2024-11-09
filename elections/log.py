#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os, sys, zipfile, traceback
import logging, logging.handlers

from flask import flash, request

from elections import app, getRemoteAddr

LOGFORMAT = "%(asctime)s.%(msecs)03d;%(levelname)-8s;%(clubid)s/%(eventid)s/%(user)s;%(ipaddr)s;%(message)s"

# Create a compressing rotating file handler.
# Slavishly borrowed from the RotatingFileHandler.
class CompressedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, logfile, offsetsfile, *args, **kwargs):
        self.logfile = logfile
        self.offsetsfile = offsetsfile

        # Cache the log file line offsets by reading from file, so we don't have to read them
        # every time we read the log.  The cache and file will be kept in sync on each log write.
        self.offsets = self._load_offsets_file()

        # Pass the rest to our superclass.
        super(CompressedRotatingFileHandler, self).__init__(*args, **kwargs)


    # Read the log file line offsets from file.
    def _load_offsets_file(self):
        offsets = []
        try:
            with open(self.offsetsfile, 'r') as of:
                line = of.readline()
                while line:
                    offsets.append(int(line))
                    line = of.readline()

        except:
            # When there's no log offsets file, there's nothing to load.
            pass

        return offsets


    # Override this method with our own...
    def emit(self, record):
        # This is the default that is written if there is no log file / offsets file.
        offset = 0

        # Open the log file and read the end-of-file.  The end of file is the start offset
        # for the new line to be added.
        with open(self.logfile, 'r') as lf:
            # Seek the end of the log file and append that to the offsets file.
            lf.seek(0, os.SEEK_END)
            offset = lf.tell()

        # Open and write the new offset to the offsets file.
        with open(self.offsetsfile, 'a') as of:
            # Write the offset of the end of the file as the offset of the new line.
            self.offsets.append(offset)
            of.write("%d\n" % offset)

            lines = record.msg.split('\n')
            if len(lines) > 1:
                # Process all the lines (split by newline) in the record, except the last.
                # The end-of-file position will serve as the offset for the next record.
                for index, line in enumerate(lines[:-1]):
                    # The first line of the bundle needs the log line's formatting to calculate the correct offset for the following lines.
                    # The following lines do not need the formatting as it only applies to the first line in the bundle.
                    if index == 0:
                        logline = 'xx-xx-xxxx xx:xx:xx.xxx;xxxxxxxx;%d/%d/%s;%s;' % \
                                (record.clubid, record.eventid, record.user, record.ipaddr) + line
                    else:
                        logline = line

                    # Add the length of the line to the current offset, adjusting for platform.
                    if sys.platform == "win32":
                        linelen = len(logline) + 2
                    else:
                        linelen = len(logline) + 1

                    # Add the line length to the offset and write to the offsets file.
                    offset += linelen
                    self.offsets.append(offset)
                    of.write("%d\n" % offset)

        # Pass the rest to our superclass.
        super(CompressedRotatingFileHandler, self).emit(record)


    # Handler rollover for our version of the handler.
    # Override this method with our own...
    def doRollover(self, reset=False):
        """
        Do a rollover, as described in __init__().
        """
        # Close the stream.
        if self.stream:
            self.stream.close()
            self.stream = None

        if self.backupCount > 0:
            print(" *** Log file '%s': Rolling log " % (self.logfile))

            # Rename the existing .x.zip files based on the backup count.
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename("%s.%d.zip" % (self.baseFilename, i))
                dfn = self.rotation_filename("%s.%d.zip" % (self.baseFilename, i + 1))
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)

            # Build the output ZIP file and remove any prior (which shouldn't exist
            # since we just renamed it away).
            dfn = self.rotation_filename(self.baseFilename + ".zip")
            if os.path.exists(dfn):
                os.remove(dfn)

            # Since we have a log file, compress it.
            if os.path.exists(self.baseFilename):
                with zipfile.ZipFile(dfn, 'w', compression=zipfile.ZIP_DEFLATED) as f_out:
                    f_out.write(self.baseFilename, os.path.basename(self.baseFilename))

                # Remove the current log file we just compressed, and rename the
                # compressed file as the first backup.
                os.remove(self.baseFilename)
                os.rename(dfn, self.baseFilename + ".1.zip")

            try:
                # Remove the log offsets file.
                os.remove(self.offsetsfile)
                self.offsets = []

                # On a straight rollover, the rollover triggers before a log in-flight is written and as such
                # requires the offsets file to have the base offset of 0 for that first log that is written after
                # the rollover completes.  If resetting the log by forcing a rollover, this is not good because
                # there is no log in flight.  So don't do it.  The next log written will write the offset as 0.
                if reset is False:
                    with open(self.offsetsfile, 'w') as of:
                        self.offsets.append(0)
                        of.write('0\n')

            except Exception as ex:
                print(" *** Log file '%s': Failed to remove log offsets file!" % (self.logfile))


        # Reopen the stream.
        if not self.delay:
            self.stream = self._open()


# The AppLog is an instance of a logger for the application.
# The intent is to assign an instance to each user, to simplify
# logging within the application.  As users log in to / select clubs and events,
# an instance of this class is assigned to the current_user.  Only one logger instance
# is created for a given club or event, with multiple AppLog classes fetching those instances.
class AppLog():
    def __init__(self, clubid, eventid, logbasename, logpath, user='System'):

        self.clubid = clubid
        self.eventid = eventid

        if not os.path.exists(logpath):
            print("### Creating logging directory '%s'" % logpath)
            os.makedirs(logpath)

        self.user = user

        # Build the log file name.
        if clubid == 0 and eventid == 0:
            self.logname = logbasename
        else:
            # Set the log name as a child of the root.
            if eventid == 0:
                # Event ID 0 = Club level log.
                self.logname = '%s.%d' % (logbasename, clubid)
            else:
                # Club and event nonzero = Event level log.
                self.logname = '%s.%d.%d' % (logbasename, clubid, eventid)

        # Stash our log file and offsets file.
        # These get passed to our log handler for generating file offsets for log file parsing.
        self.logfile = os.path.join(logpath, '%s.log' % self.logname)
        self.offsetsfile = os.path.join(logpath, '%s.offsets.log' % self.logname)

        # Root logger gets special treatment to create the root and console handler.
        if clubid == 0 and eventid == 0:
            # Get the logger instance.
            self.logger = logging.getLogger(app.config.get('LOG_BASENAME'))

            # We only want one instance of this to exist, so don't create it if a handler already is present.
            # That lets us create logger objects that point to the same log instance.
            if len(self.logger.handlers) == 0:
                handler = CompressedRotatingFileHandler(self.logfile, self.offsetsfile,
                                                        os.path.join(logpath, '%s.log' % self.logname),
                                                        backupCount=app.config.get('LOG_BACKUP_FILE_COUNT'),
                                                        maxBytes=app.config.get("LOG_BACKUP_FILE_SIZE"))

                handler.setFormatter(logging.Formatter(LOGFORMAT, datefmt='%m-%d-%Y %H:%M:%S'))
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.DEBUG)

                # Also create the console output for critical events.
                console = logging.getLogger()
                consoleformat = logging.Formatter('%(asctime)s.%(msecs)03d %(levelname)-8s: %(message)s', datefmt='%m-%d-%Y %H:%M:%S')
                handler = logging.StreamHandler()
                handler.setFormatter(consoleformat)
                handler.setLevel(logging.CRITICAL)
                console.addHandler(handler)

        else:
            # Get the logger instance.
            self.logger = logging.getLogger(self.logname)

            # We only want one instance of this to exist, so don't create it if a handler already is present.
            # That lets us create logger objects that point to the same log instance.
            if len(self.logger.handlers) == 0:
                handler = CompressedRotatingFileHandler(self.logfile, self.offsetsfile,
                                                        os.path.join(logpath, '%s.log' % self.logname),
                                                        backupCount=app.config.get('LOG_BACKUP_FILE_COUNT'),
                                                        maxBytes=app.config.get("LOG_BACKUP_FILE_SIZE"))
                handler.setFormatter(logging.Formatter(LOGFORMAT, datefmt='%m-%d-%Y %H:%M:%S'))
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.DEBUG)

        # Build / verify / rebuild the log offsets file.
        built_offset_list = self.__build_offset_list()
        if built_offset_list is True:
            # Reload the offsets from the newly created offsets file.
            handler = self.logger.handlers[0]
            handler.offsets = handler._load_offsets_file()

            self.logger.critical("Rebuilt file offsets list", extra={'clubid': self.clubid, 'eventid': self.eventid, 'user': self.user, 'ipaddr': ''})
            self.logger.propagate = True


    # Build a pad / indent value.
    def __pad(self, indent):
        pad = ''
        if indent > 0:
            pad = '%*s' % ((indent * 3), ' ')
        return pad


    # Get the log line offsets cache for our single log handler instance.
    def get_offsets(self):
        return self.logger.handlers[0].offsets


    # Count the lines in the log file.
    def count_logfile_lines(self, offsetfile=False):
        # Reader for counting the number of lines in the file.
        def _count_generator(reader, chunksize):
            b = reader(chunksize)
            while b:
                yield b
                b = reader(chunksize)

        # Quickly count the lines in the log file.
        count = 0

        logfile = self.logfile
        if offsetfile is True:
            logfile = self.offsetsfile

        with open(logfile, 'rb') as fp:
            chunksize = app.config.get('LOGFILE_OFFSETS_CHUNKSIZE')
            c_generator = _count_generator(fp.raw.read, chunksize)
            count = sum(buffer.count(b'\n') for buffer in c_generator)

        return count


    # Build a list of file offsets for individual log lines from the log file.
    def __build_offset_list(self):
        try:
            build_offsets_file = False

            # If the log file exists, and the offsets file does not, create one.
            if os.path.exists(self.logfile):
                if not os.path.exists(self.offsetsfile):
                    print(" *** Log file '%s': No log offsets file" % self.logfile)
                    build_offsets_file = True
                else:
                    # Count the number of lines on the log file and the offsets file.
                    # If they do not match, rebuild the offsets file.
                    logfile_lines = self.count_logfile_lines()
                    offset_lines = self.count_logfile_lines(offsetfile=True)

                    if logfile_lines != offset_lines:
                        print(" *** Log file '%s': Line count mismatch (file: %d, offsets: %d)" % (self.logfile, logfile_lines, offset_lines))
                        build_offsets_file = True

            # Walk the log file one line at a time, recording the file offsets for each.
            if build_offsets_file is True:
                # Remove the prior offsets file.
                if os.path.exists(self.offsetsfile):
                    os.remove(self.offsetsfile)

                # Reader for pulling buffer data from file.
                def _buffer_generator(reader, bufsize):
                    b = reader(bufsize)
                    while b:
                        yield b
                        b = reader(bufsize)

                with open(self.logfile, 'rb') as lf:
                    with open(self.offsetsfile, 'w') as of:
                        offset = 0
                        last_offset = 0
                        bufsize = app.config.get('LOGFILE_OFFSETS_CHUNKSIZE')
                        generator = _buffer_generator(lf.raw.read, bufsize)

                        # Initialize with 0 if the file is not empty (end != 0) as the offset for the first line.
                        lf.seek(0, os.SEEK_END)
                        pos = lf.tell()
                        if pos != 0:
                            of.write("0\n")

                        # Seek back to the beginning of the file.
                        lf.seek(0)

                        # Run through the file in RAW mode and find all the newlines in each file buffer.
                        for buffer in generator:
                            offsets = []
                            bufoffset = 0

                            while True:
                                # Find the next newline.
                                bufoffset = buffer.find(b'\n', bufoffset)

                                # No more newlines?
                                if bufoffset == -1:
                                    # Write out the offsets we accumulated.
                                    for o in offsets[:-1]:
                                        of.write('%d\n' % o)

                                    # Add the bytes that didn't get processed so we start on a boundary next time.
                                    if (offset % bufsize) != 0:
                                        offset += bufsize - (offset % bufsize)
                                    break

                                else:
                                    # Advance past the newline character.
                                    bufoffset += 1

                                    # Add our last recorded offset and the buffer offset in this buffer,
                                    # and store in the offsets list.
                                    offset = last_offset + bufoffset
                                    offsets.append(offset)

                            # Remember the last offset generated for the next buffer to process.
                            last_offset = offset

                print("     Rebuilt offsets file '%s'" % self.offsetsfile)

        except Exception as ex:
            print(" *** Failed to update log offsets file!")
            print(str(ex))
            print(traceback.format_exc())

        return build_offsets_file


    # Helper to create the unique log ID.
    def get_id(clubid=0, eventid=0):
        return '%d_%d' % (clubid, eventid)


    # Reset the contents of the log this user is accessing by forcing a rollover.
    def reset(self):
        if len(self.logger.handlers) > 0:
            handler = self.logger.handlers[0]
            handler.doRollover(reset=True)
            self.critical("### Cleared log for club '%d', event '%d' ###" % (self.clubid, self.eventid))
        else:
            self.critical("### Attempted to clear missing log for club '%d', event '%d' ###" % (self.clubid, self.eventid))


    # Log level methods that wrap the logging class.

    # For debug messages, propagation is disabled by default.
    # This keeps debug local (by not sending it to the parent) and less spammy for club and root logs.
    def debug(self, msg, ipaddr='', indent=0, propagate=False):
        if propagate is False:
            self.logger.propagate = False

        # Rather than change all logs to push the IP address, we fetch it here if there is a valid request object
        # and have not specified something in the call.
        if len(ipaddr) == 0 and request:
            ipaddr = getRemoteAddr(request)

        self.logger.debug('%s%s' % (self.__pad(indent), msg), extra={'clubid': self.clubid, 'eventid': self.eventid, 'user': self.user, 'ipaddr': ipaddr})
        self.logger.propagate = True

    # For info messages, propagation is disabled by default.
    # This keeps event info local (by not sending it to the parent) and less spammy for club and root logs.
    def info(self, msg, ipaddr='', indent=0, propagate=False):
        if propagate is False:
            self.logger.propagate = False

        # Rather than change all logs to push the IP address, we fetch it here if there is a valid request object
        # and have not specified something in the call.
        if len(ipaddr) == 0 and request:
            ipaddr = getRemoteAddr(request)

        self.logger.info('%s%s' % (self.__pad(indent), msg), extra={'clubid': self.clubid, 'eventid': self.eventid, 'user': self.user, 'ipaddr': ipaddr})
        self.logger.propagate = True

    def error(self, msg, ipaddr='', indent=0, propagate=True):
        if propagate is False:
            self.logger.propagate = False

        # Rather than change all logs to push the IP address, we fetch it here if there is a valid request object
        # and have not specified something in the call.
        if len(ipaddr) == 0 and request:
            ipaddr = getRemoteAddr(request)

        self.logger.error('%s%s' % (self.__pad(indent), msg), extra={'clubid': self.clubid, 'eventid': self.eventid, 'user': self.user, 'ipaddr': ipaddr})
        self.logger.propagate = True

    def warning(self, msg, ipaddr='', indent=0, propagate=True):
        if propagate is False:
            self.logger.propagate = False

        # Rather than change all logs to push the IP address, we fetch it here if there is a valid request object
        # and have not specified something in the call.
        if len(ipaddr) == 0 and request:
            ipaddr = getRemoteAddr(request)

        self.logger.warning('%s%s' % (self.__pad(indent), msg), extra={'clubid': self.clubid, 'eventid': self.eventid, 'user': self.user, 'ipaddr': ipaddr})
        self.logger.propagate = True

    def critical(self, msg, ipaddr='', indent=0, propagate=True):
        if propagate is False:
            self.logger.propagate = False

        # Rather than change all logs to push the IP address, we fetch it here if there is a valid request object
        # and have not specified something in the call.
        if len(ipaddr) == 0 and request:
            ipaddr = getRemoteAddr(request)

        self.logger.critical('%s%s' % (self.__pad(indent), msg), extra={'clubid': self.clubid, 'eventid': self.eventid, 'user': self.user, 'ipaddr': ipaddr})
        self.logger.propagate = True


    # Log a message and dump to the browser session as well.
    # The default is an error message as the usual case.
    # By default, these logs are not propagated upward; the caller must indicate to do so.
    # If specified, the messazge is dispalyed but not logged.
    def flashlog(self, prefix, msg, level='error', highlight=True, indent=False, large=False, propagate=False, log=True):
        '''
            Log and output flash (message to session).

            :param  prefix: Header in log message.

            :param  msg: Message to log.

            :param  level: Level for flash (default; 'error').

            :param log: If False, do not log the message.
        '''
        if prefix is not None:
            logmsg = "%s-> %s: %s" % ('-> ' if indent is True else '', prefix, msg)
        else:
            logmsg = "%s-> %s" %('-> ' if indent is True else '', msg)

        # Only log if specified (default).
        if log is True:
            if level == 'error':
                self.error(logmsg, propagate=propagate)
            elif level == 'warning':
                self.warning(logmsg, propagate=propagate)
            else:
                self.info(logmsg, propagate=propagate)

        if highlight is True:
            level += '-bold'

        if large is True:
            level += '-large'

        if indent is True:
            level += '-indent'

        if len(msg) == 0:
            level += '-blank'

        if level in ['error', 'warning']:
            flash(logmsg, level)
        else:
            flash(msg, level)
