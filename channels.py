#
# Parse all multicast URL's from the IPTV stream list
# (Python 3!)
#
import json
import os
import collections
import re
import urllib

import requests

TVHEADEND_USER = ''
TVHEADEND_PASS = ''

FILENAME = ''

hostname = None
assert hostname


TVHEADEND_ROOT = 'http://{}/'.format(hostname)

Channel = collections.namedtuple('Channel', ['name', 'url', 'extras'])


class ParseVLC(object):
    line_regex = re.compile("#EXT(?P<tag>\w+):(?P<value>.*)")

    def __init__(self, file_name):
        if os.path.isfile(file_name):
            self.file = open(file_name, 'r')
        else:
            raise ValueError("File {} does not exist".format(file_name))

    def __iter__(self):
        ext_m3u = False

        buffer = []

        # all lines, with whitespace stripped, and blank lines filtered
        for line in filter(bool, [line.strip() for line in self.file]):
            # eat everything until a non-header line was found
            if not ext_m3u:
                if 'EXTM3U' in line:
                    ext_m3u = True
                continue

            buffer.append(line)

            # is it not a option? -> it is the address
            if not self.line_regex.match(line):
                yield self.parse_section(buffer)
                buffer = []

    def parse_section(self, section):
        name = None
        url = None
        extras = {}

        for line in section:
            m = self.line_regex.match(line)

            if m:
                tag, value = m.groups()
                if tag == 'INF':
                    _, name = value.split(',')
                if tag == 'VLCOPT':
                    key, val = value.split('=')
                    extras[key] = val
            else:
                url = line

        return Channel(name, url, extras)


"""
Wrapper for HTTP request with basic auth, post data
"""


def tvheadend_api_post(sub_url, data):
    url = urllib.parse.urljoin(TVHEADEND_ROOT, sub_url)

    res = requests.post(url,  data=data, auth=(TVHEADEND_USER, TVHEADEND_PASS))
    return res.json()


"""
Use the TVHeadend API to add all channels:
"""
p = ParseVLC(FILENAME)

for channel in p:
    # Get the UUID of iptv or the new channel, not sure.
    uuid_request = tvheadend_api_post("/api/idnode/load", data={
        'class': "mpegts_network",
        'enum': 1,
        'query': ''
    })

    add_request = tvheadend_api_post("/api/mpegts/network/mux_create", data={
        'uuid': uuid_request['entries'][0]['key'],
        'conf': json.dumps({
            "enabled": True,
            "skipinitscan": True,
            "iptv_muxname": channel.name,
            "iptv_url": channel.url,
            "iptv_interface": "eth0",
            "charset": "AUTO"
        })
    })

    print("Added channel {} at {}".format(channel.name, channel.url))
