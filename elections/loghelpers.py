#!/usr/bin/python3

#   Copyright 2021-2022 Steve Strublic
#
#   This work is the personal property of Steve Strublic, and as such may not be
#   used, distributed, or modified without my express consent.

import os

# Available log levels for filtering.
loglevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']


# Fetch the log lines to create a page from the current offset and direction.
def fetch_loglines(logfile, browse, pagesize, linecount, fileoffsets, offset, loglevel, logstr):
    loglines = []

    if browse == 'prev':
        # If at the beginning of the file, going back is really showing the first page.
        if offset == 0:
            browse = 'first'

    elif browse == 'next':
        # If at the end of the file, going forward is really showing the last page.
        if offset == (linecount - 1):
            browse = 'last'

    # Determine the maximum number of lines to fetch from the file.
    linestofetch = pagesize
    if browse in ['prev']:
        # Going backwards is trickier. We have to go back by a page's worth of data,
        # then another page's worth to get the page we want.
        # We also have to skip the line we don't want (the last one read at 'offset').
        linestofetch = (pagesize * 2)

        # If we are at the end of file, the offset is already (count - 1) and as such don't have
        # to back up for a previous page.
        if offset != (linecount - 1):
            offset = max(0, offset - 1)

    # Use the numeric value returned from the form to set the level filter.
    filters = []
    if loglevel > 0:
        filters = loglevels[loglevel:]

    # Get the lines from the logfile at the offset up to the page size.
    with open(logfile, 'r') as lf:
        # Pull lines until we get them all or run out.
        while len(loglines) < linestofetch:
            # Pull the log file line offset from the offsets list and seek the log file to that point.
            seekoffset = fileoffsets[offset]
            lf.seek(seekoffset, os.SEEK_SET)
            linedata = lf.readline()

            # Add the log line if filtered (or no filters).
            if len(filters) == 0 or any(x in linedata for x in filters):
                if len(logstr) == 0 or logstr in linedata:
                    loglines.append(((offset + 1), linedata))

            # Going forward, add one to the line offset and stop at end of file.
            if browse in [None, 'first', 'next']:
                offset += 1
                if offset >= linecount:
                    break

            # Going backward (or last page), subtract from the offset and stop at beginning of file.
            elif browse in ['prev', 'last']:
                offset -= 1
                if offset < 0:
                    break

    # Find out how many lines to pull from the loglines list.
    lastline = min(pagesize, len(loglines))

    # If going backward (or last page), reverse the list since we walked it backwards.
    if browse in ['prev', 'last']:
        loglines = list(reversed(loglines))

        # If going backwards, we want the offset (line number) of the start of the first page we are keeping.
        # Otherwise (last page), we backed up one too many and need to advance by one to set the offset for
        # the next operation.
        if browse in ['prev']:
            offset = loglines[lastline - 1][0]
        else:
            offset += 1

    # Pull the log data from the log lines list, from start to (number of lines to render).
    loglines = loglines[0:lastline]

    # Bound the offset to the valid range.
    offset = max(0, min(offset, (linecount - 1)))

    return loglines, offset
