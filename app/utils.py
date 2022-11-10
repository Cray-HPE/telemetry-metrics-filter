#  MIT License
#
#  (C) Copyright 2022 Hewlett Packard Enterprise Development LP
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
#  OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#  ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
#  OTHER DEALINGS IN THE SOFTWARE.
#

import re
import time
import calendar

# split time into sections
REGEX_SPLIT_TIME = re.compile(r"([\d\.]{1,12}|[a-zA-Z]{2,3}|[\s/\-T:\+Z]+)")
# split timezone offset
REGEX_TZ_OFFSET = re.compile(r"^(\d{1,2})(\d\d)$")
# Doing the mapping ourselves is 3x faster than using strptime
MONTH_TO_NUMBER = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12
}


def _get_local(year, month, day, hour, minute, second):
    sec = float(second)
    time_tuple = (int(year), int(month), int(day), int(hour), int(minute), int(sec), 0, 0, -1)
    return time.mktime(time_tuple) + (sec - int(sec))


def _get_utc(year, month, day, hour, minute, second, offset):
    sec = float(second)
    time_tuple = (int(year), int(month), int(day), int(hour), int(minute), int(sec), 0, 0, -1)
    return calendar.timegm(time_tuple) + (sec - int(sec)) + offset


def _get_offset(tz):
    if tz.casefold() == 'utc' or tz.casefold() == 'gmt':
        return 0
    if time.tzname[0] == tz:
        return time.timezone
    if time.tzname[1] == tz:
        return time.altzone
    # we can only support variants of our local timezone (without including
    # some extra timezone libs)
    raise ValueError("Unsupported timezone: {}".format(tz))


def _parse_date(fields):
    if fields[1] == ' ':
        # Fri Sep 14 13:03:43 2018
        year = fields[12]
        month = MONTH_TO_NUMBER[fields[2]]
        day = fields[4]
    elif fields[1] == '-':
        # 2020-10-26
        year = fields[0]
        month = fields[2]
        day = fields[4]
    elif fields[1] == '/':
        # 12/14/[20]20
        month = fields[0]
        day = fields[2]
        year = fields[4]

    if len(year) == 2:
        year = '20' + year

    return (year, month, day)


def time_to_epoch_ms(timestamp, safe=False):
    """
    Parse a timestamp to the number of milliseconds since the epoch
    see time_to_epoch_sec for details
    """
    return int(time_to_epoch_sec(timestamp, safe) * 1000)


def time_to_epoch_sec(timestamp, safe=False):
    """
    Parse a timestamp to the number of seconds since the epoch
    Support as many of the various timestamps as possible so we don't have to
    determine what format anything is in.
    The following formats hav been verified.
        Fri Sep 14 13:03:43 2018
        07/13/2021 18:26:36
        12/04/2020 07:47:08 PM UTC
        12/14/2020 - 07:26:13 AM CST
        12/14/20 14:05:45 CST
        12/14/20 04:05:45 AM CST
        2020-10-26T14:29:24Z
        2020-10-26T14:29:24
        2021-07-26T14:25:56.495+0000
        2021-12-15T21:25:41+00:00
        2020-02-29T00:00:00.999999999Z
    local and UTC timezones are supported and processed correctly. Timezones
    from other locales are not supported and will raise an exception.
    """
    try:
        fields = REGEX_SPLIT_TIME.findall(timestamp)

        if len(fields) < 11 or fields[7] != ':':
            raise ValueError("Unknown time format: {}".format(timestamp))

        (year, month, day) = _parse_date(fields)

        # Time
        hour = fields[6]
        minute = fields[8]
        second = fields[10]

        if len(fields) == 11:
            return _get_local(year, month, day, hour, minute, second)
        if len(fields) == 12:
            if fields[11].casefold() != 'z':
                raise ValueError("Unknown time format: {}".format(timestamp))
            offset = 0
        elif len(fields) == 13:
            if fields[1] == ' ':
                # Field 12 is year. No TZ.
                return _get_local(year, month, day, hour, minute, second)
            if fields[11] in ['+', '-']:
                # calc offset ourselves
                tz_offsets = REGEX_TZ_OFFSET.match(fields[12])
                offset = int(tz_offsets[1]) * 3600 + int(tz_offsets[2]) * 60
                if fields[11] == '+':
                    # inverted. UTC to local is specified. We need local to UTC
                    offset = -offset
            else:
                offset = _get_offset(fields[12])
        elif len(fields) == 15 and fields[11] in ['+', '-']:
            offset = int(fields[12]) * 3600 + int(fields[14]) * 60
            if fields[11] == '+':
                # inverted. UTC to local is specified. We need local to UTC
                offset = -offset
        elif len(fields) == 15:
            if fields[12].casefold() == 'pm':
                hour = int(hour) + 12
            offset = _get_offset(fields[14])

        return _get_utc(year, month, day, hour, minute, second, offset)
    except Exception as e:
        if safe:
            return time.time()
        raise e
